from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from io import BytesIO
from logging import getLogger
from os import getenv
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from .data.database import create_database_engine
from .data.motor_classifier import ModelUnavailableError, MotorClassifier, Prediction, PredictionStatus
from .data.photo_files import PhotoSizeError, open_photo
from .data.repository import MotorRepository
from .data.schema import motor_models

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
IMAGE_MEDIA_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
logger = getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    classifier_ready: bool
    catalog_ready: bool


class ModelsResponse(BaseModel):
    model_ids: list[str]
    demo: bool


class CandidateResponse(BaseModel):
    model_id: str
    score: float


class PredictionResponse(BaseModel):
    candidates: list[CandidateResponse]
    status: PredictionStatus


class MotorSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    manufacturer: str
    product_line: str
    commercial_model: str


class MotorResponse(MotorSummaryResponse):
    source_reference: str
    technical_specs: dict[str, str | int | float]


class ErrorResponse(BaseModel):
    detail: str


def _classifier(request: Request) -> MotorClassifier:
    classifier = request.app.state.classifier
    if classifier is None:
        raise HTTPException(503, "Classificador indisponível.")
    return classifier


async def _read_upload(request: Request, file: BytesIO) -> None:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            length = int(content_length)
        except ValueError as error:
            raise HTTPException(400, "Content-Length inválido.") from error
        if length < 0:
            raise HTTPException(400, "Content-Length inválido.")
        if length > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "A foto excede o limite de 8 MiB.")
    try:
        async for chunk in request.stream():
            if file.tell() + len(chunk) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "A foto excede o limite de 8 MiB.")
            file.write(chunk)
    except ClientDisconnect as error:
        raise HTTPException(400, "Envio interrompido.") from error
    if not file.tell():
        raise HTTPException(400, "O corpo deve conter uma fotografia.")
    file.seek(0)


def _predict_upload(classifier: MotorClassifier, file: BytesIO, expected_format: str) -> Prediction:
    try:
        with open_photo(file, max_pixels=MAX_IMAGE_PIXELS) as photo:
            if photo.format != expected_format:
                raise HTTPException(415, "O conteúdo da foto difere do Content-Type.")
            return classifier.predict_photo(photo)
    except PhotoSizeError as error:
        raise HTTPException(413, "A foto excede o limite de 24 megapixels.") from error
    except (OSError, ValueError) as error:
        raise HTTPException(400, "Fotografia inválida.") from error
    except ModelUnavailableError as error:
        logger.warning("Falha na inferência: %s", error)
        raise HTTPException(503, "Classificador indisponível.") from error


def create_app(*, checkpoint: Path | None = None, database: Engine | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = database if database is not None else create_database_engine()
        application.state.engine = engine
        application.state.classifier = None
        try:
            configured = checkpoint or getenv("MFI_CHECKPOINT")
            if configured:
                try:
                    application.state.classifier = MotorClassifier(configured)
                except ModelUnavailableError as error:
                    logger.warning("%s", error)
            yield
        finally:
            if database is None:
                engine.dispose()

    application = FastAPI(title="MFI — API de inferência", version="0.1.0", lifespan=lifespan)

    @application.get("/health", responses={503: {"model": HealthResponse}})
    def health(response: Response) -> HealthResponse:
        classifier_ready = application.state.classifier is not None
        try:
            with application.state.engine.connect() as connection:
                connection.execute(select(motor_models.c.model_id).limit(1))
            catalog_ready = True
        except SQLAlchemyError:
            catalog_ready = False
        ready = classifier_ready and catalog_ready
        if not ready:
            response.status_code = 503
        return HealthResponse(
            status="ok" if ready else "unavailable",
            classifier_ready=classifier_ready, catalog_ready=catalog_ready,
        )

    @application.get("/models", responses={503: {"model": ErrorResponse}})
    def models(request: Request) -> ModelsResponse:
        classifier = _classifier(request)
        return ModelsResponse(model_ids=list(classifier.class_ids), demo=classifier.is_demo)

    @application.post(
        "/predict",
        response_model=PredictionResponse,
        description="Envie os bytes de uma única foto estática. Limites de 8 MiB e 24 megapixels.",
        responses={
            code: {"model": ErrorResponse, "description": reason}
            for code, reason in (
                (400, "Fotografia inválida ou vazia"), (413, "Limite de upload excedido"),
                (415, "Content-Type incompatível"), (503, "Classificador indisponível"),
            )
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    media_type: {"schema": {"type": "string", "format": "binary"}}
                    for media_type in IMAGE_MEDIA_TYPES
                },
            },
        },
    )
    async def predict(request: Request) -> Prediction:
        classifier = _classifier(request)
        media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
        expected_format = IMAGE_MEDIA_TYPES.get(media_type)
        if expected_format is None:
            raise HTTPException(415, "Use image/jpeg, image/png ou image/webp.")
        with BytesIO() as file:
            await _read_upload(request, file)
            return await run_in_threadpool(_predict_upload, classifier, file, expected_format)

    @application.get(
        "/motors",
        responses={503: {"model": ErrorResponse, "description": "Catálogo indisponível"}},
        description="Lista os modelos comerciais cadastrados, em ordem de ID.",
    )
    def motors() -> list[MotorSummaryResponse]:
        try:
            with application.state.engine.connect() as connection:
                models = MotorRepository(connection).list_models()
        except SQLAlchemyError as error:
            raise HTTPException(503, "Catálogo indisponível.") from error
        return [MotorSummaryResponse.model_validate(model) for model in models]

    @application.get("/motors/{motor_id:path}", responses={
        404: {"model": ErrorResponse}, 503: {"model": ErrorResponse},
    })
    def motor(motor_id: str) -> MotorResponse:
        try:
            with application.state.engine.connect() as connection:
                model = MotorRepository(connection).get_model(motor_id)
        except SQLAlchemyError as error:
            raise HTTPException(503, "Catálogo indisponível.") from error
        if model is None:
            raise HTTPException(404, "Modelo de motor não encontrado.")
        return MotorResponse.model_validate(model)

    return application


app = create_app()

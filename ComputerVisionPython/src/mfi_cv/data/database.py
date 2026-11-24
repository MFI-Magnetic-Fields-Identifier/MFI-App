from os import getenv
from pathlib import Path

from sqlalchemy import URL, create_engine, event, make_url
from sqlalchemy.engine import Engine


def database_url() -> URL:
    configured_url = getenv("MFI_DATABASE_URL")
    if configured_url:
        return make_url(configured_url)
    return URL.create("sqlite", database=str(Path("mfi_cv.sqlite3").resolve()))


def create_database_engine(url: str | URL | None = None) -> Engine:
    engine = create_engine(url if url is not None else database_url(), hide_parameters=True)
    if engine.dialect.name == "sqlite":
        # O SQLite exige habilitar chaves estrangeiras em cada conexão.
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    return engine

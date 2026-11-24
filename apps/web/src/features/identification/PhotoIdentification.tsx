import { useEffect, useRef, useState, type FormEvent } from 'react'
import { getMotorDetails, photoAccept, predictPhoto, type MotorDetails, type Prediction, type PredictionStatus } from './predict'

type UploadState =
  | { state: 'idle' | 'pending' }
  | { state: 'error'; message: string }
  | { state: 'result'; prediction: Prediction; motor: MotorDetails | null; motorError: string | null }

const statusLabels: Record<PredictionStatus, string> = {
  accepted: 'Candidato principal disponível',
  needs_confirmation: 'Identificação requer confirmação',
  unknown: 'Identificação inconclusiva',
}
const scoreFormat = new Intl.NumberFormat('pt-BR', { style: 'percent', maximumFractionDigits: 1 })

export function PhotoIdentification() {
  const [photo, setPhoto] = useState<File | null>(null)
  const [upload, setUpload] = useState<UploadState>({ state: 'idle' })
  const [cameraOpen, setCameraOpen] = useState(false)
  const [cameraError, setCameraError] = useState<string | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const pending = upload.state === 'pending'

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
  }, [])

  async function startCamera() {
    setCameraError(null)
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('A câmera requer HTTPS (ou localhost) e suporte do navegador.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 960 } },
      })
      streamRef.current = stream
      setCameraOpen(true)
      if (videoRef.current) videoRef.current.srcObject = stream
    } catch (error) {
      setCameraError(error instanceof DOMException && error.name === 'NotAllowedError'
        ? 'Permita o acesso à câmera nas configurações do navegador.'
        : 'Não foi possível iniciar a câmera neste dispositivo.')
    }
  }

  function stopCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    setCameraOpen(false)
  }

  async function captureFrame() {
    const video = videoRef.current
    if (!video || video.videoWidth === 0) {
      setCameraError('A câmera ainda está carregando. Tente novamente em instantes.')
      return
    }
    const scale = Math.min(1, 1920 / Math.max(video.videoWidth, video.videoHeight))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(video.videoWidth * scale)
    canvas.height = Math.round(video.videoHeight * scale)
    const context = canvas.getContext('2d')
    if (!context) {
      setCameraError('Não foi possível preparar a imagem capturada.')
      return
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.86))
    if (!blob) {
      setCameraError('Não foi possível capturar a imagem.')
      return
    }
    setPhoto(new File([blob], `motor-${Date.now()}.jpg`, { type: 'image/jpeg' }))
    setUpload({ state: 'idle' })
    setCameraError(null)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!photo || pending) return

    setUpload({ state: 'pending' })
    try {
      const prediction = await predictPhoto(photo)
      const candidate = prediction.status === 'unknown' ? null : prediction.candidates[0]
      let motor: MotorDetails | null = null
      let motorError: string | null = null
      if (candidate) {
        try {
          motor = await getMotorDetails(candidate.model_id)
        } catch (error) {
          motorError = error instanceof Error ? error.message : 'Não foi possível consultar o catálogo.'
        }
      }
      setUpload({ state: 'result', prediction, motor, motorError })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Não foi possível analisar a foto.'
      setUpload({ state: 'error', message })
    }
  }

  return (
    <section className="identification" aria-labelledby="identification-heading">
      <h2 id="identification-heading">Identificar motor pela câmera</h2>
      <p className="camera-intro">Aponte para o motor, capture uma imagem e envie para a API de identificação.</p>
      <div className={`camera-stage${cameraOpen ? ' camera-active' : ''}`}>
        <video ref={videoRef} autoPlay playsInline muted aria-label="Prévia da câmera" />
        {cameraOpen && <div className="camera-reticle" aria-hidden="true"><span>Enquadre o motor</span></div>}
        {!cameraOpen && <p className="camera-placeholder">Prévia da câmera aparece aqui</p>}
      </div>
      <div className="camera-controls">
        {!cameraOpen
          ? <button type="button" onClick={startCamera}>Abrir câmera</button>
          : <>
            <button type="button" onClick={captureFrame}>Capturar imagem</button>
            <button type="button" className="secondary-button" onClick={stopCamera}>Fechar câmera</button>
          </>}
        {photo && <span className="capture-ready">Imagem pronta para analisar</span>}
      </div>
      {cameraError && <p className="upload-feedback upload-error" role="alert">{cameraError}</p>}
      <form onSubmit={submit} aria-busy={pending}>
        <div className="upload-controls">
          <div>
            <label htmlFor="motor-photo">Ou escolha uma imagem</label>
            <input
              id="motor-photo"
              type="file"
              accept={photoAccept}
              aria-describedby="photo-hint"
              disabled={pending}
              onChange={(event) => {
                setPhoto(event.currentTarget.files?.[0] ?? null)
                setUpload({ state: 'idle' })
              }}
            />
            <p id="photo-hint">JPEG, PNG ou WebP · até 8 MiB</p>
          </div>
          <button type="submit" disabled={!photo || pending}>{pending ? 'Analisando…' : 'Analisar motor'}</button>
        </div>
      </form>

      <div aria-live="polite" aria-atomic="true">
        {pending && <p className="upload-feedback">Analisando a foto…</p>}
        {upload.state === 'error' && <p className="upload-feedback upload-error">{upload.message}</p>}
        {upload.state === 'result' && (
          <div className="upload-feedback">
            <p className="prediction-status">{statusLabels[upload.prediction.status]}</p>
            <ol className="candidates" aria-label="Candidatos sugeridos">
              {upload.prediction.candidates.map((candidate) => (
                <li key={candidate.model_id}>
                  <span>{candidate.model_id}</span>
                  <strong>{scoreFormat.format(candidate.score)}</strong>
                </li>
              ))}
            </ol>
            <p className="score-note">Pontuações do classificador, sem calibração probabilística.</p>
            {upload.motor && (
              <section className="identified-motor" aria-label="Dados do candidato no catálogo">
                <p className="prediction-status">Candidato no catálogo</p>
                <h3>{upload.motor.manufacturer} · {upload.motor.commercial_model}</h3>
                <p className="motor-line">{upload.motor.product_line} · ID {upload.motor.model_id}</p>
                {Object.entries(upload.motor.technical_specs).length > 0 && (
                  <dl className="motor-specs">
                    {Object.entries(upload.motor.technical_specs).map(([label, value]) => (
                      <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
                    ))}
                  </dl>
                )}
                <p className="score-note">Fonte: {upload.motor.source_reference}</p>
              </section>
            )}
            {upload.motorError && <p className="upload-feedback upload-error">{upload.motorError}</p>}
            <p className="field-note"><strong>Campo magnético:</strong> esta API identifica o modelo e consulta seus dados; ela ainda não retorna uma medição em teslas nem uma simulação do campo.</p>
          </div>
        )}
      </div>
    </section>
  )
}

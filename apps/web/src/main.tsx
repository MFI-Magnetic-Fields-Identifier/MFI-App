import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { PhotoIdentification } from './features/identification/PhotoIdentification'
import profiles from './profiles.json'
import './style.css'

function App() {
  const [selectedId, setSelectedId] = useState(profiles[0]?.id)
  const profile = profiles.find(({ id }) => id === selectedId)

  return (
    <>
      <header className="topbar">
        <div className="shell brand">
          <span className="brand-mark" aria-hidden="true">MFI</span>
          <span>Magnetic Fields Identifier</span>
        </div>
      </header>

      <main className="shell workspace">
        <h1>Selecione um motor</h1>
        <p className="intro">Escolha um perfil de demonstração para consultar seus parâmetros.</p>

        <div className="catalog">
          <fieldset className="profiles">
            <legend>Perfis disponíveis</legend>
            {profiles.map((item) => (
              <label className="profile-option" key={item.id}>
                <span>
                  <strong>{item.name}</strong>
                  <span className="option-specs">{item.frequencyHz} Hz · {item.poles} polos</span>
                </span>
                <input
                  type="radio"
                  name="motor-profile"
                  value={item.id}
                  checked={selectedId === item.id}
                  onChange={() => setSelectedId(item.id)}
                />
              </label>
            ))}
          </fieldset>

          <section className="details" aria-label="Perfil selecionado" aria-live="polite">
            {profile ? (
              <>
                <div className="details-heading">
                  <p className="detail-label">Perfil selecionado</p>
                  <h2>{profile.name}</h2>
                </div>
                <dl className="specs">
                  <div>
                    <dt>Fases</dt>
                    <dd>{profile.phases}</dd>
                  </div>
                  <div>
                    <dt>Frequência</dt>
                    <dd>{profile.frequencyHz} <span>Hz</span></dd>
                  </div>
                  <div>
                    <dt>Polos</dt>
                    <dd>{profile.poles}</dd>
                  </div>
                </dl>
                <p className="note">Valores ilustrativos para perfis genéricos de motores.</p>
              </>
            ) : (
              <p className="note">Nenhum perfil disponível.</p>
            )}
          </section>
        </div>
        <PhotoIdentification />
      </main>
    </>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

import { useLang } from '../context/LangContext'

export default function StagingNotice() {
  const { lang } = useLang()
  if (import.meta.env.VITE_DEPLOYMENT_ENVIRONMENT !== 'staging') return null
  return <aside aria-label={lang === 'ES' ? 'Entorno de pruebas' : 'Test environment'}
    style={{ background: '#EEE8DD', color: '#504737', padding: '4px 16px', fontSize: 10, lineHeight: 1.5, textAlign: 'center' }}>
    {lang === 'ES' ? 'Vista previa de contratación' : 'Hiring preview'}
  </aside>
}

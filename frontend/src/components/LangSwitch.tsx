import { useEffect, useState } from 'react'
import { Languages } from 'lucide-react'
import { getLang, setLang, type Lang } from '../i18n'

/** EN | ES switch. English is the default; the choice is remembered in this browser. */
export default function LangSwitch({ dark = false }: { dark?: boolean }) {
  const [lang, setL] = useState<Lang>(getLang())
  useEffect(() => {
    const h = () => setL(getLang())
    window.addEventListener('tm:lang', h)
    return () => window.removeEventListener('tm:lang', h)
  }, [])
  const choose = (l: Lang) => { setL(l); setLang(l) }
  return (
    <div className="seg" data-no-translate title="Language / Idioma" style={dark ? { borderColor: 'rgba(255,255,255,.3)' } : undefined}>
      <span style={{ display: 'grid', placeItems: 'center', padding: '0 6px', color: dark ? '#c9d4e6' : 'var(--text-3)' }}><Languages size={14} /></span>
      <button className={lang === 'en' ? 'on' : ''} onClick={() => choose('en')} aria-pressed={lang === 'en'}>EN</button>
      <button className={lang === 'es' ? 'on' : ''} onClick={() => choose('es')} aria-pressed={lang === 'es'}>ES</button>
    </div>
  )
}

/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { Building2, Leaf, LockKeyhole, ShieldCheck, UserRound } from 'lucide-react'
import { api } from './api'
import LangSwitch from './components/LangSwitch'

export interface User { id: number; first_name: string; last_name: string; name: string; email: string }
interface AuthState { user: User | null; guest: boolean; logout: () => Promise<void>; refresh: () => Promise<void> }

const AuthCtx = createContext<AuthState | null>(null)

export function useAuth() {
  const a = useContext(AuthCtx)
  if (!a) throw new Error('auth not ready')
  return a
}

/** Shows the welcome screen until the visitor signs in, creates an account or continues as a guest. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ user: User | null; guest: boolean } | null>(null)
  const refresh = useCallback(async () => {
    const r = await api.get('/api/auth/me')
    setState({ user: r.user, guest: !!r.guest })
  }, [])
  useEffect(() => { refresh().catch(() => setState({ user: null, guest: false })) }, [refresh])
  useEffect(() => {
    const h = () => setState({ user: null, guest: false })
    window.addEventListener('tm:auth-required', h)
    return () => window.removeEventListener('tm:auth-required', h)
  }, [])
  const logout = async () => { await api.post('/api/auth/logout'); setState({ user: null, guest: false }); window.history.replaceState({}, '', '/') }

  if (!state) return <div className="empty"><span className="spinner" /></div>
  if (!state.user && !state.guest) return <Welcome onDone={refresh} />
  return <AuthCtx.Provider value={{ ...state, logout, refresh }}>{children}</AuthCtx.Provider>
}

export function Welcome({ onDone, initialTab = 'signin', inline = false }: { onDone: () => void; initialTab?: 'signin' | 'signup'; inline?: boolean }) {
  const [tab, setTab] = useState<'signin' | 'signup'>(initialTab)
  const [f, setF] = useState({ first_name: '', last_name: '', email: '', password: '', confirm_password: '' })
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      if (tab === 'signin') await api.post('/api/auth/login', { email: f.email, password: f.password })
      else await api.post('/api/auth/signup', f)
      onDone()
    } catch (x) {
      const msg = (x as Error).message
      setErr(msg.includes('[') ? 'Please check the fields: valid email, password of at least 8 characters, matching confirmation.' : msg)
    } finally { setBusy(false) }
  }
  const guest = async () => { setBusy(true); try { await api.post('/api/auth/guest'); onDone() } finally { setBusy(false) } }

  const form = (
    <div className="card" style={{ padding: 24, width: 400, maxWidth: '100%' }}>
      <div className="seg" style={{ width: '100%', marginBottom: 16 }}>
        <button className={tab === 'signin' ? 'on' : ''} style={{ flex: 1 }} onClick={() => setTab('signin')}>Sign in</button>
        <button className={tab === 'signup' ? 'on' : ''} style={{ flex: 1 }} onClick={() => setTab('signup')}>Create account</button>
      </div>
      <form className="col" style={{ gap: 10 }} onSubmit={submit}>
        {tab === 'signup' && (
          <div className="grid g2" style={{ gap: 10 }}>
            <label className="field">First name<input className="input" value={f.first_name} onChange={set('first_name')} required /></label>
            <label className="field">Last name<input className="input" value={f.last_name} onChange={set('last_name')} required /></label>
          </div>
        )}
        <label className="field">Email<input className="input" type="email" autoComplete="email" value={f.email} onChange={set('email')} required /></label>
        <label className="field">Password<input className="input" type="password" autoComplete={tab === 'signin' ? 'current-password' : 'new-password'} value={f.password} onChange={set('password')} required minLength={tab === 'signup' ? 8 : undefined} /></label>
        {tab === 'signup' && <label className="field">Confirm password<input className="input" type="password" autoComplete="new-password" value={f.confirm_password} onChange={set('confirm_password')} required /></label>}
        {err && <div className="small" style={{ color: 'var(--critical)' }}>{err}</div>}
        <button className="btn primary" style={{ justifyContent: 'center', height: 38 }} disabled={busy}>
          <LockKeyhole size={15} /> {tab === 'signin' ? 'Sign in' : 'Create account'}
        </button>
      </form>
      {!inline && (
        <>
          <div className="row" style={{ margin: '16px 0', gap: 10 }}><div className="divider grow" style={{ margin: 0 }} /><span className="tiny muted">or</span><div className="divider grow" style={{ margin: 0 }} /></div>
          <button className="btn" style={{ width: '100%', justifyContent: 'center', height: 38 }} onClick={guest} disabled={busy}>
            <UserRound size={15} /> Continue as guest
          </button>
          <div className="tiny muted" style={{ marginTop: 8 }}>Guests get a private workspace in this browser. Create an account anytime to keep it and sign in from any device; your guest projects move to the account.</div>
        </>
      )}
    </div>
  )
  if (inline) return form
  return (
    <div style={{ minHeight: '100%', display: 'grid', gridTemplateColumns: 'minmax(0, 1.1fr) minmax(0, 1fr)', background: 'var(--bg)' }}>
      <div style={{ background: 'linear-gradient(135deg, #0b1a33, #17345e 60%, #1f4479)', color: '#fff', padding: '56px 64px', display: 'flex', flexDirection: 'column' }}>
        <div className="row" style={{ gap: 12 }}>
          <div className="brand-mark" style={{ width: 40, height: 40 }}><Leaf size={20} color="#fff" /></div>
          <div><div style={{ fontWeight: 700, fontSize: 20, letterSpacing: '.02em' }}>TerraMind AI</div><div className="brand-sub">Real estate investment</div></div>
        </div>
        <h1 style={{ color: '#fff', fontSize: 38, marginTop: 64, maxWidth: 560, lineHeight: 1.15 }}>AI researches. The engine calculates. You decide.</h1>
        <p style={{ color: '#c9d4e6', fontSize: 16, maxWidth: 560, marginTop: 14 }}>
          Underwrite a development the way a fund does: zoning capacity, design, market, budget, capital stack, monthly cash flows,
          investment committee and asset management, with every assumption sourced and every number computed by a tested engine.
        </p>
        <div className="col" style={{ gap: 12, marginTop: 36, color: '#dfe7f3' }}>
          <div className="row"><Building2 size={18} /> Upload permits, certificates, contracts and Excel models; agents read them for you.</div>
          <div className="row"><ShieldCheck size={18} /> Your projects are private to your account (or to this browser as a guest).</div>
        </div>
        <div style={{ marginTop: 'auto', fontSize: 12, color: '#8fa3c2' }}>Demo projects are fictional. Decision support only, not investment or legal advice.</div>
      </div>
      <div style={{ display: 'grid', placeItems: 'center', padding: 32, position: 'relative' }}>
        <div style={{ position: 'absolute', top: 20, right: 24 }}><LangSwitch /></div>
        {form}
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { RefreshCw, Search } from 'lucide-react'
import { api, notifyProjectChanged, type Json } from '../../api'

/** Runs one research specialist from the UI (limits, cache and token ledger apply server-side). */
export default function ResearchButton({ pid, kind, label, onDone }: { pid: number; kind: string; label: string; onDone?: (r: Json) => void }) {
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [msg, setMsg] = useState<{ tone: 'good' | 'warn' | 'bad'; text: string } | null>(null)

  useEffect(() => {
    if (!busy) return
    const t0 = Date.now()
    const id = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 500)
    return () => clearInterval(id)
  }, [busy])

  const run = async (force: boolean) => {
    setBusy(true); setMsg(null); setElapsed(0)
    try {
      const r = await api.post(`/api/projects/${pid}/research/${kind}`, force ? { force: true } : {})
      if (r.status === 'limit_reached') setMsg({ tone: 'warn', text: `Limit reached: ${r.detail}` })
      else if (r.status === 'duplicate') setMsg({ tone: 'warn', text: r.message })
      else {
        const u = r.turn_usage?.total
        const n = (r.proposals || []).filter((p: Json) => p.key && !p.rejected).length
        setMsg({
          tone: 'good',
          text: r.from_cache ? `Loaded from cache (${r.cached_at?.slice(0, 10)}) — 0 tokens. ${n} proposal(s) to review.`
            : `Done: ${u ? `${(u.input_tokens + u.output_tokens).toLocaleString()} tokens · $${u.cost_usd.toFixed(4)} · ` : ''}${n} proposal(s) to review.`,
        })
      }
      notifyProjectChanged(pid)
      onDone?.(r)
    } catch (e) {
      setMsg({ tone: 'bad', text: (e as Error).message })
    } finally { setBusy(false) }
  }

  return (
    <div className="col" style={{ gap: 6, alignItems: 'flex-end' }}>
      <div className="row" style={{ gap: 6 }}>
        <button className="btn primary sm" disabled={busy} onClick={() => run(false)}>
          {busy ? <span className="spinner" style={{ width: 12, height: 12 }} /> : <Search size={13} />} {busy ? `Researching… ${elapsed}s` : label}
        </button>
        <button className="btn sm" disabled={busy} onClick={() => run(true)} title="Run a fresh web search, ignoring cached results"><RefreshCw size={13} /> Refresh (ignore cache)</button>
      </div>
      {busy && <span className="tiny muted">Web research usually takes 30–60 s.</span>}
      {msg && <span className={`badge ${msg.tone === 'good' ? 'good' : msg.tone === 'warn' ? 'warn' : 'bad'}`} style={{ whiteSpace: 'normal', maxWidth: 420 }}>{msg.text}</span>}
    </div>
  )
}

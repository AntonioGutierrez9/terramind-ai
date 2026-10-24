/* eslint-disable react-refresh/only-export-components */
import { useEffect, useRef, useState } from 'react'
import { ExternalLink, RefreshCw, Search } from 'lucide-react'
import { api, notifyProjectChanged, type Json } from '../../api'
import { AXIS, GRID } from '../../format'
import { useFetch } from '../../state'

/** Shared recharts props (recessive grid, small muted ticks). */
export const gridProps = { stroke: GRID, vertical: false, strokeDasharray: '' }
export const axisProps = { tick: { fill: AXIS, fontSize: 11 }, axisLine: { stroke: GRID }, tickLine: false }

/** Compact axis tick for money: 12.3M / 1.2B. */
export function mTick(v: number): string {
  const a = Math.abs(v)
  const s = v < 0 ? '−' : ''
  if (a >= 1e9) return `${s}${(a / 1e9).toFixed(1)}B`
  if (a >= 1e6) return `${s}${(a / 1e6).toFixed(0)}M`
  if (a >= 1e3) return `${s}${(a / 1e3).toFixed(0)}K`
  return `${s}${a.toFixed(0)}`
}

export function useResearch(pid: number) {
  return useFetch<Record<string, Json>>(`/api/projects/${pid}/research`)
}

/** Button that runs a research specialist (30–60 s), with elapsed timer, cost and error handling. */
export function ResearchButton({ pid, kind, label, hasData, onDone }: { pid: number; kind: string; label: string; hasData: boolean; onDone: () => void }) {
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [msg, setMsg] = useState<{ tone: 'good' | 'bad' | 'warn'; text: string } | null>(null)
  const timer = useRef<number | null>(null)
  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current) }, [])
  const run = async (force: boolean) => {
    setBusy(true); setMsg(null); setElapsed(0)
    const t0 = Date.now()
    timer.current = window.setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 500)
    try {
      const r = await api.post(`/api/projects/${pid}/research/${kind}`, { force })
      if (r.status === 'limit_reached') setMsg({ tone: 'warn', text: `Limit reached: ${r.detail}` })
      else if (r.status !== 'ok') setMsg({ tone: 'bad', text: r.message || 'Research failed.' })
      else {
        const cost = r.turn_usage?.total?.cost_usd
        setMsg({ tone: 'good', text: r.from_cache ? `Loaded from cache (${String(r.cached_at).slice(0, 10)}) · $0.0000` : `Done in ${Math.round((Date.now() - t0) / 1000)} s · $${(cost ?? 0).toFixed(4)} · ${r.proposals?.length ?? 0} proposals for your approval` })
      }
      onDone()
      notifyProjectChanged(pid)
    } catch (e) {
      setMsg({ tone: 'bad', text: (e as Error).message })
    } finally {
      if (timer.current) window.clearInterval(timer.current)
      setBusy(false)
    }
  }
  return (
    <div className="col" style={{ gap: 6, alignItems: 'flex-end' }}>
      <div className="row" style={{ gap: 6 }}>
        {busy && <span className="small muted"><span className="spinner" style={{ width: 12, height: 12, verticalAlign: -2 }} /> researching… {elapsed}s</span>}
        <button className="btn primary sm" disabled={busy} onClick={() => run(false)}><Search size={13} /> {label}</button>
        {hasData && <button className="btn sm" disabled={busy} onClick={() => run(true)} title="Ignore cache and search again"><RefreshCw size={13} /> Refresh</button>}
      </div>
      {msg && <div className="tiny" style={{ color: msg.tone === 'good' ? 'var(--good-text)' : msg.tone === 'warn' ? 'var(--warning-text)' : 'var(--critical)' }}>{msg.text}</div>}
    </div>
  )
}

export function SourceLink({ url, title }: { url?: string | null; title?: string | null }) {
  if (!url) return <span className="muted">—</span>
  let host = url
  try { host = new URL(url).hostname.replace('www.', '') } catch { /* keep */ }
  return <a href={url} target="_blank" rel="noreferrer" title={title || url}><ExternalLink size={11} /> {host}</a>
}

export function VerifBadge({ v }: { v?: string | null }) {
  if (!v) return <span className="muted">—</span>
  const good = ['verified', 'published_rate', 'published_benchmark', 'published'].includes(v)
  const bad = v === 'not_found'
  return <span className={`badge ${good ? 'good' : bad ? 'bad' : 'warn'}`}>{v.replace(/_/g, ' ')}</span>
}

export function ResearchMeta({ r }: { r: Json }) {
  if (!r) return null
  return (
    <div className="tiny muted">
      Researched {String(r.created_at).slice(0, 16).replace('T', ' ')} UTC{r.from_cache ? ' · from cache / captured snapshot' : ''}
      {r.payload?.suspicious_fields?.length > 0 && <span style={{ color: 'var(--critical)' }}> · instruction-like text removed from {r.payload.suspicious_fields.length} field(s)</span>}
    </div>
  )
}

/** Group months into project years (Y0 = month 0, Y1 = months 1–12…). */
export function byYear(months: Json[], keys: string[]): Json[] {
  const out: Record<number, Json> = {}
  for (const m of months) {
    const y = m.month === 0 ? 0 : Math.ceil(m.month / 12)
    out[y] = out[y] || { year: y }
    for (const k of keys) out[y][k] = (out[y][k] || 0) + (m[k] || 0)
  }
  return Object.values(out)
}

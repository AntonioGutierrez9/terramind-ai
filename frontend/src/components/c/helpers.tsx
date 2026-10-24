/* eslint-disable react-refresh/only-export-components */
import { useEffect, useState } from 'react'
import { money, multiple, num, pct } from '../../format'

export const METRIC_LABELS: Record<string, string> = {
  total_cost: 'Total cost (incl. financing)', tdc: 'Total development cost', gdv: 'Gross development value', revenue: 'Revenue',
  profit: 'Development profit', net_margin: 'Net margin', gross_margin: 'Gross margin', profit_on_cost: 'Profit on cost',
  project_irr: 'Project IRR (unlevered)', equity_irr: 'Equity IRR', moic: 'Equity multiple (MOIC)', npv: 'NPV (unlevered)',
  equity_npv: 'Equity NPV', peak_equity: 'Peak equity', peak_funding: 'Peak funding requirement', peak_debt: 'Peak debt',
  duration_months: 'Duration (months)', funding_gap: 'Funding gap', ltc: 'Loan-to-cost', ltv: 'Loan-to-value', dscr: 'DSCR',
  investor_irr: 'Investor IRR', sponsor_irr: 'Sponsor IRR', units: 'Units', financing_cost: 'Financing cost',
  yield_on_cost: 'Yield on cost', cash_on_cash: 'Cash-on-cash', stabilized_noi: 'Stabilized NOI',
}

export function metricKind(k: string): 'pct' | 'x' | 'num' | 'money' {
  if (/irr|margin|on_cost|ltc|ltv|yield|cash_on_cash/.test(k)) return 'pct'
  if (k === 'moic' || k.endsWith('_moic') || k === 'dscr') return 'x'
  if (/months|units|month/.test(k)) return 'num'
  return 'money'
}

export function fmtMetric(k: string, v: number | null | undefined, cur = 'MXN'): string {
  const kind = metricKind(k)
  if (kind === 'pct') return pct(v)
  if (kind === 'x') return multiple(v)
  if (kind === 'num') return num(v)
  return money(v, cur)
}

export function fmtMetricDelta(k: string, a: number | null | undefined, b: number | null | undefined, cur = 'MXN'): string {
  if (a == null || b == null) return '—'
  const d = b - a
  const kind = metricKind(k)
  const s = d > 0 ? '+' : d < 0 ? '−' : ''
  if (kind === 'pct') return `${s}${Math.abs(d * 100).toFixed(1)} pts`
  if (kind === 'x') return `${s}${Math.abs(d).toFixed(2)}x`
  if (kind === 'num') return `${s}${num(Math.abs(d))}`
  return `${s}${money(Math.abs(d), cur)}`
}

export function shortDate(s?: string | null): string {
  if (!s) return '—'
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function shortVal(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : v.toLocaleString('en-US', { maximumFractionDigits: 2 })
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  if (Array.isArray(v)) return `[${v.length} items]`
  if (typeof v === 'object') return '{…}'
  return String(v)
}

export function ActorBadge({ actor }: { actor: string }) {
  const cls = actor === 'user' ? 'user' : actor.startsWith('chatbot') ? 'chatbot' : actor.startsWith('agent') ? 'researched' : 'default'
  return <span className={`badge ${cls}`}>{actor}</span>
}

/** Live seconds counter shown while a slow LLM call runs. */
export function Elapsed() {
  const [start] = useState(() => Date.now())
  const [, tick] = useState(0)
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 1000); return () => clearInterval(t) }, [])
  return <span className="num">{Math.round((Date.now() - start) / 1000)}s</span>
}

export function UsageLine({ u }: { u: { total?: { input_tokens: number; cached_tokens: number; output_tokens: number; cost_usd: number }; seconds?: number } | null | undefined }) {
  if (!u?.total) return null
  const t = u.total
  return (
    <span className="tiny muted">
      Measured: {num(t.input_tokens)} input ({num(t.cached_tokens)} cached) · {num(t.output_tokens)} output · ${t.cost_usd.toFixed(4)}{u.seconds ? ` · ${u.seconds}s` : ''}
    </span>
  )
}

import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, Bot, CheckCircle2, CircleAlert, Plus, Trash2 } from 'lucide-react'
import { useProject } from '../../components/Layout'
import { Callout, Card, ChartTip, Kpi, Legend, Loading, ModelIncomplete, PageHead } from '../../components/ui'
import { Elapsed, METRIC_LABELS, UsageLine, fmtMetric, fmtMetricDelta } from '../../components/c/helpers'
import { api, notifyProjectChanged, type Json } from '../../api'
import { AXIS, GRID, SERIES, money, num, pct } from '../../format'
import { useFetch } from '../../state'

const FIELDS = [
  { k: 'cost', label: 'Cost (period)' }, { k: 'units_sold', label: 'Units sold' }, { k: 'avg_price_per_area', label: 'Avg price / m²' },
  { k: 'collections', label: 'Collections' }, { k: 'debt_balance', label: 'Debt balance (end)' }, { k: 'progress_pct', label: 'Progress % (end)' },
]

export default function Asset() {
  const { data } = useProject()
  const pid = data.project.id
  const cur = data.project.profile.currency || 'MXN'
  const { data: am, loading, reload } = useFetch<Json>(`/api/projects/${pid}/asset`)
  const months: Json[] = data.results?.months || []

  const charts = useMemo(() => {
    if (!am || am.status !== 'ok') return null
    const acts: Json[] = am.actuals || []
    const asOf = am.as_of_month
    const horizon = Math.min(months.length - 1, Math.max(asOf + 12, asOf))
    const byM = Object.fromEntries(acts.map((a) => [a.month, a]))
    let cp = 0, ca = 0, up = 0, ua = 0
    const rows = []
    for (let t = 0; t <= horizon; t++) {
      const m = months[t]
      if (!m) break
      cp += m.outflow - m.land_acq
      up += m.units_sold || 0
      const a = byM[t]
      if (t <= asOf) { ca += a?.cost || 0; ua += a?.units_sold || 0 }
      rows.push({
        month: t, planCost: cp, actualCost: t <= asOf ? ca : null, planUnits: up, actualUnits: t <= asOf ? ua : null,
        planDebt: m.senior_balance + m.mezz_balance, actualDebt: a?.debt_balance ?? null,
      })
    }
    return rows
  }, [am, months])

  const setStatus = async (body: Json) => { await api.post(`/api/projects/${pid}/status`, body); notifyProjectChanged(pid) }

  return (
    <>
      <PageHead eyebrow="Step 9" title="Asset management"
        actions={<>
          <button className="btn" onClick={() => setStatus({ status: 'approved' })}>Mark approved</button>
          <button className="btn primary" onClick={() => setStatus({ status: 'portfolio', in_portfolio: true })} disabled={data.project.in_portfolio}>
            {data.project.in_portfolio ? 'In portfolio' : 'Add to portfolio'}
          </button>
        </>}>
        Compare actual results with the original underwriting. Recorded actuals drive a deterministic reforecast: the full model is re-run with cost, sales pace, price and schedule adjusted to what actually happened.
      </PageHead>
      <ModelIncomplete results={data.results} />
      {loading && !am ? <Loading /> : !am ? null : (
        <div className="col" style={{ gap: 16 }}>
          {am.status === 'ok' && <AlertPanel alerts={am.alerts} />}
          {am.status === 'no_actuals' && <Callout>No actuals recorded yet. Add monthly actuals below to start monitoring this project.</Callout>}
          {am.status === 'ok' && (
            <>
              <div className="grid g3">
                <Kpi label="Actuals as of" value={`Month ${am.as_of_month}`} sub={`${am.actuals.length} monthly records`} />
                <Kpi label="Cost to date vs plan" value={pct(am.variances.cost)} sub={`${money(am.actual_to_date.cost, cur)} vs ${money(am.plan_to_date.cost, cur)}`}
                  tone={am.variances.cost > 0.05 ? 'bad' : am.variances.cost > 0 ? 'warn' : 'good'} />
                <Kpi label="Units sold vs plan" value={`${num(am.actual_to_date.units_sold)} / ${num(am.plan_to_date.units_sold)}`}
                  sub={am.variances.units_sold != null ? `${pct(am.variances.units_sold)} vs plan` : undefined}
                  tone={am.variances.units_sold != null && am.variances.units_sold < -0.15 ? 'bad' : undefined} />
                <Kpi label="Construction progress" value={`${num(am.actual_to_date.progress_pct, 1)}%`} sub={`plan ${num(am.plan_to_date.progress_pct, 1)}%`}
                  tone={(am.actual_to_date.progress_pct ?? 0) < am.plan_to_date.progress_pct - 2 ? 'warn' : undefined} />
                <Kpi label="Debt balance vs plan" value={money(am.actual_to_date.debt_balance, cur)} sub={`plan ${money(am.plan_to_date.debt_balance, cur)}`} />
                <Kpi label="Equity IRR: underwriting → updated" value={`${pct(am.underwriting?.equity_irr)} → ${pct(am.updated?.equity_irr)}`}
                  sub={fmtMetricDelta('equity_irr', am.underwriting?.equity_irr, am.updated?.equity_irr)}
                  tone={am.updated && am.underwriting && am.updated.equity_irr < am.underwriting.equity_irr ? 'bad' : 'good'} />
              </div>

              <div className="grid g2">
                <Card title="Underwriting vs updated forecast" sub="Both columns come from the deterministic engine">
                  <table className="t">
                    <thead><tr><th>Metric</th><th className="num">Underwriting</th><th className="num">Updated forecast</th><th className="num">Change</th></tr></thead>
                    <tbody>{am.comparison.map((c: Json) => (
                      <tr key={c.metric}><td>{METRIC_LABELS[c.metric] || c.metric}</td>
                        <td className="num">{fmtMetric(c.metric, c.underwriting, cur)}</td><td className="num">{fmtMetric(c.metric, c.updated, cur)}</td>
                        <td className="num">{fmtMetricDelta(c.metric, c.underwriting, c.updated, cur)}</td></tr>
                    ))}</tbody>
                  </table>
                </Card>
                <Card title="Reforecast drivers" sub="What changed and how it entered the model">
                  {am.drivers.length === 0 ? <div className="small muted">Actuals are on plan; no adjustments.</div> : (
                    <table className="t"><thead><tr><th>Driver</th><th className="num">Factor</th><th>Evidence</th></tr></thead>
                      <tbody>{am.drivers.map((d: Json) => <tr key={d.driver}><td><b>{d.driver}</b></td><td className="num">{d.factor == null ? '—' : `${d.factor.toFixed(3)}×`}</td><td className="small">{d.detail}</td></tr>)}</tbody>
                    </table>
                  )}
                  <div className="tiny muted" style={{ marginTop: 10 }}>
                    Method: cost factor = actual development cost to date ÷ underwritten cost to date (applied to hard costs); sales pace = actual net units per month since sales started;
                    price factor = achieved price ÷ underwritten effective price; schedule delay = progress gap × construction months. The whole model is then re-run, so IRR, MOIC, covenants and funding needs update together.
                  </div>
                  {Object.keys(am.overrides || {}).length > 0 && (
                    <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
                      {Object.entries(am.overrides).map(([k, v]) => <span key={k} className="badge">{k} → {typeof v === 'number' ? num(v, v % 1 ? 2 : 0) : String(v)}</span>)}
                    </div>
                  )}
                </Card>
              </div>

              {charts && (
                <div className="grid g3">
                  <MiniLine title="Cumulative development cost" sub="Excludes land" rows={charts} plan="planCost" actual="actualCost" fmt={(v) => money(v, cur)} tick={(v) => `${(v / 1e6).toFixed(0)}M`} />
                  <MiniLine title="Cumulative units sold" rows={charts} plan="planUnits" actual="actualUnits" fmt={(v) => num(v, 1)} tick={(v) => num(v)} />
                  <MiniLine title="Debt balance" rows={charts} plan="planDebt" actual="actualDebt" fmt={(v) => money(v, cur)} tick={(v) => `${(v / 1e6).toFixed(0)}M`} />
                </div>
              )}
              <Commentary pid={pid} />
            </>
          )}
          <ActualsEditor pid={pid} actuals={am.actuals || []} onChange={() => { reload(); notifyProjectChanged(pid) }} cur={cur} />
        </div>
      )}
    </>
  )
}

function AlertPanel({ alerts }: { alerts: Json[] }) {
  if (!alerts?.length) return <Callout tone="good">No early-warning alerts: the project is tracking its underwriting.</Callout>
  return (
    <Card title="Early-warning alerts" sub={`${alerts.filter((a) => a.level === 'red').length} critical · ${alerts.filter((a) => a.level === 'amber').length} watch`}>
      <div className="col" style={{ gap: 6 }}>
        {alerts.map((a, i) => (
          <div key={i} className={`callout ${a.level === 'red' ? 'bad' : 'warn'}`} style={{ padding: '8px 12px' }}>
            {a.level === 'red' ? <CircleAlert size={16} style={{ flexShrink: 0 }} /> : <AlertTriangle size={16} style={{ flexShrink: 0 }} />}
            <div><b>{a.level === 'red' ? 'Critical' : 'Watch'} · {a.area}:</b> {a.message}</div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function MiniLine({ title, sub, rows, plan, actual, fmt, tick }: { title: string; sub?: string; rows: Json[]; plan: string; actual: string; fmt: (v: number) => string; tick: (v: number) => string }) {
  return (
    <Card title={title} sub={sub}>
      <ResponsiveContainer width="100%" height={210}>
        <LineChart data={rows} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="month" stroke={AXIS} fontSize={11} tickFormatter={(m) => `M${m}`} />
          <YAxis stroke={AXIS} fontSize={11} tickFormatter={tick} width={48} />
          <Tooltip content={<ChartTip fmt={(v) => fmt(v)} labelFmt={(l) => `Month ${l}`} />} />
          <Line type="monotone" dataKey={plan} name="Underwriting" stroke={SERIES[0]} strokeWidth={2} dot={false} strokeDasharray="5 4" />
          <Line type="monotone" dataKey={actual} name="Actual" stroke={SERIES[1]} strokeWidth={2} dot={{ r: 3 }} connectNulls={false} />
        </LineChart>
      </ResponsiveContainer>
      <Legend items={[{ label: 'Underwriting (dashed)', color: SERIES[0] }, { label: 'Actual', color: SERIES[1] }]} />
    </Card>
  )
}

function Commentary({ pid }: { pid: number }) {
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<Json>(null)
  const [err, setErr] = useState<string | null>(null)
  const run = async () => {
    setBusy(true); setErr(null)
    try { setRes(await api.post(`/api/projects/${pid}/asset/commentary`)) } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <Card title="Asset Management agent commentary" sub="The agent explains the deterministic variances above; it does not compute numbers."
      actions={<button className="btn" onClick={run} disabled={busy}>{busy ? <><span className="spinner" /> Analyzing… <Elapsed /></> : <><Bot size={14} /> Generate AI commentary</>}</button>}>
      {err && <Callout tone="bad">{err}</Callout>}
      {!res && !err && <div className="small muted">Generate a short explanation of what drove the change in returns and recommended actions.</div>}
      {res && (
        <div className="col">
          <div style={{ fontWeight: 620, fontSize: 15 }}>{res.headline}</div>
          <div className="grid g2">
            <div><h3 style={{ marginBottom: 6 }}>Drivers</h3><ul style={{ margin: 0, paddingLeft: 18 }}>{res.drivers?.map((d: string, i: number) => <li key={i} className="small" style={{ marginBottom: 4 }}>{d}</li>)}</ul></div>
            <div><h3 style={{ marginBottom: 6 }}>Recommended actions</h3><ul style={{ margin: 0, paddingLeft: 18 }}>{res.actions?.map((d: string, i: number) => <li key={i} className="small" style={{ marginBottom: 4 }}><CheckCircle2 size={12} color="var(--good)" /> {d}</li>)}</ul></div>
          </div>
          <UsageLine u={res.turn_usage} />
        </div>
      )}
    </Card>
  )
}

function ActualsEditor({ pid, actuals, onChange, cur }: { pid: number; actuals: Json[]; onChange: () => void; cur: string }) {
  const next = actuals.length ? Math.max(...actuals.map((a) => a.month)) + 1 : 1
  const [form, setForm] = useState<Record<string, string>>({ month: String(next) })
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const add = async () => {
    setBusy(true); setErr(null)
    try {
      const body: Json = { month: Number(form.month) }
      for (const f of FIELDS) if (form[f.k] !== undefined && form[f.k] !== '') body[f.k] = Number(form[f.k])
      await api.post(`/api/projects/${pid}/actuals`, body)
      setForm({ month: String(Number(form.month) + 1) })
      onChange()
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const del = async (m: number) => { await api.del(`/api/projects/${pid}/actuals/${m}`); onChange() }
  return (
    <Card title="Monthly actuals" sub={`Record actual results (${cur}). Cost, units and collections are per-month amounts; debt balance and progress are end-of-month levels. Saving re-runs the reforecast.`}>
      <div className="table-wrap" style={{ maxHeight: 360 }}>
        <table className="t">
          <thead><tr><th className="num">Month</th>{FIELDS.map((f) => <th key={f.k} className="num">{f.label}</th>)}<th /></tr></thead>
          <tbody>
            {actuals.map((a) => (
              <tr key={a.month}><td className="num">M{a.month}</td>
                {FIELDS.map((f) => <td key={f.k} className="num">{a[f.k] == null ? '—' : f.k === 'progress_pct' ? `${num(a[f.k], 1)}%` : num(a[f.k], f.k === 'units_sold' ? 1 : 0)}</td>)}
                <td><button className="btn ghost sm danger" onClick={() => del(a.month)} title="Delete"><Trash2 size={13} /></button></td></tr>
            ))}
            <tr>
              <td><input className="input" style={{ width: 64 }} value={form.month ?? ''} onChange={(e) => setForm({ ...form, month: e.target.value })} /></td>
              {FIELDS.map((f) => <td key={f.k}><input className="input" style={{ minWidth: 90 }} value={form[f.k] ?? ''} placeholder="—" onChange={(e) => setForm({ ...form, [f.k]: e.target.value })} /></td>)}
              <td><button className="btn primary sm" onClick={add} disabled={busy}><Plus size={13} /> Save</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      {err && <div style={{ marginTop: 8 }}><Callout tone="bad">{err}</Callout></div>}
    </Card>
  )
}

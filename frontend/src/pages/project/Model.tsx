import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Play, Plus, Save, Target, Trash2 } from 'lucide-react'
import { api, notifyProjectChanged, type Json } from '../../api'
import { useProject } from '../../components/Layout'
import { Callout, Card, ChartTip, Kpi, Legend, Loading, ModelIncomplete, PageHead } from '../../components/ui'
import { axisProps, byYear, gridProps, mTick } from '../../components/b/common'
import { SERIES, fmtValue, money, multiple, num, pct } from '../../format'
import { useFetch, useMeta } from '../../state'

const PCT_METRICS = new Set(['equity_irr', 'project_irr', 'net_margin', 'profit_on_cost'])

export default function Model() {
  const { data } = useProject()
  const p = data.project
  const cur = p.profile.currency || 'MXN'
  const res = data.results
  const ok = res?.status === 'ok'
  const analysis = useFetch<Json>(ok ? `/api/projects/${p.id}/analysis` : null, [p.updated_at])

  return (
    <div className="col" style={{ gap: 16 }}>
      <PageHead eyebrow="Step 6 · Underwriting" title="Financial Model"
        actions={p.profile.demo ? <span className="badge demo">Fictional demo inputs</span> : undefined}>
        Monthly cash-flow model computed by TerraMind's deterministic Python engine. The AI never performs this arithmetic.
      </PageHead>
      <ModelIncomplete results={res} />
      {ok && <Headline res={res} cur={cur} mode={data.mode} />}
      {ok && (res.warnings.length > 0 || res.compliance.length > 0) && (
        <div className="col" style={{ gap: 8 }}>
          {res.compliance.length > 0 && <Callout tone="bad"><b>Potentially noncompliant scenario.</b> {res.compliance.map((c: Json) => c.detail).join(' · ')}</Callout>}
          {res.warnings.map((w: string, i: number) => <Callout key={i} tone="warn">{w}</Callout>)}
        </div>
      )}
      {ok && <CashFlowCharts months={res.months} cur={cur} />}
      {ok && <AnnualTable months={res.months} cur={cur} />}
      {ok && (analysis.loading && !analysis.data ? <Loading label="Running scenarios and sensitivities…" /> : analysis.data?.status === 'ok' && (
        <>
          <Scenarios sc={analysis.data.scenarios} cur={cur} pid={p.id} reload={analysis.reload} />
          <div className="grid g2">
            <Tornado t={analysis.data.tornado} />
            <Heatmap h={analysis.data.heatmap} hurdle={(res.metrics.equity_discount_rate_pct ?? 18) / 100} />
          </div>
          <Breakeven b={analysis.data.breakeven} cur={cur} mode={data.mode} />
        </>
      ))}
      {ok && (
        <div className="grid g2">
          <ScenarioBuilder pid={p.id} base={res.metrics} cur={cur} onSaved={analysis.reload} />
          <Solver pid={p.id} cur={cur} assumptions={p.assumptions} />
        </div>
      )}
    </div>
  )
}

function Headline({ res, cur, mode }: { res: Json; cur: string; mode: string }) {
  const m = res.metrics
  const hurdle = (m.equity_discount_rate_pct ?? 18) / 100
  const tone = m.equity_irr == null ? undefined : m.equity_irr >= hurdle ? 'good' : 'bad'
  return (
    <>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(7, minmax(0, 1fr))' }}>
        <Kpi hero label="Equity IRR" value={pct(m.equity_irr)} tone={tone} sub={`hurdle ${pct(hurdle, 0)}`} />
        <Kpi hero label="Project IRR" value={pct(m.project_irr)} sub="unlevered" />
        <Kpi hero label="Equity multiple" value={multiple(m.moic)} sub="MOIC" />
        <Kpi hero label="Development profit" value={money(m.profit, cur)} tone={m.profit < 0 ? 'bad' : undefined} />
        <Kpi hero label="Net margin" value={pct(m.net_margin)} sub={`gross ${pct(m.gross_margin)}`} />
        <Kpi hero label="NPV" value={money(m.npv, cur)} sub={`@ ${num(m.discount_rate_pct, 1)}% unlevered`} tone={m.npv < 0 ? 'bad' : undefined} />
        <Kpi hero label="Peak equity" value={money(m.peak_equity, cur)} sub={`peak funding ${money(m.peak_funding, cur)}`} />
      </div>
      <div className="grid" style={{ gridTemplateColumns: `repeat(${mode === 'rent' ? 7 : 6}, minmax(0, 1fr))` }}>
        <Kpi label={mode === 'rent' ? 'Exit value' : 'GDV'} value={money(m.gdv, cur)} />
        <Kpi label="Total cost" value={money(m.total_cost, cur)} sub="incl. financing" />
        <Kpi label="Profit on cost" value={pct(m.profit_on_cost)} />
        <Kpi label="Duration" value={`${m.duration_months} mo`} sub={`delivery M${m.delivery_month}`} />
        <Kpi label="Investor IRR" value={pct(m.investor_irr)} sub={`MOIC ${multiple(m.investor_moic)}`} />
        <Kpi label="Sponsor IRR" value={pct(m.sponsor_irr)} sub={`MOIC ${multiple(m.sponsor_moic)}`} />
        {mode === 'rent' && <Kpi label="DSCR / CoC / YoC" value={m.dscr != null ? `${m.dscr.toFixed(2)}x` : '—'} sub={`cash-on-cash ${pct(m.cash_on_cash)} · YoC ${pct(m.yield_on_cost, 2)}`} />}
      </div>
    </>
  )
}

function CashFlowCharts({ months, cur }: { months: Json[]; cur: string }) {
  const rows = useMemo(() => {
    let cu = 0, cl = 0
    return months.map((x) => { cu += x.unlevered_cf; cl += x.levered_cf; return { month: x.month, inflow: x.inflow, outflow: -x.outflow, cum: cu, cumLev: cl } })
  }, [months])
  return (
    <div className="grid g2">
      <Card title="Monthly cash flow (unlevered)" sub="Inflows above the axis, development costs below">
        <Legend items={[{ label: 'Inflows', color: SERIES[0] }, { label: 'Outflows', color: SERIES[1] }]} />
        <div style={{ height: 260, marginTop: 6 }}>
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} stackOffset="sign">
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={mTick} />
              <ReferenceLine y={0} stroke="#cfd6e1" />
              <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => money(v, cur)} />} />
              <Bar dataKey="inflow" name="Inflows" stackId="c" fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={12} />
              <Bar dataKey="outflow" name="Outflows" stackId="c" fill={SERIES[1]} radius={[0, 0, 4, 4]} maxBarSize={12} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="Cumulative cash flow" sub="Unlevered (project) vs levered (equity); the trough is the peak funding need">
        <Legend items={[{ label: 'Unlevered', color: SERIES[0] }, { label: 'Levered (equity)', color: SERIES[2] }]} />
        <div style={{ height: 260, marginTop: 6 }}>
          <ResponsiveContainer>
            <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={mTick} />
              <ReferenceLine y={0} stroke="#cfd6e1" />
              <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => money(v, cur)} />} />
              <Line dataKey="cum" name="Unlevered" stroke={SERIES[0]} strokeWidth={2} dot={false} />
              <Line dataKey="cumLev" name="Levered (equity)" stroke={SERIES[2]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  )
}

function AnnualTable({ months, cur }: { months: Json[]; cur: string }) {
  const keys = ['inflow', 'outflow', 'unlevered_cf', 'interest', 'equity_contrib', 'equity_dist', 'levered_cf']
  const rows = byYear(months, keys)
  const tot = Object.fromEntries(keys.map((k) => [k, rows.reduce((s, r) => s + r[k], 0)]))
  const cols = [['inflow', 'Inflows'], ['outflow', 'Costs (excl. fin.)'], ['unlevered_cf', 'Unlevered CF'], ['interest', 'Interest'],
    ['equity_contrib', 'Equity in'], ['equity_dist', 'Equity out'], ['levered_cf', 'Levered CF']]
  return (
    <Card title="Annual cash-flow summary" sub={`${cur} millions · Y0 = closing month, Y1 = months 1–12`}>
      <div className="table-wrap">
        <table className="t">
          <thead><tr><th>Year</th>{cols.map(([k, l]) => <th key={k} className="num">{l}</th>)}</tr></thead>
          <tbody>
            {rows.map((r) => <tr key={r.year}><td>Y{r.year}</td>{cols.map(([k]) => <td key={k} className="num" style={{ color: r[k] < -0.5 ? 'var(--critical)' : undefined }}>{num(r[k] / 1e6, 1)}</td>)}</tr>)}
            <tr className="total"><td>Total</td>{cols.map(([k]) => <td key={k} className="num">{num(tot[k] / 1e6, 1)}</td>)}</tr>
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function describeChanges(changes: Json[], reg: Record<string, Json>) {
  if (!changes?.length) return 'Current assumptions'
  return changes.map((c) => {
    const lbl = reg[c.key]?.label ?? c.key
    if (c.op === 'pct') return `${lbl} ${c.value > 0 ? '+' : ''}${c.value}%`
    if (c.op === 'add') return `${lbl} ${c.value > 0 ? '+' : ''}${c.value}`
    return `${lbl} = ${c.value}`
  }).join(' · ')
}

function Scenarios({ sc, cur, pid, reload }: { sc: Json[]; cur: string; pid: number; reload: () => void }) {
  const meta = useMeta()
  const variants = useFetch<Json[]>(`/api/projects/${pid}/variants`)
  const savedByName = new Map((variants.data || []).filter((v) => v.kind === 'scenario').map((v) => [v.name, v.id]))
  const del = async (id: number) => { await api.del(`/api/variants/${id}`); variants.reload(); reload() }
  return (
    <Card title="Scenario analysis" sub="Each scenario re-runs the entire model with its changes">
      <div className="table-wrap">
        <table className="t">
          <thead><tr><th>Scenario</th><th>Changes vs current</th><th className="num">Equity IRR</th><th className="num">Project IRR</th><th className="num">Profit</th>
            <th className="num">Net margin</th><th className="num">MOIC</th><th className="num">Peak equity</th><th /></tr></thead>
          <tbody>{sc.map((s, i) => {
            const m = s.metrics || {}
            const vid = i >= 3 ? savedByName.get(s.name) : undefined
            return (
              <tr key={s.name + i}>
                <td style={{ fontWeight: 600 }}>{s.name}</td>
                <td className="small muted" style={{ maxWidth: 360 }}>{describeChanges(s.changes, meta.registry)}</td>
                {s.status === 'ok' ? <>
                  <td className="num" style={{ fontWeight: 600 }}>{pct(m.equity_irr)}</td><td className="num">{pct(m.project_irr)}</td>
                  <td className="num" style={{ color: m.profit < 0 ? 'var(--critical)' : undefined }}>{money(m.profit, cur)}</td><td className="num">{pct(m.net_margin)}</td>
                  <td className="num">{multiple(m.moic)}</td><td className="num">{money(m.peak_equity, cur)}</td>
                </> : <td colSpan={6} className="small" style={{ color: 'var(--critical)' }}>{s.error || `Model ${s.status}`}</td>}
                <td>{vid && <button className="btn ghost sm" title="Delete saved scenario" onClick={() => del(vid)}><Trash2 size={13} /></button>}</td>
              </tr>
            )
          })}</tbody>
        </table>
      </div>
    </Card>
  )
}

function Tornado({ t }: { t: Json }) {
  if (!t || t.status !== 'ok') return null
  const base = t.base ?? 0
  const vals = t.bars.flatMap((b: Json) => [b.low_input, b.high_input]).filter((v: Json) => v != null)
  const span = Math.max(...vals.map((v: number) => Math.abs(v - base)), 0.01)
  const x = (v: number) => 50 + ((v - base) / span) * 46
  return (
    <Card title="Tornado — equity IRR sensitivity" sub={`Base ${pct(base)} · each driver shocked down and up`}>
      <Legend items={[{ label: 'Driver decreased (−)', color: SERIES[1] }, { label: 'Driver increased (+)', color: SERIES[0] }]} />
      <div className="col" style={{ gap: 9, marginTop: 10 }}>
        {t.bars.map((b: Json) => (
          <div key={b.driver} className="row" style={{ gap: 10 }}>
            <div className="small" style={{ width: 150, color: 'var(--text-2)' }}>{b.driver}</div>
            <div className="grow" style={{ position: 'relative', height: 20 }}>
              <div style={{ position: 'absolute', left: '50%', top: -3, bottom: -3, width: 1, background: '#9aa4b2' }} />
              {[['low_input', SERIES[1], '−'], ['high_input', SERIES[0], '+']].map(([k, color, sgn]) => {
                const v = b[k as string]
                if (v == null) return null
                const a = Math.min(50, x(v)), w = Math.abs(x(v) - 50)
                return <div key={k as string} title={`${b.driver} (${sgn}): ${pct(v)}`} style={{ position: 'absolute', left: `${a}%`, width: `${Math.max(w, 0.4)}%`, top: 2, bottom: 2,
                  background: color as string, borderRadius: x(v) < 50 ? '4px 0 0 4px' : '0 4px 4px 0', opacity: 0.95 }} />
              })}
            </div>
            <div className="tiny num muted" style={{ width: 92, textAlign: 'right' }}>{pct(b.low_input)} / {pct(b.high_input)}</div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function mix(a: string, b: string, t: number) {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16)), pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16))
  return `rgb(${pa.map((v, i) => Math.round(v + (pb[i] - v) * t)).join(',')})`
}

function Heatmap({ h, hurdle }: { h: Json; hurdle: number }) {
  if (!h) return null
  const all = h.grid.flat().filter((v: Json) => v != null) as number[]
  const span = Math.max(...all.map((v) => Math.abs(v - hurdle)), 0.01)
  const color = (v: number | null) => {
    if (v == null) return { bg: '#f8fafc', fg: 'var(--text-3)' }
    const t = Math.min(Math.abs(v - hurdle) / span, 1)
    const bg = v >= hurdle ? mix('#f0efec', '#184f95', t) : mix('#f0efec', '#c22f2f', t)
    return { bg, fg: t > 0.55 ? '#fff' : 'var(--text)' }
  }
  return (
    <Card title="Equity IRR heatmap" sub={`${h.x_label} (columns) × ${h.y_label} (rows) · blue above / red below the ${pct(hurdle, 0)} hurdle`}>
      <table className="t" style={{ tableLayout: 'fixed' }}>
        <thead><tr><th style={{ width: 110 }}>Cost ↓ / Price →</th>{h.x_steps.map((s: number) => <th key={s} className="num">{s > 0 ? '+' : ''}{s}%</th>)}</tr></thead>
        <tbody>{h.grid.map((row: (number | null)[], i: number) => (
          <tr key={i}><td className="small" style={{ fontWeight: 600 }}>{h.y_steps[i] > 0 ? '+' : ''}{h.y_steps[i]}%</td>
            {row.map((v, j) => { const c = color(v); const base = h.x_steps[j] === 0 && h.y_steps[i] === 0
              return <td key={j} className="num" title={`Price ${h.x_steps[j]}%, cost ${h.y_steps[i]}%: ${pct(v)}`}
                style={{ background: c.bg, color: c.fg, fontWeight: base ? 700 : 500, outline: base ? '2px solid #0b1a33' : undefined, outlineOffset: -2, borderBottom: '2px solid #fff' }}>{pct(v)}</td> })}
          </tr>
        ))}</tbody>
      </table>
    </Card>
  )
}

function Breakeven({ b, cur, mode }: { b: Json; cur: string; mode: string }) {
  if (!b) return null
  const unit = mode === 'sale' ? '/ m²' : '/ m² / month'
  const item = (r: Json, label: string, fmt: (v: number) => string, cmp?: number) => (
    <div className="card kpi flat">
      <div className="label">{label}</div>
      {r?.status === 'ok' ? <>
        <div className="value">{fmt(r.value)}</div>
        <div className="sub">current {cmp != null ? fmt(cmp) : '—'}{cmp ? ` · ${(((r.value / cmp) - 1) * 100).toFixed(1)}%` : ''}</div>
      </> : <div className="sub" style={{ marginTop: 6 }}>{r?.message || 'Not reachable in the search range'}</div>}
    </div>
  )
  return (
    <Card title="Break-even analysis" sub="Solved by bisection on the full model">
      <div className="grid g3">
        {item(b.breakeven_profit, `Break-even ${b.label.toLowerCase()} (profit = 0)`, (v) => `${cur} ${num(v)} ${unit}`, b.current)}
        {item(b.hurdle_equity_irr, `${b.label} for hurdle equity IRR`, (v) => `${cur} ${num(v)} ${unit}`, b.current)}
        {b.absorption_for_hurdle && item(b.absorption_for_hurdle, 'Absorption for hurdle equity IRR', (v) => `${num(v, 2)} units/mo`, b.absorption_for_hurdle.current)}
      </div>
    </Card>
  )
}

interface Row { key: string; op: 'set' | 'pct' | 'add'; value: string }

function ScenarioBuilder({ pid, base, cur, onSaved }: { pid: number; base: Json; cur: string; onSaved: () => void }) {
  const meta = useMeta()
  const keys = Object.entries(meta.registry).filter(([, s]) => s.kind === 'number' || s.kind === 'int')
  const [rows, setRows] = useState<Row[]>([{ key: 'rev.price_per_area', op: 'pct', value: '-5' }])
  const [out, setOut] = useState<Json>(null)
  const [err, setErr] = useState<string | null>(null)
  const [name, setName] = useState('')
  const changes = rows.filter((r) => r.value !== '').map((r) => ({ key: r.key, op: r.op, value: Number(r.value) }))
  const run = async () => {
    setErr(null)
    try { setOut(await api.post(`/api/projects/${pid}/what-if`, { changes })) } catch (e) { setErr((e as Error).message); setOut(null) }
  }
  const save = async () => {
    setErr(null)
    try { await api.post(`/api/projects/${pid}/variants`, { kind: 'scenario', name: name || 'Custom scenario', payload: changes }); setName(''); onSaved(); notifyProjectChanged(pid) }
    catch (e) { setErr((e as Error).message) }
  }
  const cmp = [['equity_irr', 'Equity IRR', pct], ['project_irr', 'Project IRR', pct], ['profit', 'Profit', (v: number) => money(v, cur)],
    ['net_margin', 'Net margin', pct], ['peak_equity', 'Peak equity', (v: number) => money(v, cur)], ['duration_months', 'Duration', (v: number) => `${v} mo`]] as const
  return (
    <Card title="Custom what-if" sub="Nothing is saved to the project unless you save it as a scenario">
      <div className="col" style={{ gap: 6 }}>
        {rows.map((r, i) => (
          <div key={i} className="row" style={{ gap: 6 }}>
            <select className="input" value={r.key} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, key: e.target.value } : x))}>
              {keys.map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
            </select>
            <select className="input" style={{ width: 110 }} value={r.op} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, op: e.target.value as Row['op'] } : x))}>
              <option value="pct">% change</option><option value="add">add</option><option value="set">set to</option>
            </select>
            <input className="input num" style={{ width: 110 }} value={r.value} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, value: e.target.value } : x))} />
            <button className="btn ghost sm" onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 size={13} /></button>
          </div>
        ))}
        <div className="row" style={{ gap: 6 }}>
          <button className="btn sm" onClick={() => setRows([...rows, { key: 'cost.hard_per_area', op: 'pct', value: '' }])}><Plus size={13} /> Add change</button>
          <div className="grow" />
          <button className="btn primary sm" onClick={run} disabled={!changes.length}><Play size={13} /> Run</button>
        </div>
        {err && <Callout tone="bad">{err}</Callout>}
        {out && (out.status === 'ok' ? (
          <>
            <table className="t">
              <thead><tr><th>Metric</th><th className="num">Current</th><th className="num">What-if</th><th className="num">Change</th></tr></thead>
              <tbody>{cmp.map(([k, l, f]) => {
                const a = base[k], b = out.metrics[k]
                const d = a != null && b != null ? b - a : null
                return <tr key={k}><td>{l}</td><td className="num">{a != null ? f(a) : '—'}</td><td className="num" style={{ fontWeight: 600 }}>{b != null ? f(b) : '—'}</td>
                  <td className="num" style={{ color: d == null ? undefined : d < 0 ? 'var(--critical)' : 'var(--good-text)' }}>
                    {d == null ? '—' : PCT_METRICS.has(k) ? `${d > 0 ? '+' : ''}${(d * 100).toFixed(1)} pts` : k === 'duration_months' ? `${d > 0 ? '+' : ''}${d}` : `${d > 0 ? '+' : ''}${money(d, cur)}`}</td></tr>
              })}</tbody>
            </table>
            {out.covenants?.some((c: Json) => !c.ok) && <Callout tone="warn">Covenant breach in this scenario: {out.covenants.filter((c: Json) => !c.ok).map((c: Json) => c.name).join(', ')}</Callout>}
            {out.warnings?.map((w: string, i: number) => <Callout key={i} tone="warn">{w}</Callout>)}
            <div className="row" style={{ gap: 6 }}>
              <input className="input" placeholder="Scenario name" value={name} onChange={(e) => setName(e.target.value)} />
              <button className="btn sm" onClick={save}><Save size={13} /> Save scenario</button>
            </div>
          </>
        ) : <Callout tone="warn">Model {out.status}: {(out.missing || []).join(', ')}</Callout>)}
      </div>
    </Card>
  )
}

function Solver({ pid, cur, assumptions }: { pid: number; cur: string; assumptions: Json }) {
  const meta = useMeta()
  const keys = Object.entries(meta.registry).filter(([, s]) => s.kind === 'number' || s.kind === 'int')
  const [key, setKey] = useState('site.land_price')
  const [metric, setMetric] = useState('equity_irr')
  const [target, setTarget] = useState('18')
  const [out, setOut] = useState<Json>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const isPct = PCT_METRICS.has(metric)
  const solve = async () => {
    setBusy(true); setErr(null)
    try {
      const t = Number(target)
      setOut(await api.post(`/api/projects/${pid}/solve`, { key, metric, target: isPct ? t / 100 : t }))
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const unit = meta.registry[key]?.unit ?? ''
  return (
    <Card title="Reverse underwriting" sub="Find the input value that achieves a target return">
      <div className="col" style={{ gap: 8 }}>
        <label className="field">Solve for
          <select className="input" value={key} onChange={(e) => setKey(e.target.value)}>{keys.map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}</select>
        </label>
        <div className="row" style={{ gap: 8 }}>
          <label className="field grow">Target metric
            <select className="input" value={metric} onChange={(e) => setMetric(e.target.value)}>
              <option value="equity_irr">Equity IRR</option><option value="project_irr">Project IRR</option><option value="net_margin">Net margin</option><option value="profit">Development profit</option>
            </select>
          </label>
          <label className="field" style={{ width: 150 }}>Target {isPct ? '(%)' : `(${cur})`}
            <input className="input num" value={target} onChange={(e) => setTarget(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && solve()} />
          </label>
        </div>
        <button className="btn primary" onClick={solve} disabled={busy}><Target size={14} /> {busy ? 'Solving…' : 'Solve'}</button>
        {err && <Callout tone="bad">{err}</Callout>}
        {out && (out.status === 'ok' ? (
          <div className="grid g2">
            <div className="card kpi flat"><div className="label">{out.label}</div><div className="value">{fmtValue(out.value, unit, cur)}</div>
              <div className="sub">current {fmtValue(assumptions[key] ?? out.current, unit, cur)}{out.current ? ` · ${(((out.value / out.current) - 1) * 100).toFixed(1)}%` : ''}</div></div>
            <div className="card kpi flat"><div className="label">Achieved</div><div className="value">{isPct ? pct(out.achieved, 2) : money(out.achieved, cur)}</div>
              <div className="sub">target {isPct ? `${target}%` : money(Number(target), cur)}</div></div>
          </div>
        ) : <Callout tone="warn">{out.message || `Status: ${out.status}`}</Callout>)}
      </div>
    </Card>
  )
}

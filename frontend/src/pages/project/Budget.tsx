import { Fragment, useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { applyChanges, type Json } from '../../api'
import { useProject } from '../../components/Layout'
import { Callout, Card, ChartTip, FieldGroup, Kpi, Legend, ModelIncomplete, PageHead } from '../../components/ui'
import { ResearchButton, ResearchMeta, SourceLink, VerifBadge, axisProps, gridProps, mTick, useResearch } from '../../components/b/common'
import { SERIES, money, num, pctNum } from '../../format'
import { useMeta } from '../../state'

const COST_KEYS = ['cost.hard_per_area', 'cost.below_grade_per_area', 'cost.demolition', 'cost.infrastructure_fees', 'cost.renovation_budget',
  'cost.design_pct', 'cost.permits_pct', 'cost.pm_supervision_pct', 'cost.insurance_other_pct', 'cost.contingency_pct',
  'cost.escalation_pct', 'cost.developer_fee_pct']
const SCH_KEYS = ['sch.predev_months', 'sch.construction_months']
const GROUP_ORDER = ['Acquisition', 'Hard costs', 'Soft costs', 'Commercial', 'Other', 'Financing']
const STACK = [
  { key: 'land_acq', label: 'Land & acquisition', color: SERIES[0] },
  { key: 'hard', label: 'Hard costs', color: SERIES[1] },
  { key: 'soft', label: 'Soft costs', color: SERIES[2] },
  { key: 'other', label: 'Contingency & fee', color: SERIES[3] },
  { key: 'commercial', label: 'Commercial', color: SERIES[4] },
]

export default function Budget() {
  const { data } = useProject()
  const p = data.project
  const cur = p.profile.currency || 'MXN'
  const res = data.results
  const ok = res?.status === 'ok'
  const m = ok ? res.metrics : null
  const research = useResearch(p.id)

  return (
    <div className="col" style={{ gap: 16 }}>
      <PageHead eyebrow="Step 4 · Cost & construction" title="Development Budget & Schedule">
        Costs are built from per-m², per-space, fixed and percentage drivers. Benchmarks are estimates, not contractor quotations.
      </PageHead>
      <ModelIncomplete results={res} />
      {ok && (
        <div className="grid g3" style={{ gridTemplateColumns: 'repeat(6, minmax(0, 1fr))' }}>
          <Kpi label="Total development cost" value={money(m.tdc, cur)} sub="excl. financing" />
          <Kpi label="Total cost incl. financing" value={money(m.total_cost, cur)} sub={`financing ${money(m.financing_cost, cur)}`} />
          <Kpi label="Cost per m² GBA" value={num(m.cost_per_area_gba)} sub={`${cur} / m² (incl. parking area)`} />
          <Kpi label="Hard costs" value={money(m.hard_cost, cur)} sub="escalated" />
          <Kpi label="Soft costs" value={money(m.soft_cost, cur)} />
          <Kpi label="Land & acquisition" value={money(m.land_and_acquisition, cur)} />
        </div>
      )}
      {ok && <BudgetTable res={res} cur={cur} />}
      {ok && <Timeline sch={res.schedule} mode={data.mode} />}
      {ok && <SpendCharts months={res.months} cur={cur} />}
      <div className="grid g2">
        <FieldGroup data={data} keys={COST_KEYS} title="Cost drivers" sub="Per m², fixed and % assumptions" cols={1} />
        <div className="col" style={{ gap: 16 }}>
          <FieldGroup data={data} keys={SCH_KEYS} title="Schedule" sub="Month 0 = land closing; construction follows pre-development" cols={1} />
          <HardSplit />
        </div>
      </div>
      <CostResearch pid={p.id} research={research.data?.cost} reload={research.reload} />
    </div>
  )
}

function BudgetTable({ res, cur }: { res: Json; cur: string }) {
  const groups = useMemo(() => {
    const g: Record<string, Json[]> = {}
    for (const r of res.budget as Json[]) (g[r.group] = g[r.group] || []).push(r)
    return GROUP_ORDER.filter((k) => g[k]).map((k) => ({ group: k, rows: g[k], total: g[k].reduce((s, r) => s + r.amount, 0) }))
  }, [res])
  const total = res.metrics.total_cost
  const units = res.metrics.units
  const areaBasis = total / (res.metrics.cost_per_area_gba || 1)
  const maxG = Math.max(...groups.map((g) => g.total))
  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 2.2fr) minmax(0, 1fr)' }}>
      <Card title="Development budget" sub="Every line is computed by the engine from its driver (basis column)">
        <div className="table-wrap" style={{ maxHeight: 620 }}>
          <table className="t">
            <thead><tr><th>Item</th><th>Basis</th><th className="num">Amount ({cur})</th><th className="num">Per m²</th><th className="num">Per unit</th><th className="num">% total</th></tr></thead>
            <tbody>
              {groups.map((g) => (
                <Fragment key={g.group}>
                  <tr className="group"><td colSpan={2}>{g.group}</td><td className="num">{num(g.total)}</td>
                    <td className="num">{num(g.total / areaBasis)}</td><td className="num">{units ? num(g.total / units) : '—'}</td><td className="num">{pctNum(g.total / total * 100)}</td></tr>
                  {g.rows.map((r: Json) => (
                    <tr key={r.item}><td style={{ paddingLeft: 20 }}>{r.item}</td><td className="small muted">{r.basis}</td><td className="num">{num(r.amount)}</td>
                      <td className="num">{r.per_area != null ? num(r.per_area) : '—'}</td><td className="num">{r.per_unit != null ? num(r.per_unit) : '—'}</td>
                      <td className="num">{r.pct_total != null ? pctNum(r.pct_total) : '—'}</td></tr>
                  ))}
                </Fragment>
              ))}
              <tr className="total"><td colSpan={2}>Total cost incl. financing</td><td className="num">{num(total)}</td><td className="num">{num(res.metrics.cost_per_area_gba)}</td>
                <td className="num">{units ? num(total / units) : '—'}</td><td className="num">100.0%</td></tr>
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Cost by category" sub="Share of total cost">
        <div className="col" style={{ gap: 10 }}>
          {groups.map((g, i) => (
            <div key={g.group}>
              <div className="row between small"><span>{g.group}</span><span className="num" style={{ fontWeight: 600 }}>{money(g.total, cur)} · {pctNum(g.total / total * 100)}</span></div>
              <div style={{ height: 10, background: 'var(--surface-2)', borderRadius: 4, marginTop: 4 }} title={`${g.group}: ${money(g.total, cur)}`}>
                <div style={{ width: `${(g.total / maxG) * 100}%`, height: '100%', background: SERIES[i], borderRadius: 4 }} />
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

function Timeline({ sch, mode }: { sch: Json; mode: string }) {
  const H = Math.max(sch.horizon, 1)
  const bars = [
    { label: 'Acquisition', from: 0, to: 0.6, color: SERIES[0] },
    { label: 'Design & permits', from: 0.6, to: sch.predev_months + 1, color: SERIES[6] },
    { label: 'Construction', from: sch.construction_start + 1, to: sch.delivery_month + 1, color: SERIES[1] },
    ...(mode === 'sale' && sch.sales_start != null
      ? [{ label: 'Commercialization (sales)', from: sch.sales_start, to: sch.sellout_month + 1, color: SERIES[2] }]
      : sch.exit_month != null ? [{ label: 'Operations & hold', from: sch.delivery_month + 1, to: sch.exit_month + 1, color: SERIES[2] }] : []),
  ]
  return (
    <Card title="Development timeline" sub={`Delivery in month ${sch.delivery_month} · horizon ${sch.horizon} months`}>
      <div className="col" style={{ gap: 8 }}>
        {bars.map((b) => (
          <div key={b.label} className="row" style={{ gap: 10 }}>
            <div className="small" style={{ width: 190, color: 'var(--text-2)' }}>{b.label}</div>
            <div className="grow" style={{ position: 'relative', height: 18, background: 'var(--surface-2)', borderRadius: 4 }}>
              <div title={`M${Math.round(b.from)}–M${Math.round(b.to) - 1}`} style={{ position: 'absolute', left: `${(b.from / (H + 1)) * 100}%`,
                width: `${Math.max(((b.to - b.from) / (H + 1)) * 100, 0.8)}%`, top: 0, bottom: 0, background: b.color, borderRadius: 4 }} />
            </div>
            <div className="tiny muted num" style={{ width: 80 }}>M{Math.round(b.from)}–M{Math.max(Math.round(b.to) - 1, Math.round(b.from))}</div>
          </div>
        ))}
        <div className="row" style={{ gap: 10 }}>
          <div style={{ width: 190 }} />
          <div className="grow row between tiny muted"><span>M0</span><span>Delivery M{sch.delivery_month}</span><span>M{H}</span></div>
          <div style={{ width: 80 }} />
        </div>
      </div>
    </Card>
  )
}

function SpendCharts({ months, cur }: { months: Json[]; cur: string }) {
  const rows = months.map((m) => ({ ...m, land_acq: m.month === 0 ? 0 : m.land_acq }))
  const land0 = months[0]?.land_acq || 0
  return (
    <div className="grid g2">
      <Card title="Monthly development expenditure" sub={`S-curve construction spend · month-0 land & acquisition (${money(land0, cur)}) omitted from bars for scale`}>
        <Legend items={STACK.slice(1)} />
        <div style={{ height: 260, marginTop: 6 }}>
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={mTick} />
              <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => money(v, cur)} />} />
              {STACK.slice(1).map((s, i, arr) => (
                <Bar key={s.key} dataKey={s.key} name={s.label} stackId="a" fill={s.color} stroke="#fff" strokeWidth={1}
                  radius={i === arr.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} maxBarSize={16} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="Cumulative development cost" sub="All costs incl. land, excluding financing">
        <div style={{ height: 284 }}>
          <ResponsiveContainer>
            <LineChart data={months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={mTick} />
              <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => money(v, cur)} />} />
              <Line dataKey="cumulative_cost" name="Cumulative cost" stroke={SERIES[0]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  )
}

function HardSplit() {
  const { data } = useProject()
  const meta = useMeta()
  const saved = data.project.assumptions.hard_cost_split as Record<string, number> | undefined
  const base = saved || meta.hard_cost_split
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<string | null>(null)
  useEffect(() => { setDraft(Object.fromEntries(Object.entries(base).map(([k, v]) => [k, String(v)]))) }, [base])
  const sum = Object.values(draft).reduce((s, v) => s + (Number(v) || 0), 0)
  const okSum = Math.abs(sum - 100) <= 0.5
  const save = async () => {
    const r = await applyChanges(data.project.id, [{ key: 'hard_cost_split', value: Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, Number(v) || 0])) }], { reason: 'hard cost split edit' })
    setMsg(r.rejected?.length ? r.rejected[0].error : 'Saved — budget recalculated.')
  }
  return (
    <Card title="Hard-cost category split" sub={saved ? 'Project-specific split' : 'Benchmark allocation (default) — edit to match your cost plan'}>
      <div className="grid g2" style={{ columnGap: 16, rowGap: 6 }}>
        {Object.keys(draft).map((k) => (
          <label key={k} className="row" style={{ gap: 6, justifyContent: 'space-between' }}>
            <span className="small">{k}</span>
            <input className="input num" style={{ width: 70, height: 28, textAlign: 'right' }} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
          </label>
        ))}
      </div>
      <div className="row between" style={{ marginTop: 10 }}>
        <span className="small" style={{ color: okSum ? 'var(--good-text)' : 'var(--critical)' }}>Total {num(sum, 1)}% {okSum ? '✓' : '(must equal 100%)'}</span>
        <div className="row" style={{ gap: 8 }}>{msg && <span className="tiny muted">{msg}</span>}<button className="btn primary sm" disabled={!okSum} onClick={save}>Save split</button></div>
      </div>
    </Card>
  )
}

function CostResearch({ pid, research, reload }: { pid: number; research: Json; reload: () => void }) {
  const rows: Json[] = research?.payload?.benchmarks ?? []
  return (
    <Card title="Construction cost benchmarks" sub="Cost & Construction agent · published guides and indices · estimates, not contractor quotes"
      actions={<ResearchButton pid={pid} kind="cost" label="Run Cost agent" hasData={!!research} onDone={reload} />}>
      {!research ? <Callout tone="info">No cost research yet. Run the Cost agent to find preliminary benchmarks for this location and quality. Mapped values become pending proposals in the cost fields above.</Callout> : (
        <div className="col" style={{ gap: 8 }}>
          <ResearchMeta r={research} />
          <div className="table-wrap">
            <table className="t">
              <thead><tr><th>Benchmark</th><th className="num">Value</th><th>Unit</th><th className="num">Range</th><th>Year</th><th>Status</th><th>Maps to</th><th>Source</th></tr></thead>
              <tbody>{rows.map((b, i) => (
                <tr key={i}><td>{b.item}{b.note && <div className="tiny muted">{b.note}</div>}</td><td className="num">{b.value != null ? num(b.value, b.value % 1 ? 2 : 0) : '—'}</td>
                  <td className="small">{b.unit}</td><td className="num small">{b.low != null || b.high != null ? `${b.low != null ? num(b.low) : '?'} – ${b.high != null ? num(b.high) : '?'}` : '—'}</td>
                  <td className="small">{b.year || '—'}</td><td><VerifBadge v={b.verification} /></td><td className="tiny muted">{b.key || '—'}</td><td className="small"><SourceLink url={b.source_url} title={b.source_title} /></td></tr>
              ))}</tbody>
            </table>
          </div>
          {research.payload?.caveats?.length > 0 && <div className="small muted">{research.payload.caveats.join(' · ')}</div>}
        </div>
      )}
    </Card>
  )
}

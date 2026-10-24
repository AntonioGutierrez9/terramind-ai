import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { api, notifyProjectChanged, type Json } from '../../api'
import { useProject } from '../../components/Layout'
import ScheduleEditor from '../../components/ScheduleEditor'
import { Callout, Card, ChartTip, FieldGroup, Kpi, Legend, ModelIncomplete, PageHead, StatusBadge } from '../../components/ui'
import { ResearchButton, ResearchMeta, SourceLink, axisProps, gridProps, mTick, useResearch } from '../../components/b/common'
import { SERIES, money, num, pct, pctNum } from '../../format'

const SALE_KEYS = ['rev.price_per_area', 'rev.floor_view_premium_pct', 'rev.terrace_value_pct', 'rev.discount_pct', 'rev.escalation_pct',
  'rev.absorption_per_month', 'rev.cancellation_pct', 'rev.sales_start_offset', 'rev.commission_pct', 'rev.marketing_pct']
const PAY_KEYS = ['rev.deposit_pct', 'rev.installments_pct', 'rev.closing_pct']
const RENT_KEYS = ['rent.rent_per_area_month', 'rent.vacancy_pct', 'rent.concessions_pct', 'rent.opex_pct_egi', 'rent.growth_pct',
  'rent.lease_up_months', 'rent.exit_cap_pct', 'rent.selling_costs_pct', 'rent.hold_years']

export default function Market() {
  const { data } = useProject()
  const p = data.project
  const cur = p.profile.currency || 'MXN'
  const res = data.results
  const ok = res?.status === 'ok'
  const m = ok ? res.metrics : null
  const sale = data.mode === 'sale'
  const research = useResearch(p.id)

  return (
    <div className="col" style={{ gap: 16 }}>
      <PageHead eyebrow="Step 3 · Market" title="Market Research & Revenue"
        actions={<span className="badge">{sale ? 'Build-to-sell revenue model' : 'Rental income model'}</span>}>
        The Market Research agent finds real comparables with sources. TerraMind computes price per m² itself and proposes a base price you approve or override.
      </PageHead>
      <ModelIncomplete results={res} />

      {ok && sale && (
        <div className="grid g5">
          <Kpi label="Gross development value" value={money(m.gdv, cur)} sub="net of discounts, after cancellations" />
          <Kpi label="Avg unit price (today)" value={money(m.avg_unit_price_today, cur)} sub={`${num(m.units)} units`} />
          <Kpi label="Revenue per m²" value={money(m.revenue_per_area, cur, false)} sub="saleable area" />
          <Kpi label="Sales start → sellout" value={`M${m.sales_start} → M${m.sellout_month}`} sub={`${m.sellout_months} months of sales`} />
          <Kpi label="Delivery" value={`M${m.delivery_month}`} sub="balance collected at closing" />
        </div>
      )}
      {ok && !sale && (
        <div className="grid g5">
          <Kpi label="Stabilized GPR" value={money(m.stabilized_gpr, cur)} sub="per year" />
          <Kpi label="Stabilized EGI" value={money(m.stabilized_egi, cur)} sub="after vacancy & concessions" />
          <Kpi label="Stabilized NOI" value={money(m.stabilized_noi, cur)} sub="per year" />
          <Kpi label="Yield on cost" value={pct(m.yield_on_cost, 2)} sub={`exit cap ${pctNum(p.assumptions['rent.exit_cap_pct'], 2)}`} />
          <Kpi label="Exit value" value={money(m.exit_value, cur)} sub={`month ${m.exit_month}`} />
        </div>
      )}

      <Comparables pid={p.id} cur={cur} research={research.data?.market} reload={research.reload}
        basePrice={sale ? p.assumptions['rev.price_per_area'] : null} loading={research.loading && !research.data} />

      {sale ? (
        <div className="grid g2">
          <FieldGroup data={data} keys={SALE_KEYS} title="Pricing & absorption" sub="Fundamental inputs — revenue is calculated" cols={1} />
          <div className="col" style={{ gap: 16 }}>
            <PaymentSchedule data={data} />
            {ok && <UnitPricing res={res} cur={cur} />}
          </div>
        </div>
      ) : (
        <FieldGroup data={data} keys={RENT_KEYS} title="Rental assumptions" sub="GPR − vacancy − concessions = EGI; EGI − opex = NOI" />
      )}

      {sale && (
        <div className="grid g2" style={{ marginTop: 16 }}>
          <ScheduleEditor pid={p.id} k="sales_phases" rows={p.assumptions.sales_phases} />
          <ScheduleEditor pid={p.id} k="price_phases" rows={p.assumptions.price_phases} />
        </div>
      )}
      {ok && sale && <SalesCharts months={res.months} cur={cur} />}
      {ok && !sale && <NoiChart months={res.months} cur={cur} />}
    </div>
  )
}

function Comparables({ pid, cur, research, reload, basePrice, loading }: { pid: number; cur: string; research: Json; reload: () => void; basePrice: number | null; loading: boolean }) {
  const payload = research?.payload
  const rows: Json[] = payload?.summary?.rows ?? []
  const stats = payload?.summary?.stats
  const [busyIdx, setBusyIdx] = useState<number | null>(null)
  const toggle = async (i: number, excluded: boolean) => {
    setBusyIdx(i)
    try {
      await api.post(`/api/projects/${pid}/research/market/exclude`, { index: i, excluded })
      reload()
      notifyProjectChanged(pid)
    } finally { setBusyIdx(null) }
  }
  const dots = rows.filter((r) => r.price_per_area).map((r, i) => ({ x: r.price_per_area, y: 1, name: r.title, excluded: !!r.excluded, i }))
  return (
    <Card title="Comparable properties" sub="Real listings found by the Market Research agent · asking prices are never presented as transactions"
      actions={<ResearchButton pid={pid} kind="market" label="Run Market agent" hasData={!!payload} onDone={reload} />}>
      {loading ? <div className="empty"><span className="spinner" /></div> : !payload ? (
        <Callout tone="info">No market research yet. Run the Market agent to search for comparables near the project (about 30–60 seconds; results are cached and become a pending price proposal).</Callout>
      ) : (
        <div className="col" style={{ gap: 12 }}>
          <ResearchMeta r={research} />
          {stats ? (
            <div className="grid g4">
              <Kpi label="Comparables used" value={num(stats.n)} sub={`${rows.length - stats.n} excluded / no price`} />
              <Kpi label="Median price / m²" value={money(stats.median, cur, false)} sub="asking prices" />
              <Kpi label="Interquartile range" value={`${mTick(stats.p25)} – ${mTick(stats.p75)}`} sub={`min ${mTick(stats.min)} · max ${mTick(stats.max)}`} />
              <Kpi label="Project base price" value={basePrice ? money(basePrice, cur, false) : '—'}
                sub={basePrice && stats.median ? `${((basePrice / stats.median - 1) * 100).toFixed(1)}% vs median` : 'per m²'} />
            </div>
          ) : <Callout tone="warn">No comparables with both price and size are included, so no price statistics can be computed.</Callout>}
          {dots.length > 0 && (
            <div style={{ height: 110 }}>
              <ResponsiveContainer>
                <ScatterChart margin={{ top: 10, right: 20, bottom: 0, left: 10 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis type="number" dataKey="x" name="Price / m²" {...axisProps} tickFormatter={mTick} domain={['auto', 'auto']} />
                  <YAxis type="number" dataKey="y" hide domain={[0, 2]} />
                  <ZAxis range={[90, 90]} />
                  <Tooltip content={({ active, payload: pl }) => active && pl?.length ? (
                    <div className="chart-tip"><div className="tt">{pl[0].payload.name}</div>{money(pl[0].payload.x, cur, false)} / m²{pl[0].payload.excluded ? ' · excluded' : ''}</div>) : null} />
                  {basePrice && <ReferenceLine x={basePrice} stroke="#17345e" strokeDasharray="4 3" label={{ value: 'Base price', fill: '#17345e', fontSize: 11, position: 'top' }} />}
                  {stats && <ReferenceLine x={stats.median} stroke={SERIES[1]} strokeDasharray="2 3" label={{ value: 'Median', fill: '#52514e', fontSize: 11, position: 'insideTopRight' }} />}
                  <Scatter data={dots.filter((d) => !d.excluded)} fill={SERIES[0]} stroke="#fff" strokeWidth={2} />
                  <Scatter data={dots.filter((d) => d.excluded)} fill="#c3c8d1" stroke="#fff" strokeWidth={2} />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="table-wrap">
            <table className="t">
              <thead><tr><th>Use</th><th>Comparable</th><th>Area</th><th className="num">Size</th><th className="num">Beds</th><th className="num">Price</th><th className="num">Price / m²</th><th>Price type</th><th>Listed</th><th>Source</th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} style={{ opacity: r.excluded ? 0.5 : 1 }}>
                    <td><input type="checkbox" checked={!r.excluded} disabled={busyIdx === i} onChange={(e) => toggle(i, !e.target.checked)} title="Include in price statistics" /></td>
                    <td style={{ maxWidth: 260 }}><div style={{ fontWeight: 550 }}>{r.title}</div>
                      <div className="tiny muted">{[r.quality, ...(r.amenities || []).slice(0, 3)].filter(Boolean).join(' · ')}{r.notes ? ` — ${r.notes}` : ''}</div></td>
                    <td className="small">{r.neighborhood || '—'}</td>
                    <td className="num">{r.size ? `${num(r.size)} m²` : '—'}</td>
                    <td className="num">{r.bedrooms ?? '—'}</td>
                    <td className="num">{r.price ? money(r.price, r.currency || cur) : '—'}</td>
                    <td className="num" style={{ fontWeight: 600 }}>{r.price_per_area ? num(r.price_per_area) : '—'}</td>
                    <td>{r.price_type === 'transaction' ? <StatusBadge level="good">transaction</StatusBadge> : <StatusBadge level="warn">{r.price_type === 'asking' ? 'asking, not transaction' : 'unknown'}</StatusBadge>}</td>
                    <td className="small">{r.listing_date || '—'}</td>
                    <td className="small"><SourceLink url={r.source_url} title={r.title} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(payload.market_notes?.length > 0 || payload.caveats?.length > 0) && (
            <div className="grid g2">
              {payload.market_notes?.length > 0 && <div className="small"><b>Market notes</b><ul style={{ margin: '4px 0', paddingLeft: 18 }}>{payload.market_notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>
                {payload.absorption_evidence && <div className="small muted">Absorption: {payload.absorption_evidence}</div>}</div>}
              {payload.caveats?.length > 0 && <div className="small"><b>Caveats</b><ul style={{ margin: '4px 0', paddingLeft: 18 }}>{payload.caveats.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul></div>}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

function PaymentSchedule({ data }: { data: ReturnType<typeof useProject>['data'] }) {
  const a = data.project.assumptions
  const sum = PAY_KEYS.reduce((s, k) => s + (Number(a[k]) || 0), 0)
  const okSum = Math.abs(sum - 100) <= 0.5
  return (
    <div className="col" style={{ gap: 8 }}>
      <FieldGroup data={data} keys={PAY_KEYS} title="Buyer payment schedule" sub="Deposit at contract, installments to delivery, balance at closing" cols={1} />
      {okSum ? <Callout tone="good">Payment schedule adds to {num(sum, 1)}%.</Callout>
        : <Callout tone="bad">Deposit + installments + closing = {num(sum, 1)}%. It must equal 100% before the model can run.</Callout>}
    </div>
  )
}

function UnitPricing({ res, cur }: { res: Json; cur: string }) {
  const types: Json[] = res.design?.unit_types ?? []
  return (
    <Card title="Unit pricing (today's prices)" sub="Base price × type premium × floor/view premium + terrace value">
      <table className="t">
        <thead><tr><th>Type</th><th className="num">Units</th><th className="num">Size</th><th className="num">Terrace</th><th className="num">Premium</th><th className="num">Unit price</th><th className="num">Effective / m²</th></tr></thead>
        <tbody>
          {types.map((t) => (
            <tr key={t.name}><td>{t.name}</td><td className="num">{t.units}</td><td className="num">{num(t.size)} m²</td><td className="num">{num(t.terrace)} m²</td>
              <td className="num">{pctNum(t.premium_pct, 0)}</td><td className="num">{money(t.unit_price, cur)}</td><td className="num">{num(t.price_per_area_effective)}</td></tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function SalesCharts({ months, cur }: { months: Json[]; cur: string }) {
  const rows = useMemo(() => months.map((m) => ({ month: m.month, units: m.units_sold || 0, cum: m.units_sold_cum || 0, inflow: m.inflow, contract: m.contract_value || 0 })), [months])
  return (
    <div className="grid g2">
      <Card title="Monthly sales absorption" sub="Net units sold per month (after cancellations)">
        <div style={{ height: 200 }}>
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
              <YAxis {...axisProps} />
              <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => num(v, 2)} />} />
              <Bar dataKey="units" name="Units sold" fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={14} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div style={{ height: 140, marginTop: 8 }}>
          <ResponsiveContainer>
            <LineChart data={rows} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
              <YAxis {...axisProps} />
              <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => num(v, 1)} />} />
              <Line dataKey="cum" name="Cumulative units" stroke={SERIES[0]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="Contracts vs cash collections" sub="Contract value signed vs cash collected (deposits, installments, closing)">
        <Legend items={[{ label: 'Contract value', color: SERIES[0] }, { label: 'Cash collected', color: SERIES[1] }]} />
        <div style={{ height: 330, marginTop: 6 }}>
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={mTick} />
              <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => money(v, cur)} />} />
              <Bar dataKey="contract" name="Contract value" fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={10} />
              <Bar dataKey="inflow" name="Cash collected" fill={SERIES[1]} radius={[4, 4, 0, 0]} maxBarSize={10} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  )
}

function NoiChart({ months, cur }: { months: Json[]; cur: string }) {
  const rows = months.filter((m) => m.noi != null).map((m) => ({ month: m.month, noi: m.noi }))
  return (
    <Card title="Monthly net operating income" sub="Lease-up after delivery, then stabilized NOI growing with rents (exit proceeds excluded)">
      <div style={{ height: 240 }}>
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
            <YAxis {...axisProps} tickFormatter={mTick} />
            <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => money(v, cur)} />} />
            <Line dataKey="noi" name="NOI" stroke={SERIES[0]} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

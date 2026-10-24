import { useMemo } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Json } from '../../api'
import { useProject } from '../../components/Layout'
import { Callout, Card, ChartTip, FieldGroup, Kpi, Legend, ModelIncomplete, PageHead, StatusBadge } from '../../components/ui'
import { ResearchButton, ResearchMeta, SourceLink, VerifBadge, axisProps, gridProps, mTick, useResearch } from '../../components/b/common'
import { SERIES, money, multiple, num, pct, pctNum } from '../../format'

const STRUCTURE = ['fin.senior_ltc_pct', 'fin.mezz_ltc_pct', 'fin.sponsor_equity_share_pct', 'fin.senior_term_months', 'fin.sweep_pct', 'fin.interest_capitalized', 'fin.amortization_years']
const RATES = ['fin.senior_rate_type', 'fin.reference_rate_pct', 'fin.senior_spread_pct', 'fin.senior_fixed_rate_pct', 'fin.mezz_rate_pct', 'fin.origination_fee_pct', 'fin.commitment_fee_pct']
const COVENANTS = ['fin.max_ltc_covenant_pct', 'fin.max_ltv_covenant_pct', 'fin.min_presales_pct', 'fin.min_dscr']
const WATERFALL = ['fin.pref_return_pct', 'fin.promote_pct']

export default function Financing() {
  const { data } = useProject()
  const p = data.project
  const cur = p.profile.currency || 'MXN'
  const res = data.results
  const ok = res?.status === 'ok'
  const m = ok ? res.metrics : null
  const research = useResearch(p.id)

  return (
    <div className="col" style={{ gap: 16 }}>
      <PageHead eyebrow="Step 5 · Capital structure" title="Financing & Capital Structure">
        Equity funds first, then mezzanine, then senior debt. Interest accrues monthly on the actual drawn balance, not as a flat percentage of cost.
      </PageHead>
      <ModelIncomplete results={res} />
      <Callout tone="info">Financing terms are <b>material</b>. Your edits here apply directly; when the AI assistant proposes them, they wait for your confirmation click. TerraMind never executes financing transactions.</Callout>
      {ok && (m.funding_gap > 1 || m.maturity_shortfall > 1) && (
        <Callout tone="bad">
          {m.funding_gap > 1 && <div><b>Funding gap:</b> {money(m.funding_gap, cur)} of additional equity is needed beyond the planned capital stack.</div>}
          {m.maturity_shortfall > 1 && <div><b>Maturity shortfall:</b> {money(m.maturity_shortfall, cur)} of senior debt is still outstanding at maturity (month {m.maturity_month}).</div>}
        </Callout>
      )}
      {ok && (
        <>
          <div className="grid g4">
            <Kpi label="Senior commitment" value={money(m.senior_commitment, cur)} sub={`LTC ${pct(m.ltc)}`} />
            <Kpi label="Peak debt" value={money(m.peak_debt, cur)} sub={`LTV ${pct(m.ltv)} of GDV`} />
            <Kpi label="All-in senior rate" value={pctNum(m.senior_rate_pct, 2)} sub={p.assumptions['fin.senior_rate_type'] === 'fixed' ? 'fixed' : 'reference + spread'} />
            <Kpi label="Financing cost" value={money(m.financing_cost, cur)} sub="interest + fees on actual balances" />
            <Kpi label="Peak equity" value={money(m.peak_equity, cur)} sub={`contributed ${money(m.equity_contributed, cur)}`} />
            <Kpi label="Funding gap" value={money(m.funding_gap, cur)} tone={m.funding_gap > 1 ? 'bad' : 'good'} sub={m.funding_gap > 1 ? 'additional equity required' : 'none'} />
            <Kpi label="First draw / maturity" value={m.first_draw_month != null ? `M${m.first_draw_month} / M${m.maturity_month}` : 'No draw'} sub={m.presales_at_first_draw_pct != null ? `${pctNum(m.presales_at_first_draw_pct, 0)} presold at first draw` : ''} />
            <Kpi label="Equity multiple" value={multiple(m.moic)} sub={`equity IRR ${pct(m.equity_irr)}`} />
          </div>
          <CapitalStack m={m} cur={cur} />
        </>
      )}
      <div className="grid g2">
        <FieldGroup data={data} keys={STRUCTURE} title="Capital structure" sub="Sources as % of total cost (incl. financing)" cols={1} />
        <FieldGroup data={data} keys={RATES} title="Pricing & fees" sub="Floating = reference rate + spread" cols={1} />
      </div>
      {ok && <DebtCharts months={res.months} cur={cur} />}
      {ok && <EquityCharts months={res.months} cur={cur} />}
      <div className="grid g2">
        <div className="col" style={{ gap: 16 }}>
          {ok && <Covenants covs={res.covenants} />}
          <FieldGroup data={data} keys={COVENANTS} title="Covenant thresholds" cols={1} />
        </div>
        <div className="col" style={{ gap: 16 }}>
          {ok && <Waterfall wf={res.waterfall} cur={cur} />}
          <FieldGroup data={data} keys={WATERFALL} title="Waterfall terms" sub="Return of capital → preferred return → promote" cols={1} />
        </div>
      </div>
      {ok && res.months.some((x: Json) => x.funding_gap > 0) && <GapChart months={res.months} cur={cur} />}
      <RateResearch pid={p.id} research={research.data?.financing} reload={research.reload} />
    </div>
  )
}

function CapitalStack({ m, cur }: { m: Json; cur: string }) {
  const parts = [
    { label: 'Senior debt (commitment)', v: m.senior_commitment, color: SERIES[0] },
    { label: 'Mezzanine (commitment)', v: m.mezz_commitment, color: SERIES[6] },
    { label: 'Equity contributed', v: m.equity_contributed, color: SERIES[2] },
  ].filter((x) => x.v > 0)
  const total = parts.reduce((s, x) => s + x.v, 0) || 1
  return (
    <Card title="Capital stack" sub={`Sources vs total cost incl. financing (${money(m.total_cost, cur)}). Presale collections fund the remainder.`}>
      <div style={{ display: 'flex', height: 30, borderRadius: 6, overflow: 'hidden', gap: 2, background: '#fff' }}>
        {parts.map((x) => (
          <div key={x.label} title={`${x.label}: ${money(x.v, cur)}`} style={{ width: `${(x.v / total) * 100}%`, background: x.color, color: '#fff', fontSize: 12, fontWeight: 600, display: 'grid', placeItems: 'center' }}>
            {(x.v / total) > 0.08 ? pct(x.v / m.total_cost, 0) : ''}
          </div>
        ))}
      </div>
      <div className="row wrap" style={{ marginTop: 10, gap: 18 }}>
        {parts.map((x) => (
          <div key={x.label} className="small"><span className="sw" style={{ width: 10, height: 10, borderRadius: 3, background: x.color, display: 'inline-block', marginRight: 6 }} />
            {x.label}: <b className="num">{money(x.v, cur)}</b> <span className="muted">({pct(x.v / m.total_cost)} of cost)</span></div>
        ))}
      </div>
    </Card>
  )
}

function DebtCharts({ months, cur }: { months: Json[]; cur: string }) {
  const rows = months.map((x) => ({ month: x.month, senior: x.senior_balance, mezz: x.mezz_balance, draw: x.senior_draw, repay: -x.senior_repay, interest: x.interest }))
  const hasMezz = rows.some((r) => r.mezz > 0)
  return (
    <div className="grid g3">
      <Card title="Debt balance" sub="End-of-month balances incl. capitalized interest" className="span2">
        {hasMezz && <Legend items={[{ label: 'Senior', color: SERIES[0] }, { label: 'Mezzanine', color: SERIES[6] }]} />}
        <div style={{ height: 230, marginTop: 6 }}>
          <ResponsiveContainer>
            <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={mTick} />
              <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => money(v, cur)} />} />
              <Area dataKey="senior" name="Senior" stackId="d" stroke={SERIES[0]} strokeWidth={2} fill={SERIES[0]} fillOpacity={0.18} />
              {hasMezz && <Area dataKey="mezz" name="Mezzanine" stackId="d" stroke={SERIES[6]} strokeWidth={2} fill={SERIES[6]} fillOpacity={0.18} />}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="Monthly interest" sub="Rate × opening balance">
        <div style={{ height: 250 }}>
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ top: 8, right: 8, left: -6, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={mTick} />
              <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => money(v, cur)} />} />
              <Bar dataKey="interest" name="Interest" fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={12} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="Senior draws and repayments" sub="Draws above the axis, repayments (sales sweep / balloon) below" className="span3">
        <Legend items={[{ label: 'Draws', color: SERIES[0] }, { label: 'Repayments', color: SERIES[1] }]} />
        <div style={{ height: 200, marginTop: 6 }}>
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} stackOffset="sign">
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={mTick} />
              <ReferenceLine y={0} stroke="#cfd6e1" />
              <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => money(Math.abs(v), cur)} />} />
              <Bar dataKey="draw" name="Draws" stackId="s" fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={12} />
              <Bar dataKey="repay" name="Repayments" stackId="s" fill={SERIES[1]} radius={[0, 0, 4, 4]} maxBarSize={12} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  )
}

function EquityCharts({ months, cur }: { months: Json[]; cur: string }) {
  const rows = useMemo(() => {
    let cum = 0
    return months.map((x) => { cum += x.equity_contrib - x.equity_dist; return { month: x.month, contrib: -x.equity_contrib, dist: x.equity_dist, net: cum } })
  }, [months])
  return (
    <div className="grid g2">
      <Card title="Equity contributions and distributions" sub="Contributions below the axis, distributions above">
        <Legend items={[{ label: 'Contributions', color: SERIES[1] }, { label: 'Distributions', color: SERIES[2] }]} />
        <div style={{ height: 230, marginTop: 6 }}>
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} stackOffset="sign">
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={mTick} />
              <ReferenceLine y={0} stroke="#cfd6e1" />
              <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => money(Math.abs(v), cur)} />} />
              <Bar dataKey="contrib" name="Contributions" stackId="e" fill={SERIES[1]} radius={[0, 0, 4, 4]} maxBarSize={12} />
              <Bar dataKey="dist" name="Distributions" stackId="e" fill={SERIES[2]} radius={[4, 4, 0, 0]} maxBarSize={12} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="Net equity outstanding" sub="Cumulative contributions − distributions (peak = peak equity)">
        <div style={{ height: 254 }}>
          <ResponsiveContainer>
            <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={mTick} />
              <ReferenceLine y={0} stroke="#cfd6e1" />
              <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => money(v, cur)} />} />
              <Line dataKey="net" name="Net equity" stroke={SERIES[2]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  )
}

function Covenants({ covs }: { covs: Json[] }) {
  return (
    <Card title="Covenant compliance" sub="Checked by the engine on the modeled cash flows">
      {covs.length === 0 ? <div className="small muted">No debt, so no covenants apply.</div> : (
        <table className="t">
          <thead><tr><th>Covenant</th><th className="num">Limit</th><th className="num">Actual</th><th>Status</th></tr></thead>
          <tbody>{covs.map((c) => (
            <tr key={c.name}><td>{c.name}</td><td className="num">{num(c.limit, c.unit === 'x' ? 2 : 1)} {c.unit}</td><td className="num">{num(c.actual, c.unit === 'x' ? 2 : 1)} {c.unit}</td>
              <td>{c.ok ? <StatusBadge level="good">compliant</StatusBadge> : <StatusBadge level="bad">breach</StatusBadge>}</td></tr>
          ))}</tbody>
        </table>
      )}
    </Card>
  )
}

function Waterfall({ wf, cur }: { wf: Json; cur: string }) {
  const tiers = [
    { k: 'return_of_capital', label: 'Return of capital' },
    { k: 'preferred_return', label: 'Preferred return' },
    { k: 'residual_pro_rata', label: 'Residual (pro rata)' },
    { k: 'sponsor_promote', label: 'Sponsor promote' },
  ].map((t, i) => ({ ...t, v: wf.tiers[t.k] || 0, color: SERIES[i] }))
  const max = Math.max(...tiers.map((t) => t.v), 1)
  return (
    <Card title="Equity waterfall" sub="Distributions by tier and by partner">
      <div className="col" style={{ gap: 8 }}>
        {tiers.map((t) => (
          <div key={t.k}>
            <div className="row between small"><span>{t.label}</span><b className="num">{money(t.v, cur)}</b></div>
            <div style={{ height: 8, background: 'var(--surface-2)', borderRadius: 4, marginTop: 3 }}><div style={{ width: `${(t.v / max) * 100}%`, height: '100%', background: t.color, borderRadius: 4 }} /></div>
          </div>
        ))}
      </div>
      <table className="t" style={{ marginTop: 12 }}>
        <thead><tr><th>Partner</th><th className="num">Contributed</th><th className="num">Distributed</th><th className="num">IRR</th><th className="num">MOIC</th></tr></thead>
        <tbody>
          {(['investor', 'sponsor'] as const).map((k) => (
            <tr key={k}><td style={{ textTransform: 'capitalize' }}>{k}</td><td className="num">{money(wf[k].contributed, cur)}</td><td className="num">{money(wf[k].distributed, cur)}</td>
              <td className="num">{pct(wf[k].irr)}</td><td className="num">{multiple(wf[k].moic)}</td></tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function GapChart({ months, cur }: { months: Json[]; cur: string }) {
  return (
    <Card title="Funding requirement beyond the capital stack" sub="Months where additional equity was needed">
      <div style={{ height: 200 }}>
        <ResponsiveContainer>
          <BarChart data={months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="month" {...axisProps} tickFormatter={(v) => `M${v}`} interval="preserveStartEnd" />
            <YAxis {...axisProps} tickFormatter={mTick} />
            <Tooltip content={<ChartTip labelFmt={(l) => `Month ${l}`} fmt={(v) => money(v, cur)} />} />
            <Bar dataKey="funding_gap" name="Funding gap" fill={SERIES[7]} radius={[4, 4, 0, 0]} maxBarSize={14} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function RateResearch({ pid, research, reload }: { pid: number; research: Json; reload: () => void }) {
  const rows: Json[] = research?.payload?.rates ?? []
  return (
    <Card title="Financing benchmarks" sub="Published rates, indicative assumptions and actual lender offers are distinguished; web research never produces lender offers."
      actions={<ResearchButton pid={pid} kind="financing" label="Run Financing agent" hasData={!!research} onDone={reload} />}>
      {!research ? <Callout tone="info">No financing research yet. Run the Financing agent to fetch the current reference rate (e.g. TIIE) and typical construction-loan terms. Mapped values become pending proposals above.</Callout> : (
        <div className="col" style={{ gap: 8 }}>
          <ResearchMeta r={research} />
          <table className="t">
            <thead><tr><th>Item</th><th className="num">Rate</th><th>As of</th><th>Type</th><th>Institution</th><th>Maps to</th><th>Source</th></tr></thead>
            <tbody>{rows.map((r, i) => (
              <tr key={i}><td>{r.item}{r.note && <div className="tiny muted">{r.note}</div>}</td><td className="num">{r.value_pct != null ? pctNum(r.value_pct, 2) : '—'}</td>
                <td className="small">{r.as_of || '—'}</td><td><VerifBadge v={r.kind} /></td><td className="small">{r.institution || '—'}</td><td className="tiny muted">{r.key || '—'}</td>
                <td className="small"><SourceLink url={r.source_url} title={r.source_title} /></td></tr>
            ))}</tbody>
          </table>
          {research.payload?.lenders?.length > 0 && <div className="small"><b>Lenders mentioned publicly:</b> {research.payload.lenders.join(', ')}</div>}
          {research.payload?.caveats?.length > 0 && <div className="small muted">{research.payload.caveats.join(' · ')}</div>}
        </div>
      )}
    </Card>
  )
}

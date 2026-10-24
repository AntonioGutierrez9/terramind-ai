import { Link, useNavigate } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { api, notifyProjectChanged, type Json } from '../api'
import { useAuth } from '../auth'
import { t as tr } from '../i18n'
import { Callout, Card, ChartTip, Kpi, Loading, PageHead, StatusBadge } from '../components/ui'
import { AXIS, GRID, money, multiple, pct, SERIES } from '../format'
import { useFetch } from '../state'

const HURDLE = 0.18
// keeps the remove button visible when the table scrolls sideways
const STICKY = { position: 'sticky', right: 0, background: 'var(--surface)', padding: '0 6px' } as const
const MODEL_LABEL: Record<string, string> = {
  build_to_sell: 'Build-to-sell', develop_and_sell: 'Develop & sell', build_to_rent: 'Build-to-rent',
  acquire_and_hold: 'Acquire & hold', value_add: 'Value-add',
}

export default function Portfolio() {
  const nav = useNavigate()
  const { user } = useAuth()
  const [removing, setRemoving] = useState<number | null>(null)
  const [removeError, setRemoveError] = useState<string | null>(null)
  const { data, error } = useFetch<Json>('/api/portfolio')
  // Signed-in users choose which projects to keep; guest workspaces cannot remove projects.
  const remove = async (p: Json) => {
    const msg = [tr('Remove this project permanently?'), p.name, tr('Its assumptions, chat, documents and history will be deleted. This cannot be undone.')]
    if (!confirm(msg.join('\n\n'))) return
    setRemoving(p.id); setRemoveError(null)
    try { await api.del(`/api/projects/${p.id}`); notifyProjectChanged(null) } catch (e) { setRemoveError((e as Error).message) } finally { setRemoving(null) }
  }
  if (error) return <Callout tone="bad">{error}</Callout>
  if (!data) return <Loading label="Loading portfolio…" />
  const t = data.totals || {}
  const projects: Json[] = data.projects || []
  const alerts: Json[] = data.alerts || []
  const cur = projects[0]?.currency || 'MXN'
  const conc = Object.entries(data.concentration_by_area || {}).map(([k, v]) => ({ name: k, share: v as number }))
    .sort((a, b) => b.share - a.share)
  const irrRows = projects.filter((p) => p.metrics?.equity_irr != null).map((p) => ({
    name: p.name.replace(' (fictional)', ''), irr: p.metrics.equity_irr, id: p.id,
  }))
  const reds = alerts.filter((a) => a.level === 'red').length

  return (
    <div>
      <PageHead eyebrow="Fund overview" title="Portfolio Dashboard"
        actions={<button className="btn primary" onClick={() => nav('/new')}><Plus size={15} /> New investment</button>}>
        Committed capital, projected returns and early warnings across every project. All demo projects are fictional.
      </PageHead>

      <div className="grid g5" style={{ gridTemplateColumns: 'repeat(6, minmax(0,1fr))', marginBottom: 16 }}>
        <Kpi label="Projects" value={projects.length} sub={`${projects.filter((p) => p.in_portfolio).length} in portfolio`} />
        <Kpi label="Committed equity" value={money(t.equity, cur)} sub="planned contributions" />
        <Kpi label="Peak debt" value={money(t.debt, cur)} sub="sum of project peaks" />
        <Kpi label="Total GDV" value={money(t.gdv, cur)} sub="gross development value" />
        <Kpi label="Projected profit" value={money(t.profit, cur)} sub={`on ${money(t.total_cost, cur)} cost`} />
        <Kpi label="Weighted MOIC" value={multiple(data.weighted_moic)} sub="distributions / equity" />
      </div>

      <div className="grid g3" style={{ marginBottom: 16 }}>
        <Card title="Early-warning dashboard" className="span2"
          sub={alerts.length ? `${reds} critical · ${alerts.length - reds} watch` : 'No alerts'}>
          {alerts.length === 0 ? <Callout tone="good">No construction, sales, liquidity, maturity or covenant alerts.</Callout> : (
            <table className="t">
              <thead><tr><th>Level</th><th>Project</th><th>Area</th><th>Message</th><th /></tr></thead>
              <tbody>
                {alerts.map((a, i) => (
                  <tr key={i}>
                    <td><StatusBadge level={a.level}>{a.level === 'red' ? 'Critical' : 'Watch'}</StatusBadge></td>
                    <td><Link to={`/p/${a.project_id}/model`}>{a.project}</Link></td>
                    <td>{a.area}</td>
                    <td>{a.message}</td>
                    <td className="right"><Link to={`/p/${a.project_id}/asset`} className="small">Review →</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title="Equity concentration by area" sub="share of committed equity">
          <ResponsiveContainer width="100%" height={Math.max(140, conc.length * 44)}>
            <BarChart data={conc} layout="vertical" margin={{ left: 0, right: 30, top: 4, bottom: 4 }}>
              <CartesianGrid stroke={GRID} horizontal={false} />
              <XAxis type="number" tickFormatter={(v) => pct(v, 0)} tick={{ fill: AXIS, fontSize: 11 }} domain={[0, 1]} />
              <YAxis type="category" dataKey="name" width={120} tick={{ fill: AXIS, fontSize: 11 }} />
              <Tooltip content={<ChartTip fmt={(v) => pct(v)} />} cursor={{ fill: 'rgba(42,120,214,.06)' }} />
              <Bar dataKey="share" name="Equity share" fill={SERIES[0]} radius={[0, 4, 4, 0]} barSize={16} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid g3">
        <Card title="Projects" className="span2" bodyClass="">
          {removeError && <Callout tone="bad">{removeError}</Callout>}
          <div className="table-wrap">
            <table className="t">
              <thead>
                <tr><th>Project</th><th>Neighborhood</th><th>Model</th><th>Status</th><th className="num">Equity IRR</th>
                  <th className="num">MOIC</th><th className="num">Profit</th><th className="num">GDV</th><th className="num">Alerts</th><th>Model</th>{user && <th style={{ position: 'sticky', right: 0 }} />}</tr>
              </thead>
              <tbody>
                {projects.map((p) => {
                  const m = p.metrics || {}
                  return (
                    <tr key={p.id}>
                      <td><Link to={`/p/${p.id}/model`} style={{ fontWeight: 600 }}>{p.name}</Link>{p.demo && <span className="badge demo" style={{ marginLeft: 6 }}>fictional</span>}</td>
                      <td>{p.neighborhood || '—'}</td>
                      <td>{MODEL_LABEL[p.business_model] || p.business_model}</td>
                      <td><span className="badge">{p.status}</span></td>
                      <td className="num" style={{ color: m.equity_irr != null && m.equity_irr < HURDLE ? 'var(--critical)' : undefined }}>{pct(m.equity_irr)}</td>
                      <td className="num">{multiple(m.moic)}</td>
                      <td className="num">{money(m.profit, p.currency || cur)}</td>
                      <td className="num">{money(m.gdv, p.currency || cur)}</td>
                      <td className="num">{p.alerts || 0}</td>
                      <td>{p.model_status === 'ok' ? <StatusBadge level="good">complete</StatusBadge> : <StatusBadge level="amber">incomplete</StatusBadge>}</td>
                      {user && (
                        <td className="right" style={STICKY}>
                          <button className="btn ghost sm" onClick={() => remove(p)} disabled={removing === p.id} title="Remove project" aria-label={`Remove ${p.name}`}>
                            {removing === p.id ? <span className="spinner" /> : <Trash2 size={14} />}
                          </button>
                        </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Equity IRR vs 18% hurdle" sub="base case, from the deterministic engine">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={irrRows} margin={{ left: 0, right: 8, top: 8, bottom: 4 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="name" tick={{ fill: AXIS, fontSize: 10 }} interval={0} />
              <YAxis tickFormatter={(v) => pct(v, 0)} tick={{ fill: AXIS, fontSize: 11 }} width={40} />
              <Tooltip content={<ChartTip fmt={(v) => pct(v)} />} cursor={{ fill: 'rgba(42,120,214,.06)' }} />
              <ReferenceLine y={HURDLE} stroke="var(--critical)" strokeDasharray="4 3" label={{ value: 'Hurdle 18%', fill: AXIS, fontSize: 11, position: 'insideTopRight' }} />
              <Bar dataKey="irr" name="Equity IRR" radius={[4, 4, 0, 0]} barSize={28} onClick={(d: Json) => nav(`/p/${d.id}/model`)} style={{ cursor: 'pointer' }}>
                {irrRows.map((r) => <Cell key={r.id} fill={SERIES[0]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="tiny muted">Bars below the dashed line do not clear the fund's equity hurdle.</div>
        </Card>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { AlertTriangle, Bot, CheckCircle2, Lightbulb, Package } from 'lucide-react'
import { api, notifyProjectChanged, type Json } from '../../api'
import { useProject } from '../../components/Layout'
import { Callout, Card, Kpi, Loading, ModelIncomplete, PageHead } from '../../components/ui'
import { money, pct } from '../../format'
import { useFetch } from '../../state'

const RISK: Record<string, string> = { low: 'good', medium: 'warn', high: 'bad' }

function dPts(x: number | null | undefined) { return x == null ? '—' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(2)} pts` }
function dMoney(x: number | null | undefined, cur: string) { return x == null ? '—' : `${x >= 0 ? '+' : '−'}${money(Math.abs(x), cur)}` }

export default function Advisor() {
  const { data } = useProject()
  const p = data.project
  const cur = p.profile.currency || 'MXN'
  const { data: rec, loading } = useFetch<Json>(`/api/projects/${p.id}/recommendations`)
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [plan, setPlan] = useState<Json>(null)

  const apply = async (body: Json, label: string) => {
    setBusy(label); setMsg(null)
    try {
      const r = await api.post(`/api/projects/${p.id}/recommendations/apply`, body)
      notifyProjectChanged(p.id)
      setMsg(r.rejected?.length ? `Some changes were rejected: ${r.rejected[0].error}` : `Applied: ${label}. Use Undo (top bar) to revert.`)
    } catch (e) { setMsg((e as Error).message) } finally { setBusy(null) }
  }
  const commentary = async () => {
    setBusy('plan')
    try { setPlan(await api.post(`/api/projects/${p.id}/recommendations/commentary`)) } catch (e) { setMsg((e as Error).message) } finally { setBusy(null) }
  }

  if (data.results?.status !== 'ok') return <div><PageHead eyebrow="Advisor" title="Recommendations" /><ModelIncomplete results={data.results} /></div>
  if (!rec || loading && !rec) return <Loading label="Testing improvement levers on the model…" />
  const b = rec.base

  return (
    <div>
      <PageHead eyebrow="Advisor" title="Recommendations to improve the project"
        actions={<button className="btn primary" disabled={busy === 'plan'} onClick={commentary}><Bot size={15} /> {busy === 'plan' ? 'Writing plan…' : 'AI action plan'}</button>}>
        TerraMind tests concrete levers on the full financial model and ranks them by their computed effect. Issues that block the
        investment come first. Apply any lever with one click (it is audited and can be undone), or ask the assistant to explain it.
      </PageHead>

      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Kpi label="Equity IRR today" value={pct(b.equity_irr)} hero />
        <Kpi label="Profit today" value={money(b.profit, cur)} />
        <Kpi label="NPV today" value={money(b.npv, cur)} />
        <Kpi label="Peak equity today" value={money(b.peak_equity, cur)} />
      </div>

      {rec.issues?.length > 0 && (
        <Callout tone="bad"><b>Issues to resolve:</b><ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{rec.issues.map((i: Json, k: number) => <li key={k}>{i.detail}</li>)}</ul></Callout>
      )}
      {msg && <div style={{ marginTop: 10 }}><Callout tone="info">{msg}</Callout></div>}

      {rec.package && (
        <Card className="" title={<span className="row" style={{ gap: 8 }}><Package size={16} /> Recommended package</span>}
          sub="The top levers that touch different inputs, tested together (high-risk levers excluded)"
          actions={<button className="btn primary sm" disabled={!!busy} onClick={() => apply({ package: true }, 'recommended package')}>Apply package</button>}>
          <div className="row wrap" style={{ gap: 18 }}>
            <div className="grow small">{rec.package.titles.map((t: string, i: number) => <div key={i}>• {t}</div>)}</div>
            <div className="kpi" style={{ padding: 0 }}><div className="label">Equity IRR</div><div className="value" style={{ color: 'var(--good-text)' }}>{pct(rec.package.after.equity_irr)}</div><div className="sub">{dPts(rec.package.delta.equity_irr)}</div></div>
            <div className="kpi" style={{ padding: 0 }}><div className="label">Profit</div><div className="value">{money(rec.package.after.profit, cur)}</div><div className="sub">{dMoney(rec.package.delta.profit, cur)}</div></div>
          </div>
        </Card>
      )}

      {plan && (
        <Card className="" title={<span className="row" style={{ gap: 8 }}><Bot size={16} /> AI action plan</span>} sub="Written by the Improvement Advisor from the computed levers (it does not compute numbers)">
          <p style={{ fontWeight: 600 }}>{plan.headline}</p>
          {plan.priorities?.map((pr: Json, i: number) => (
            <div key={i} className="callout" style={{ marginBottom: 8, display: 'block' }}>
              <div style={{ fontWeight: 600 }}>{i + 1}. {rec.levers.find((l: Json) => l.id === pr.lever_id)?.title || pr.lever_id}</div>
              <div className="small"><b>Why:</b> {pr.why}</div>
              <div className="small"><b>How:</b> {pr.how_to_execute}</div>
              <div className="small"><b>Risk:</b> {pr.main_risk}</div>
            </div>
          ))}
          <div className="grid g3">
            {[['Quick wins', plan.quick_wins], ['Avoid', plan.avoid], ['Data that would help', plan.data_gaps]].map(([t, items]) => (
              <div key={t as string}><div className="small" style={{ fontWeight: 600 }}>{t}</div><ul className="small" style={{ paddingLeft: 16 }}>{(items as string[] || []).map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            ))}
          </div>
          {plan.turn_usage && <div className="tiny muted">cost ${plan.turn_usage.total.cost_usd.toFixed(4)}</div>}
        </Card>
      )}

      <Card className="" title={<span className="row" style={{ gap: 8 }}><Lightbulb size={16} /> Levers tested on the model</span>} sub={rec.note}>
        <div className="col" style={{ gap: 10 }}>
          {rec.levers.map((lv: Json) => (
            <div key={lv.id} className="card flat" style={{ padding: 12, borderLeft: lv.fixes?.length ? '3px solid var(--critical)' : undefined }}>
              <div className="row between wrap" style={{ gap: 12, alignItems: 'flex-start' }}>
                <div className="grow" style={{ minWidth: 280 }}>
                  <div className="row" style={{ gap: 8 }}>
                    <span style={{ fontWeight: 600 }}>{lv.title}</span>
                    <span className="badge">{lv.category}</span>
                    <span className={`badge ${RISK[lv.risk]}`}>{lv.risk} risk</span>
                  </div>
                  <div className="small muted" style={{ marginTop: 4 }}>{lv.note}</div>
                  {lv.fixes?.length > 0 && <div className="small" style={{ color: 'var(--good-text)', marginTop: 4 }}><CheckCircle2 size={12} /> Addresses: {lv.fixes.join('; ')}</div>}
                  {lv.remaining_issues?.length > 0 && <div className="tiny" style={{ color: 'var(--warning-text)', marginTop: 2 }}><AlertTriangle size={11} /> Still open after this change: {lv.remaining_issues.join('; ')}</div>}
                </div>
                <div className="row" style={{ gap: 18 }}>
                  <div style={{ textAlign: 'right' }}><div className="tiny muted">Equity IRR</div><div className="num" style={{ fontWeight: 650, color: (lv.delta.equity_irr ?? 0) >= 0 ? 'var(--good-text)' : 'var(--critical)' }}>{dPts(lv.delta.equity_irr)}</div></div>
                  <div style={{ textAlign: 'right' }}><div className="tiny muted">Profit</div><div className="num">{dMoney(lv.delta.profit, cur)}</div></div>
                  <div style={{ textAlign: 'right' }}><div className="tiny muted">Peak equity</div><div className="num">{dMoney(lv.delta.peak_equity, cur)}</div></div>
                  <button className="btn sm primary" disabled={!!busy} onClick={() => apply({ lever_id: lv.id }, lv.title)}>{busy === lv.title ? 'Applying…' : 'Apply'}</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

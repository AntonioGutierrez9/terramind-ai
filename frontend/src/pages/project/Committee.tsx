import { useState } from 'react'
import { AlertTriangle, ArrowRight, Gavel, Printer, ShieldAlert, Users } from 'lucide-react'
import { useProject } from '../../components/Layout'
import { Callout, Card, Loading, PageHead } from '../../components/ui'
import { Elapsed, METRIC_LABELS, UsageLine, fmtMetric, shortDate } from '../../components/c/helpers'
import { api, type Json } from '../../api'
import { money, num } from '../../format'
import { useFetch } from '../../state'

const REC_TONE: Record<string, string> = {
  Invest: 'good', 'Invest with conditions': 'warn', Reject: 'bad', 'Insufficient information': '',
}
const SEV: Record<string, string> = { high: 'bad', medium: 'warn', low: '' }
const KEY_METRICS = ['total_cost', 'gdv', 'profit', 'net_margin', 'profit_on_cost', 'project_irr', 'equity_irr', 'moic', 'npv',
  'peak_equity', 'ltc', 'ltv', 'duration_months', 'funding_gap', 'investor_irr', 'sponsor_irr', 'dscr', 'yield_on_cost']

export default function Committee() {
  const { data } = useProject()
  const pid = data.project.id
  const cur = data.project.profile.currency || 'MXN'
  const { data: memoRec, loading, setData } = useFetch<Json>(`/api/projects/${pid}/committee`)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [usage, setUsage] = useState<Json>(null)
  const res = data.results
  const ok = res?.status === 'ok'

  const convene = async () => {
    setBusy(true); setErr(null); setUsage(null)
    try {
      const r = await api.post(`/api/projects/${pid}/committee`)
      if (r.status === 'limit_reached') { setErr(`Limit reached: ${r.detail}`); return }
      setUsage(r.turn_usage)
      setData(await api.get(`/api/projects/${pid}/committee`))
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  const memo = memoRec?.memo
  const packet = memoRec?.metrics || {}
  return (
    <>
      <PageHead eyebrow="Step 8" title="Investment Committee"
        actions={<>
          {memo && <button className="btn" onClick={() => window.print()}><Printer size={14} /> Print / save as PDF</button>}
          <button className="btn primary" onClick={convene} disabled={busy}>{busy ? <span className="spinner" /> : <Gavel size={14} />} Convene Investment Committee</button>
        </>}>
        Two specialist agents challenge the underwriting before the chair issues a recommendation. Every financial figure comes from the deterministic engine; code-level guardrails can override the chair.
      </PageHead>

      <div className="col" style={{ gap: 16 }}>
        <Card title="Committee process" bodyClass="">
          <div className="row wrap" style={{ gap: 10 }}>
            <Step n={1} title="Evidence packet" text="Engine metrics, covenants, scenarios, sensitivities, assumption provenance" active={busy} />
            <ArrowRight size={16} color="var(--text-3)" />
            <Step n={2} title="Challengers (parallel)" text="Underwriting challenger + Capital & risk challenger" active={busy} />
            <ArrowRight size={16} color="var(--text-3)" />
            <Step n={3} title="Chair" text="Invest · Invest with conditions · Reject · Insufficient information" active={busy} />
            <ArrowRight size={16} color="var(--text-3)" />
            <Step n={4} title="Guardrails" text="Covenant / funding-gap / compliance overrides + number check" active={busy} />
          </div>
          {busy && <div className="small muted" style={{ marginTop: 10 }}><span className="spinner" /> Committee in session… <Elapsed /> (usually 30–60 s)</div>}
          {usage && <div style={{ marginTop: 8 }}><UsageLine u={usage} /></div>}
          {err && <div style={{ marginTop: 10 }}><Callout tone="bad">{err}</Callout></div>}
          {!ok && <div style={{ marginTop: 10 }}><Callout tone="warn">The financial model is incomplete, so the committee will return <b>Insufficient information</b> without calling the language model (no tokens spent). Missing: {(res?.missing_labels || []).join(', ')}.</Callout></div>}
        </Card>

        {loading && !memoRec ? <Loading /> : !memo ? (
          <Card><div className="empty"><Users size={28} /><div style={{ marginTop: 8 }}>No committee memo yet. Convene the committee to generate one.</div></div></Card>
        ) : (
          <div className="card" style={{ padding: 0 }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', background: 'linear-gradient(180deg, var(--navy-50), #fff)' }}>
              <div className="row between" style={{ alignItems: 'flex-start' }}>
                <div>
                  <div className="tiny muted" style={{ textTransform: 'uppercase', letterSpacing: '.1em' }}>Investment Committee Memorandum</div>
                  <h1 style={{ marginTop: 4 }}>{data.project.name}</h1>
                  <div className="small muted">{[data.project.profile.neighborhood, data.project.profile.city].filter(Boolean).join(', ')} · {shortDate(memoRec.created_at)} · {memo.llm_used ? 'TerraMind IC agents (gpt-6-luna)' : 'deterministic pre-check (no LLM)'}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="tiny muted">Recommendation</div>
                  <span className={`badge ${REC_TONE[memo.recommendation] ?? ''}`} style={{ fontSize: 15, padding: '6px 14px', marginTop: 4 }}>{memo.recommendation}</span>
                </div>
              </div>
              {data.project.profile.demo && <div style={{ marginTop: 10 }}><Callout tone="warn">Fictional demonstration case — all inputs are illustrative.</Callout></div>}
            </div>
            <div style={{ padding: '18px 24px' }} className="col">
              <Section title="Executive summary"><p>{memo.summary}</p></Section>

              {memo.guardrail_adjustments?.length > 0 && (
                <Callout tone="bad" icon={<ShieldAlert size={16} style={{ flexShrink: 0, marginTop: 1 }} />}>
                  <b>Deterministic guardrails changed the chair's recommendation:</b>
                  <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{memo.guardrail_adjustments.map((g: string, i: number) => <li key={i}>{g}</li>)}</ul>
                </Callout>
              )}

              <div className="grid g2">
                <Section title="Key metrics" note="All figures from the deterministic engine (live model).">
                  {ok ? (
                    <table className="t"><tbody>
                      {KEY_METRICS.filter((k) => res.metrics[k] != null).map((k) => (
                        <tr key={k}><td>{METRIC_LABELS[k] || k}</td><td className="num">{fmtMetric(k, res.metrics[k], cur)}</td></tr>
                      ))}
                    </tbody></table>
                  ) : <div className="small muted">Model incomplete.</div>}
                  <div className="tiny muted" style={{ marginTop: 6 }}>Memo snapshot taken {shortDate(memoRec.created_at)}; if assumptions changed since, re-convene the committee.</div>
                </Section>
                <div className="col">
                  {packet.scenarios?.length > 0 && (
                    <Section title="Scenarios (engine, at memo date)">
                      <table className="t">
                        <thead><tr><th>Scenario</th><th className="num">Equity IRR</th><th className="num">Profit</th></tr></thead>
                        <tbody>{packet.scenarios.map((s: Json) => (
                          <tr key={s.name}><td>{s.name}</td><td className="num">{s.equity_irr_pct == null ? '—' : `${s.equity_irr_pct.toFixed(1)}%`}</td><td className="num">{money(s.profit, cur)}</td></tr>
                        ))}</tbody>
                      </table>
                    </Section>
                  )}
                  {packet.covenants?.length > 0 && (
                    <Section title="Covenants">
                      <table className="t"><tbody>{packet.covenants.map((c: Json) => (
                        <tr key={c.name}><td>{c.name}</td><td className="num">{num(c.actual, 1)} vs {num(c.limit, 1)}</td>
                          <td><span className={`badge ${c.ok ? 'good' : 'bad'}`}>{c.ok ? 'OK' : 'Breach'}</span></td></tr>
                      ))}</tbody></table>
                    </Section>
                  )}
                  {packet.assumption_provenance && (
                    <Section title="Assumption provenance">
                      <div className="row wrap" style={{ gap: 6 }}>
                        {Object.entries(packet.assumption_provenance).map(([k, v]) => <span key={k} className="badge">{k}: {String(v)}</span>)}
                        {packet.pending_research_proposals > 0 && <span className="badge pending">pending proposals: {packet.pending_research_proposals}</span>}
                      </div>
                    </Section>
                  )}
                </div>
              </div>

              <Section title="Rationale"><p>{memo.rationale}</p></Section>
              <div className="grid g2">
                <Section title="Conditions precedent">
                  {memo.conditions?.length ? <ol style={{ margin: 0, paddingLeft: 18 }}>{memo.conditions.map((c: string, i: number) => <li key={i} style={{ marginBottom: 4 }}>{c}</li>)}</ol> : <div className="small muted">None.</div>}
                </Section>
                <Section title="Required diligence">
                  {memo.required_diligence?.length ? <ul style={{ margin: 0, paddingLeft: 18 }}>{memo.required_diligence.map((c: string, i: number) => <li key={i} style={{ marginBottom: 4 }}>{c}</li>)}</ul> : <div className="small muted">None.</div>}
                </Section>
              </div>
              {memo.key_risks?.length > 0 && (
                <Section title="Key risks & mitigations">
                  <table className="t"><thead><tr><th style={{ width: '45%' }}>Risk</th><th>Mitigation</th></tr></thead>
                    <tbody>{memo.key_risks.map((r: Json, i: number) => <tr key={i}><td>{r.risk}</td><td>{r.mitigation}</td></tr>)}</tbody></table>
                </Section>
              )}

              {memo.challengers && (memo.challengers.underwriting || memo.challengers.capital_risk) && (
                <div className="grid g2">
                  <Challenger title="Underwriting challenger" rep={memo.challengers.underwriting} />
                  <Challenger title="Capital & risk challenger" rep={memo.challengers.capital_risk} />
                </div>
              )}

              {memo.unverified_numbers?.length > 0 && (
                <Callout tone="warn" icon={<AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1 }} />}>
                  <b>Number check:</b> these figures in the AI-written text did not match any engine figure in the evidence packet: {memo.unverified_numbers.join(', ')}. Treat them as unverified.
                </Callout>
              )}
              {memo.unverified_numbers && memo.unverified_numbers.length === 0 && memo.llm_used && (
                <Callout tone="good">Number check passed: every percentage in the memo text matches an engine figure.</Callout>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  )
}

function Step({ n, title, text, active }: { n: number; title: string; text: string; active: boolean }) {
  return (
    <div className="card flat" style={{ padding: '10px 12px', flex: '1 1 180px', borderColor: active ? 'var(--accent)' : undefined }}>
      <div className="tiny muted">Step {n}</div>
      <div style={{ fontWeight: 620 }}>{title}</div>
      <div className="tiny muted">{text}</div>
    </div>
  )
}

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 style={{ textTransform: 'uppercase', fontSize: 11.5, letterSpacing: '.08em', color: 'var(--navy-700)', marginBottom: 6 }}>{title}</h3>
      {note && <div className="tiny muted" style={{ marginBottom: 6 }}>{note}</div>}
      {children}
    </div>
  )
}

function Challenger({ title, rep }: { title: string; rep: Json }) {
  if (!rep) return null
  return (
    <div className="card flat" style={{ padding: 14 }}>
      <h3 style={{ marginBottom: 8 }}>{title}</h3>
      {rep.concerns?.map((c: Json, i: number) => (
        <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
          <div className="row" style={{ gap: 6 }}><span className={`badge ${SEV[c.severity] ?? ''}`}>{c.severity}</span><b className="small">{c.area}</b></div>
          <div className="small" style={{ marginTop: 3 }}>{c.issue}</div>
          <div className="tiny muted">Evidence: {c.evidence}</div>
          <div className="tiny" style={{ color: 'var(--navy-600)' }}>Test: {c.suggested_test}</div>
        </div>
      ))}
      {rep.strengths?.length > 0 && <div className="small" style={{ marginTop: 8 }}><b>Strengths:</b> {rep.strengths.join(' · ')}</div>}
    </div>
  )
}

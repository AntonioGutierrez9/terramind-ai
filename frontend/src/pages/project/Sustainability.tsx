import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { ExternalLink, Leaf, Play, Sparkles } from 'lucide-react'
import { useProject } from '../../components/Layout'
import { Callout, Card, ChartTip, Kpi, Legend, Loading, ModelIncomplete, PageHead } from '../../components/ui'
import { Elapsed, UsageLine } from '../../components/c/helpers'
import { api, applyChanges, notifyProjectChanged, type Json } from '../../api'
import { AXIS, GRID, SERIES, money, num, pct } from '../../format'
import { useFetch } from '../../state'

const EDITABLE = ['capex', 'savings_annual', 'sale_premium_pct', 'rent_premium_pct'] as const

export default function Sustainability() {
  const { data } = useProject()
  const pid = data.project.id
  const cur = data.project.profile.currency || 'MXN'
  const { data: ev, loading } = useFetch<Json>(`/api/projects/${pid}/sustainability`)
  const { data: research, reload: reloadResearch } = useFetch<Json>(`/api/projects/${pid}/research`)
  const list: Json[] = data.project.assumptions.sustainability_measures || []
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const saveList = async (next: Json[]) => {
    setSaving(true); setErr(null)
    try {
      const r = await applyChanges(pid, [{ key: 'sustainability_measures', value: next }], { reason: 'sustainability measures edited' })
      if (r.rejected?.length) setErr(r.rejected[0].error)
    } catch (e) { setErr((e as Error).message) } finally { setSaving(false) }
  }
  const toggle = (key: string) => saveList(list.map((m) => (m.key === key ? { ...m, enabled: !m.enabled } : m)))
  const editField = (key: string, field: string, value: string) => {
    const v = Number(value)
    if (Number.isNaN(v)) return
    saveList(list.map((m) => (m.key === key ? { ...m, [field]: v } : m)))
  }

  if (!list.length) return (
    <>
      <PageHead eyebrow="Step 7" title="Sustainability optimization" />
      <Callout>No sustainability measures are defined for this project yet.</Callout>
    </>
  )
  if (loading && !ev) return <Loading />
  const rows: Json[] = ev?.measures || []
  const base = ev?.base_metrics
  const withM = ev?.with_enabled_metrics
  const enabled = rows.filter((m) => m.enabled)
  const capex = enabled.reduce((s, m) => s + (m.capex || 0), 0)
  const co2 = enabled.reduce((s, m) => s + (m.co2_t_annual || 0), 0)
  const frontier = rows.map((m) => ({ name: m.name, capex: m.capex, co2: m.co2_t_life + (m.embodied_co2_t || 0), enabled: m.enabled }))
  const irrBars = rows.map((m) => ({ name: m.name.split('(')[0].trim(), delta: (m.delta_equity_irr ?? 0) * 100 }))

  return (
    <>
      <PageHead eyebrow="Step 7" title="Sustainability optimization">
        Evaluate sustainable construction measures: their cost, the savings and emissions they deliver, and who captures the benefit. Every return effect comes from re-running the full development model.
      </PageHead>
      <ModelIncomplete results={data.results} />
      <div className="col" style={{ gap: 16 }}>
        <Callout tone={data.mode === 'sale' ? 'warn' : 'good'} icon={<Leaf size={16} style={{ flexShrink: 0, marginTop: 1 }} />}>
          <b>Who benefits?</b> {ev?.beneficiary_note}
        </Callout>
        <div className="grid g4">
          <Kpi label="Enabled measures capex" value={money(capex, cur)} sub={`${enabled.length} of ${rows.length} measures`} />
          <Kpi label="Operating CO₂ avoided" value={`${num(co2)} t/yr`} sub="preliminary estimate" tone="good" />
          <Kpi label="Equity IRR without → with" value={`${pct(base?.equity_irr)} → ${pct(withM?.equity_irr)}`}
            sub={base && withM ? `${((withM.equity_irr - base.equity_irr) * 100).toFixed(2)} pts` : undefined}
            tone={base && withM ? (withM.equity_irr >= base.equity_irr ? 'good' : 'bad') : undefined} />
          <Kpi label="Profit impact (developer)" value={base && withM ? money(withM.profit - base.profit, cur) : '—'}
            tone={base && withM ? (withM.profit >= base.profit ? 'good' : 'bad') : undefined} sub="vs. no measures" />
        </div>

        <Card title="Measures" sub="Toggle a measure to include it in the project model. Values are preliminary estimates, not engineering results."
          actions={saving ? <span className="small muted"><span className="spinner" /> recalculating…</span> : undefined}>
          {err && <Callout tone="bad">{err}</Callout>}
          <div className="table-wrap">
            <table className="t">
              <thead><tr>
                <th>On</th><th>Measure</th><th className="num">Capex</th><th className="num">Savings / yr</th>
                <th className="num">{data.mode === 'sale' ? 'Sale premium %' : 'Rent premium %'}</th><th className="num">Payback</th>
                <th className="num">Lifecycle NPV</th><th className="num">Lifetime CO₂ (t)</th><th className="num">Δ Equity IRR</th><th className="num">Δ Profit</th><th>Status</th>
              </tr></thead>
              <tbody>
                {rows.map((m) => {
                  const premKey = data.mode === 'sale' ? 'sale_premium_pct' : 'rent_premium_pct'
                  return (
                    <tr key={m.key}>
                      <td><input type="checkbox" checked={!!m.enabled} disabled={saving} onChange={() => toggle(m.key)} aria-label={`Enable ${m.name}`} /></td>
                      <td><div style={{ fontWeight: 600 }}>{m.name}</div><div className="tiny muted">{m.life_years} yr life · beneficiary: {m.beneficiary}</div></td>
                      <td className="num"><NumCell value={m.capex} onSave={(v) => editField(m.key, 'capex', v)} /></td>
                      <td className="num"><NumCell value={m.savings_annual} onSave={(v) => editField(m.key, 'savings_annual', v)} /></td>
                      <td className="num"><NumCell value={m[premKey]} digits={2} onSave={(v) => editField(m.key, premKey, v)} /></td>
                      <td className="num">{m.simple_payback_years ? `${m.simple_payback_years.toFixed(1)} yr` : '—'}</td>
                      <td className="num" style={{ color: m.lifecycle_npv < 0 ? 'var(--critical)' : undefined }}>{money(m.lifecycle_npv, cur)}</td>
                      <td className="num">{num(m.co2_t_life + (m.embodied_co2_t || 0))}</td>
                      <td className="num">{m.delta_equity_irr == null ? '—' : `${(m.delta_equity_irr * 100).toFixed(2)} pts`}</td>
                      <td className="num">{money(m.delta_profit, cur)}</td>
                      <td><span className="badge warn" title={m.source}>{m.status === 'verified' ? 'verified' : 'preliminary estimate'}</span>
                        <details className="tiny muted" style={{ maxWidth: 220 }}><summary style={{ cursor: 'pointer' }}>source</summary>{m.source}</details></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="tiny muted" style={{ marginTop: 8 }}>
            Editable: {EDITABLE.join(', ').replace(/_/g, ' ')} — click a number to change it. Lifecycle NPV is the owner-of-the-asset view at the project discount rate; Δ IRR / Δ profit are the developer impact from the full model with only that measure enabled.
          </div>
        </Card>

        <div className="grid g2">
          <Card title="Investment frontier" sub="Capex vs lifetime CO₂ avoided (operating + embodied), one dot per measure">
            <ResponsiveContainer width="100%" height={280}>
              <ScatterChart margin={{ top: 16, right: 24, bottom: 8, left: 8 }}>
                <CartesianGrid stroke={GRID} />
                <XAxis type="number" dataKey="capex" name="Capex" tickFormatter={(v) => `${(v / 1e6).toFixed(1)}M`} stroke={AXIS} fontSize={11} />
                <YAxis type="number" dataKey="co2" name="Lifetime CO₂" unit=" t" stroke={AXIS} fontSize={11} width={64} />
                <ZAxis range={[90, 90]} />
                <Tooltip content={<FrontierTip cur={cur} />} />
                <Scatter data={frontier}>
                  {frontier.map((f, i) => <Cell key={i} fill={f.enabled ? SERIES[0] : '#b8c2d1'} stroke="#fff" strokeWidth={2} />)}
                  <LabelList dataKey="name" position="top" fontSize={10} fill="#4a5568" formatter={(v: unknown) => String(v).split(' ')[0]} />
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
            <Legend items={[{ label: 'Enabled', color: SERIES[0] }, { label: 'Not enabled', color: '#b8c2d1' }]} />
          </Card>
          <Card title="Developer equity IRR impact" sub="Change in equity IRR (pts) with each measure alone">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={irrBars} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
                <CartesianGrid stroke={GRID} horizontal={false} />
                <XAxis type="number" stroke={AXIS} fontSize={11} tickFormatter={(v) => `${v.toFixed(2)}`} />
                <YAxis type="category" dataKey="name" width={150} stroke={AXIS} fontSize={11} />
                <ReferenceLine x={0} stroke="#9aa5b6" />
                <Tooltip content={<ChartTip fmt={(v) => `${v.toFixed(2)} pts`} />} cursor={{ fill: 'rgba(42,120,214,.06)' }} />
                <Bar dataKey="delta" name="Δ equity IRR" barSize={12} radius={[0, 4, 4, 0]}>
                  {irrBars.map((b, i) => <Cell key={i} fill={b.delta >= 0 ? SERIES[2] : SERIES[7]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>

        <Optimizer pid={pid} cur={cur} list={list} onEnable={saveList} />
        <ResearchCard pid={pid} research={research} onDone={reloadResearch} />
      </div>
    </>
  )
}

function NumCell({ value, onSave, digits = 0 }: { value: number; onSave: (v: string) => void; digits?: number }) {
  const [edit, setEdit] = useState(false)
  const [draft, setDraft] = useState('')
  if (!edit) return <span style={{ cursor: 'pointer', borderBottom: '1px dashed var(--border-strong)' }} onClick={() => { setDraft(String(value ?? 0)); setEdit(true) }}>{num(value, digits)}</span>
  return (
    <input className="input" style={{ width: 100, height: 26 }} autoFocus value={draft} onChange={(e) => setDraft(e.target.value)}
      onBlur={() => { setEdit(false); if (draft !== String(value)) onSave(draft) }}
      onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') setEdit(false) }} />
  )
}

function FrontierTip({ active, payload, cur }: { active?: boolean; payload?: Json[]; cur: string }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="tt">{p.name ?? (p.keys?.length ? p.keys.join(', ') : 'No measures')}</div>
      <div>Capex: <b>{money(p.capex, cur)}</b></div>
      <div>Lifetime CO₂: <b>{num(p.co2 ?? p.co2_t_life)} t</b></div>
      {p.lifecycle_npv != null && <div>Lifecycle NPV: <b>{money(p.lifecycle_npv, cur)}</b></div>}
    </div>
  )
}

function Optimizer({ pid, cur, list, onEnable }: { pid: number; cur: string; list: Json[]; onEnable: (l: Json[]) => void }) {
  const total = list.reduce((s, m) => s + (m.capex || 0), 0)
  const [budget, setBudget] = useState(String(Math.round(total / 2 / 1e5) * 1e5))
  const [objective, setObjective] = useState('co2')
  const [res, setRes] = useState<Json>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const run = async () => {
    setBusy(true); setErr(null)
    try { setRes(await api.post(`/api/projects/${pid}/sustainability/optimize`, { budget: Number(budget), objective })) }
    catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const names = Object.fromEntries(list.map((m) => [m.key, m.name]))
  const best = res?.best
  const bestKey = best ? [...best.keys].sort().join('|') : ''
  const pts = (res?.frontier || []).map((f: Json) => ({ ...f, isBest: [...f.keys].sort().join('|') === bestKey }))
  return (
    <Card title="Budget optimizer" sub="Finds the best combination of measures within a capex budget (exhaustive search over every subset).">
      <div className="row wrap" style={{ alignItems: 'flex-end' }}>
        <label className="field" style={{ width: 200 }}>Capex budget ({cur})<input className="input" value={budget} onChange={(e) => setBudget(e.target.value)} /></label>
        <label className="field" style={{ width: 260 }}>Objective
          <select className="input" value={objective} onChange={(e) => setObjective(e.target.value)}>
            <option value="co2">Maximize lifetime CO₂ avoided</option>
            <option value="lifecycle_npv">Maximize owner lifecycle NPV</option>
            <option value="equity_irr">Maximize developer equity IRR (full model)</option>
          </select>
        </label>
        <button className="btn primary" onClick={run} disabled={busy}>{busy ? <span className="spinner" /> : <Sparkles size={14} />} Optimize</button>
        <span className="tiny muted">All measures together cost {money(total, cur)}.</span>
      </div>
      {err && <div style={{ marginTop: 10 }}><Callout tone="bad">{err}</Callout></div>}
      {best && (
        <div className="grid g2" style={{ marginTop: 14 }}>
          <div className="col">
            <Callout tone="good">
              <b>Best combination</b> ({res.evaluated} combinations evaluated): {best.keys.length ? best.keys.map((k: string) => names[k] || k).join(', ') : 'no measures fit the budget'}
            </Callout>
            <table className="t">
              <tbody>
                <tr><td>Capex</td><td className="num">{money(best.capex, cur)}</td></tr>
                <tr><td>Lifetime operating CO₂ avoided</td><td className="num">{num(best.co2_t_life)} t</td></tr>
                <tr><td>Owner lifecycle NPV</td><td className="num">{money(best.lifecycle_npv, cur)}</td></tr>
                {best.equity_irr != null && <tr><td>Developer equity IRR</td><td className="num">{pct(best.equity_irr)}</td></tr>}
              </tbody>
            </table>
            <div><button className="btn accent" onClick={() => onEnable(list.map((m) => ({ ...m, enabled: best.keys.includes(m.key) })))}>Enable this combination</button></div>
          </div>
          <div>
            <ResponsiveContainer width="100%" height={240}>
              <ScatterChart margin={{ top: 10, right: 20, bottom: 4, left: 8 }}>
                <CartesianGrid stroke={GRID} />
                <XAxis type="number" dataKey="capex" tickFormatter={(v) => `${(v / 1e6).toFixed(1)}M`} stroke={AXIS} fontSize={11} name="Capex" />
                <YAxis type="number" dataKey="co2_t_life" stroke={AXIS} fontSize={11} width={60} name="CO₂" />
                <ZAxis range={[36, 36]} />
                <Tooltip content={<FrontierTip cur={cur} />} />
                <Scatter data={pts}>
                  {pts.map((p: Json, i: number) => <Cell key={i} fill={p.isBest ? SERIES[1] : SERIES[0]} fillOpacity={p.isBest ? 1 : 0.35} stroke={p.isBest ? '#fff' : 'none'} strokeWidth={2} />)}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
            <Legend items={[{ label: 'Evaluated combinations within budget', color: SERIES[0] }, { label: 'Best', color: SERIES[1] }]} />
          </div>
        </div>
      )}
    </Card>
  )
}

function ResearchCard({ pid, research, onDone }: { pid: number; research: Json; onDone: () => void }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ tone: 'bad' | 'warn' | 'good'; text: string } | null>(null)
  const [usage, setUsage] = useState<Json>(null)
  const r = research?.sustainability
  const run = async () => {
    setBusy(true); setMsg(null)
    try {
      const res = await api.post(`/api/projects/${pid}/research/sustainability`, {})
      if (res.status === 'limit_reached') setMsg({ tone: 'warn', text: res.detail })
      else { setUsage(res.turn_usage); setMsg({ tone: 'good', text: res.from_cache ? 'Loaded from research cache (no tokens spent).' : 'Research complete.' }) }
      onDone(); notifyProjectChanged(pid)
    } catch (e) { setMsg({ tone: 'bad', text: (e as Error).message }) } finally { setBusy(false) }
  }
  const items: Json[] = r?.payload?.benchmarks || []
  return (
    <Card title="Sustainability research" sub="Documented parameters found by the Sustainability agent (web search). Use them to refine the measure estimates above."
      actions={<button className="btn" onClick={run} disabled={busy}>{busy ? <><span className="spinner" /> Researching… <Elapsed /></> : <><Play size={14} /> Run Sustainability agent</>}</button>}>
      {busy && <div className="small muted" style={{ marginBottom: 8 }}>Web research usually takes 30–60 seconds.</div>}
      {msg && <div style={{ marginBottom: 10 }}><Callout tone={msg.tone}>{msg.text} {usage && <UsageLine u={usage} />}</Callout></div>}
      {!items.length ? <div className="small muted">No sustainability research yet.</div> : (
        <>
          <div className="tiny muted" style={{ marginBottom: 6 }}>{r.from_cache ? 'From cache · ' : ''}{r.created_at?.slice(0, 10)} · {r.request}</div>
          <div className="table-wrap">
            <table className="t">
              <thead><tr><th>Measure</th><th>Item</th><th className="num">Value</th><th>Unit</th><th>Status</th><th>Source</th></tr></thead>
              <tbody>
                {items.map((b, i) => (
                  <tr key={i}>
                    <td>{b.measure_key || '—'}</td><td>{b.item}{b.note && <div className="tiny muted">{b.note}</div>}</td>
                    <td className="num">{b.value == null ? '—' : num(b.value, b.value % 1 ? 2 : 0)}</td><td>{b.unit}</td>
                    <td><span className={`badge ${b.verification === 'published' ? 'good' : b.verification === 'not_found' ? 'bad' : 'warn'}`}>{b.verification}</span></td>
                    <td>{b.source_url ? <a href={b.source_url} target="_blank" rel="noreferrer">{b.source_title || 'link'} <ExternalLink size={11} /></a> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {r.payload.caveats?.length > 0 && <div className="tiny muted" style={{ marginTop: 6 }}>Caveats: {r.payload.caveats.join(' · ')}</div>}
        </>
      )}
      <div style={{ marginTop: 10 }}><Callout tone="warn">All sustainability figures are preliminary estimates for screening — not verified engineering results or energy models.</Callout></div>
    </Card>
  )
}

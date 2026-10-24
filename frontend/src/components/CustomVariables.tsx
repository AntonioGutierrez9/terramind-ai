import { useState } from 'react'
import { Plus, Sparkles, Trash2 } from 'lucide-react'
import { applyChanges, type Json } from '../api'
import { fmtValue } from '../format'
import type { ProjectData } from '../state'
import { Card } from './ui'

export const EFFECTS: Record<string, { label: string; unit: string; hint: string }> = {
  cost_fixed: { label: 'One-off cost', unit: 'currency', hint: 'e.g. a permit consultant, a utility connection' },
  cost_per_area: { label: 'Cost per m² of GBA', unit: 'currency/area', hint: 'e.g. an acoustic upgrade' },
  cost_per_unit: { label: 'Cost per unit', unit: 'currency/unit', hint: 'e.g. a smart-home package' },
  cost_pct_hard: { label: '% of hard cost', unit: '%', hint: 'e.g. a contractor bond' },
  cost_pct_revenue: { label: '% of sales collections', unit: '%', hint: 'e.g. a trust (fideicomiso) fee' },
  cost_monthly: { label: 'Monthly cost', unit: 'currency/month', hint: 'e.g. site security' },
  revenue_fixed: { label: 'One-off income', unit: 'currency', hint: 'e.g. sale of a retail unit' },
  revenue_per_unit: { label: 'Income per unit sold', unit: 'currency/unit', hint: 'e.g. storage units, extra parking' },
  revenue_monthly: { label: 'Monthly income', unit: 'currency/month', hint: 'e.g. rooftop antenna lease' },
  price_pct: { label: '% change to sale price / rent', unit: '%', hint: 'e.g. a view premium' },
  info: { label: 'Tracked only (no effect)', unit: '', hint: 'e.g. the permit consultant firm' },
}
const ANCHORS = [['closing', 'Land closing'], ['sales_start', 'Sales start'], ['construction_start', 'Construction start'], ['delivery', 'Delivery']]

/** User-defined variables for the sections of this page. They change the model deterministically (no AI arithmetic). */
export default function CustomVariables({ data, sections, defaultSection }: { data: ProjectData; sections: string[]; defaultSection: string }) {
  const p = data.project
  const all: Json[] = p.assumptions.custom_variables || []
  const mine = all.filter((v) => sections.includes(v.section))
  const cur = p.profile.currency || 'MXN'
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState<Json>({ label: '', effect: 'cost_fixed', value: '', section: defaultSection, timing: 'construction', anchor: 'construction_start', offset: 0, months: 12 })
  const [edit, setEdit] = useState<Record<string, string>>({})
  const [err, setErr] = useState<string | null>(null)

  const save = async (list: Json[]) => {
    setErr(null)
    const r = await applyChanges(p.id, [{ key: 'custom_variables', value: list }], { reason: 'user-defined variables' })
    if (r.rejected?.length) { setErr(r.rejected[0].error); return false }
    return true
  }
  const add = async () => {
    if (!draft.label.trim()) { setErr('Give the variable a name.'); return }
    if (await save([...all, { ...draft, created_by: 'user' }])) { setAdding(false); setDraft({ ...draft, label: '', value: '' }) }
  }
  const updateValue = async (key: string) => {
    if (await save(all.map((v) => (v.key === key ? { ...v, value: edit[key] } : v)))) setEdit({ ...edit, [key]: undefined as unknown as string })
  }
  const remove = (key: string) => save(all.filter((v) => v.key !== key))
  const needsTiming = ['cost_fixed', 'cost_monthly', 'revenue_fixed', 'revenue_monthly'].includes(draft.effect)

  if (!mine.length && !adding) {
    return (
      <div className="card flat" style={{ padding: '10px 14px', marginTop: 16, display: 'flex', alignItems: 'center', gap: 10, background: 'var(--surface-2)' }}>
        <Sparkles size={15} color="var(--accent)" />
        <span className="small muted grow">Need an input the model doesn't have? Add your own variable here, or just ask the AI assistant ("add a trust fee of 0.5% of sales").</span>
        <button className="btn sm" onClick={() => setAdding(true)}><Plus size={13} /> Add variable</button>
      </div>
    )
  }
  return (
    <Card className="" title="User-defined variables" sub="Inputs added for this project. Each one changes the model through a defined effect, and is audited and undoable."
      actions={!adding && <button className="btn sm" onClick={() => setAdding(true)}><Plus size={13} /> Add variable</button>}>
      {mine.length > 0 && (
        <table className="t">
          <thead><tr><th>Variable</th><th>Effect</th><th className="num">Value</th><th>Added by</th><th /></tr></thead>
          <tbody>
            {mine.map((v) => (
              <tr key={v.key}>
                <td style={{ fontWeight: 550 }}>{v.label}<div className="tiny muted">{v.key}{v.note ? ` · ${v.note}` : ''}</div></td>
                <td className="small">{EFFECTS[v.effect]?.label}</td>
                <td className="num">
                  {edit[v.key] !== undefined ? (
                    <div className="row" style={{ gap: 4, justifyContent: 'flex-end' }}>
                      <input className="input" style={{ width: 120 }} value={edit[v.key]} onChange={(e) => setEdit({ ...edit, [v.key]: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && updateValue(v.key)} />
                      <button className="btn sm primary" onClick={() => updateValue(v.key)}>Save</button>
                    </div>
                  ) : <button className="btn ghost sm" onClick={() => setEdit({ ...edit, [v.key]: String(v.value ?? '') })}>{fmtValue(v.value, v.unit || '', cur)}</button>}
                </td>
                <td><span className={`badge ${v.created_by === 'chatbot' ? 'chatbot' : 'user'}`}>{v.created_by}</span></td>
                <td><button className="btn ghost sm" onClick={() => remove(v.key)}><Trash2 size={13} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {adding && (
        <div className="card flat" style={{ padding: 12, marginTop: 10, background: 'var(--surface-2)' }}>
          <div className="grid g3" style={{ gap: 10 }}>
            <label className="field">Name<input className="input" value={draft.label} placeholder="e.g. Trust (fideicomiso) fee" onChange={(e) => setDraft({ ...draft, label: e.target.value })} /></label>
            <label className="field">How it affects the model
              <select className="input" value={draft.effect} onChange={(e) => setDraft({ ...draft, effect: e.target.value })}>
                {Object.entries(EFFECTS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            </label>
            <label className="field">Value {EFFECTS[draft.effect].unit && <span className="muted">({EFFECTS[draft.effect].unit.replace('currency', cur).replace('area', 'm²')})</span>}
              <input className="input" value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} placeholder={EFFECTS[draft.effect].hint} />
            </label>
            {needsTiming && (
              <>
                {draft.effect === 'cost_fixed' && (
                  <label className="field">Timing
                    <select className="input" value={draft.timing} onChange={(e) => setDraft({ ...draft, timing: e.target.value })}>
                      <option value="construction">Spread over construction</option><option value="anchor">At a milestone</option>
                    </select>
                  </label>
                )}
                {(draft.effect !== 'cost_fixed' || draft.timing === 'anchor') && (
                  <>
                    <label className="field">Starts at
                      <select className="input" value={draft.anchor} onChange={(e) => setDraft({ ...draft, anchor: e.target.value })}>
                        {ANCHORS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                      </select>
                    </label>
                    <label className="field">Offset (months)<input className="input" value={draft.offset} onChange={(e) => setDraft({ ...draft, offset: e.target.value })} /></label>
                  </>
                )}
                {draft.effect.endsWith('monthly') && <label className="field">Months<input className="input" value={draft.months} onChange={(e) => setDraft({ ...draft, months: e.target.value })} /></label>}
              </>
            )}
          </div>
          <div className="row" style={{ marginTop: 10, gap: 6 }}>
            <button className="btn primary sm" onClick={add}>Add to model</button>
            <button className="btn ghost sm" onClick={() => setAdding(false)}>Cancel</button>
            <span className="tiny muted">{EFFECTS[draft.effect].hint}</span>
          </div>
        </div>
      )}
      {err && <div className="small" style={{ color: 'var(--critical)', marginTop: 6 }}>{err}</div>}
    </Card>
  )
}

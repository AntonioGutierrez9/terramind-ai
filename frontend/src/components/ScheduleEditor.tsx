import { useEffect, useState } from 'react'
import { Plus, Save, Trash2 } from 'lucide-react'
import { applyChanges, type Json } from '../api'
import { Card } from './ui'

export interface Col { field: string; label: string; type: 'text' | 'number' | 'anchor' | 'flowtype'; width?: number; placeholder?: string }

const ANCHORS = [['closing', 'Land closing'], ['sales_start', 'Sales start'], ['construction_start', 'Construction start'], ['delivery', 'Delivery']]

export const SCHEDULES: Record<string, { title: string; sub: string; cols: Col[]; blank: Json; example?: Json[] }> = {
  sales_phases: {
    title: 'Sales phases',
    sub: 'Give the sales pace a shape: periods with their own units/month. Outside the phases, the base absorption applies.',
    cols: [{ field: 'name', label: 'Phase', type: 'text' }, { field: 'anchor', label: 'Starts at', type: 'anchor' },
      { field: 'offset', label: 'Offset (mo)', type: 'number', width: 90 }, { field: 'months', label: 'Months', type: 'number', width: 80 },
      { field: 'units_per_month', label: 'Units / month', type: 'number', width: 110 }],
    blank: { name: 'New phase', anchor: 'construction_start', offset: 0, months: 3, units_per_month: 5 },
    example: [{ name: 'Launch peak', anchor: 'construction_start', offset: 0, months: 3, units_per_month: 10 },
      { name: 'Delivery peak', anchor: 'delivery', offset: 0, months: 4, units_per_month: 8 }],
  },
  price_phases: {
    title: 'Price phases',
    sub: 'Price changes for contracts signed in a period, e.g. −8% launch discount or +5% after delivery (on top of escalation).',
    cols: [{ field: 'name', label: 'Phase', type: 'text' }, { field: 'anchor', label: 'Starts at', type: 'anchor' },
      { field: 'offset', label: 'Offset (mo)', type: 'number', width: 90 }, { field: 'months', label: 'Months', type: 'number', width: 80 },
      { field: 'pct', label: 'Price change %', type: 'number', width: 110 }],
    blank: { name: 'Launch discount', anchor: 'sales_start', offset: 0, months: 6, pct: -5 },
  },
  land_payments: {
    title: 'Land payment schedule',
    sub: 'Pay the land in installments: % of the price by month from closing (must add to 100%). Empty = all at closing.',
    cols: [{ field: 'month', label: 'Month', type: 'number', width: 90 }, { field: 'pct', label: '% of price', type: 'number', width: 110 }],
    blank: { month: 0, pct: 100 },
  },
  custom_flows: {
    title: 'Custom cash flows',
    sub: 'Any one-off cost or revenue the standard inputs don\'t cover: fees, utility connections, sale of a commercial unit, subsidies…',
    cols: [{ field: 'label', label: 'Item', type: 'text' }, { field: 'type', label: 'Type', type: 'flowtype', width: 100 },
      { field: 'amount', label: 'Amount', type: 'number', width: 130 }, { field: 'anchor', label: 'Timing', type: 'anchor' },
      { field: 'offset', label: 'Offset (mo)', type: 'number', width: 90 }],
    blank: { label: 'New item', type: 'cost', amount: 1000000, anchor: 'construction_start', offset: 0 },
  },
}

/** Table editor for a time-varying input. Saves through the same validated write path (audit trail + undo). */
export default function ScheduleEditor({ pid, k, rows: initial }: { pid: number; k: keyof typeof SCHEDULES; rows?: Json[] }) {
  const spec = SCHEDULES[k]
  const norm = (rs: Json[] | undefined) => (rs || []).map((r) => (k === 'custom_flows' && !r.anchor ? { ...r, anchor: 'closing', offset: r.month ?? 0 } : r))
  const [rows, setRows] = useState<Json[]>(norm(initial))
  const [err, setErr] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { setRows(norm(initial)) // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(initial)])
  const dirty = JSON.stringify(rows) !== JSON.stringify(norm(initial))
  const set = (i: number, f: string, v: string) => setRows(rows.map((r, j) => (j === i ? { ...r, [f]: v } : r)))
  const save = async (value: Json[]) => {
    setBusy(true); setErr(null); setMsg(null)
    try {
      const cleaned = value.map((r) => Object.fromEntries(Object.entries(r).map(([f, v]) => [f, spec.cols.find((c) => c.field === f)?.type === 'number' ? Number(v) : v])))
      const res = await applyChanges(pid, [{ key: k, value: cleaned }], { reason: `${spec.title} edited` })
      if (res.rejected?.length) setErr(res.rejected[0].error)
      else setMsg(value.length ? 'Saved; the model has been recalculated.' : 'Removed; the model uses the standard assumption.')
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const total = k === 'land_payments' ? rows.reduce((s, r) => s + Number(r.pct || 0), 0) : null

  return (
    <Card title={spec.title} sub={spec.sub} actions={<>
      {spec.example && rows.length === 0 && <button className="btn sm ghost" onClick={() => setRows(spec.example!)}>Use example</button>}
      <button className="btn sm" onClick={() => setRows([...rows, { ...spec.blank }])}><Plus size={13} /> Row</button>
      <button className="btn sm primary" disabled={busy || !dirty} onClick={() => save(rows)}><Save size={13} /> Save</button></>}>
      {rows.length === 0 ? <div className="small muted">None. The model uses the standard assumption.{spec.example ? ' Click "Use example" to start from a template.' : ''}</div> : (
        <table className="t">
          <thead><tr>{spec.cols.map((c) => <th key={c.field} style={{ width: c.width }}>{c.label}</th>)}<th style={{ width: 36 }} /></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {spec.cols.map((c) => (
                  <td key={c.field}>
                    {c.type === 'anchor' ? (
                      <select className="input" value={r[c.field] ?? 'closing'} onChange={(e) => set(i, c.field, e.target.value)}>
                        {ANCHORS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    ) : c.type === 'flowtype' ? (
                      <select className="input" value={r[c.field] ?? 'cost'} onChange={(e) => set(i, c.field, e.target.value)}>
                        <option value="cost">Cost</option><option value="revenue">Revenue</option>
                      </select>
                    ) : (
                      <input className="input" value={r[c.field] ?? ''} inputMode={c.type === 'number' ? 'decimal' : undefined} onChange={(e) => set(i, c.field, e.target.value)} />
                    )}
                  </td>
                ))}
                <td><button className="btn ghost sm" onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 size={13} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="row between" style={{ marginTop: 8 }}>
        <div className="tiny muted">{total != null && rows.length > 0 ? `Total ${total.toFixed(1)}% ${Math.abs(total - 100) > 0.5 ? '(must be 100%)' : '✓'}` : 'Edits are validated, recorded in the audit trail and can be undone. The AI assistant can set these for you too.'}</div>
        {(initial?.length ?? 0) > 0 && <button className="btn sm ghost danger" disabled={busy} onClick={() => { setRows([]); save([]) }}>Remove all</button>}
      </div>
      {err && <div className="small" style={{ color: 'var(--critical)', marginTop: 6 }}>{err}</div>}
      {msg && <div className="small" style={{ color: 'var(--good-text)', marginTop: 6 }}>{msg}</div>}
    </Card>
  )
}

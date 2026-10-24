import { Plus, Trash2 } from 'lucide-react'

export interface UnitRow {
  name: string; bedrooms: number; bathrooms: number; size: number; share_pct: number; terrace: number; premium_pct: number
}

export const DEFAULT_MIX: UnitRow[] = [
  { name: '1 BR', bedrooms: 1, bathrooms: 1, size: 65, share_pct: 30, terrace: 0, premium_pct: 5 },
  { name: '2 BR', bedrooms: 2, bathrooms: 2, size: 95, share_pct: 50, terrace: 6, premium_pct: 0 },
  { name: '3 BR', bedrooms: 3, bathrooms: 2.5, size: 135, share_pct: 20, terrace: 10, premium_pct: -3 },
]

const COLS: { k: keyof UnitRow; label: string; w: number; text?: boolean }[] = [
  { k: 'name', label: 'Type', w: 90, text: true },
  { k: 'bedrooms', label: 'Beds', w: 56 },
  { k: 'bathrooms', label: 'Baths', w: 56 },
  { k: 'size', label: 'Size m²', w: 76 },
  { k: 'share_pct', label: 'Share %', w: 70 },
  { k: 'terrace', label: 'Terrace m²', w: 78 },
  { k: 'premium_pct', label: 'Premium %', w: 76 },
]

export default function UnitMixEditor({ rows, onChange, sizeLabel = 'm²' }: { rows: UnitRow[]; onChange: (r: UnitRow[]) => void; sizeLabel?: string }) {
  const total = rows.reduce((s, r) => s + (Number(r.share_pct) || 0), 0)
  const set = (i: number, k: keyof UnitRow, v: string) => {
    const next = rows.map((r, j) => (j === i ? { ...r, [k]: k === 'name' ? v : v === '' ? ('' as unknown as number) : Number(v) } : r))
    onChange(next)
  }
  return (
    <div>
      <table className="t">
        <thead>
          <tr>{COLS.map((c) => <th key={c.k} style={{ width: c.w }}>{c.label.replace('m²', sizeLabel)}</th>)}<th /></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {COLS.map((c) => (
                <td key={c.k} style={{ padding: '4px 6px' }}>
                  <input className="input" style={{ height: 28 }} type={c.text ? 'text' : 'number'} step="any" value={r[c.k] as string | number}
                    onChange={(e) => set(i, c.k, e.target.value)} />
                </td>
              ))}
              <td style={{ padding: '4px 6px' }}>
                <button className="btn ghost sm" title="Remove" onClick={() => onChange(rows.filter((_, j) => j !== i))} disabled={rows.length <= 1}><Trash2 size={13} /></button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row between" style={{ marginTop: 8 }}>
        <button className="btn sm" onClick={() => onChange([...rows, { name: `Type ${rows.length + 1}`, bedrooms: 2, bathrooms: 2, size: 90, share_pct: 0, terrace: 0, premium_pct: 0 }])}>
          <Plus size={13} /> Add unit type
        </button>
        <span className={`badge ${Math.abs(total - 100) <= 0.5 ? 'good' : 'bad'}`}>Shares total {total.toFixed(1)}% {Math.abs(total - 100) <= 0.5 ? '✓' : '(must be 100%)'}</span>
      </div>
    </div>
  )
}

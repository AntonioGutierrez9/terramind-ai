// Number formatting. Currency-agnostic: pass the project's currency code.

export function money(v: number | null | undefined, cur = 'MXN', compact = true): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const abs = Math.abs(v)
  const sign = v < 0 ? '−' : ''
  if (compact) {
    if (abs >= 1e9) return `${sign}${cur} ${(abs / 1e9).toFixed(2)}B`
    if (abs >= 1e6) return `${sign}${cur} ${(abs / 1e6).toFixed(1)}M`
    if (abs >= 1e3) return `${sign}${cur} ${(abs / 1e3).toFixed(0)}K`
  }
  return `${sign}${cur} ${abs.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export function mm(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return (v / 1e6).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function num(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

/** Fractions (0.18) → "18.0%". */
export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

/** Percent numbers (18) → "18.0%". */
export function pctNum(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return `${v.toFixed(digits)}%`
}

export function multiple(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return `${v.toFixed(2)}x`
}

export function area(v: number | null | undefined, unit = 'm²'): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return `${num(v)} ${unit}`
}

export function delta(v: number | null | undefined, kind: 'pct' | 'money' = 'pct', cur = 'MXN'): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const s = v > 0 ? '+' : ''
  return kind === 'pct' ? `${s}${(v * 100).toFixed(1)} pts` : `${s}${money(v, cur)}`
}

/** Render a registry value with its unit label. */
export function fmtValue(v: unknown, unit: string, cur = 'MXN'): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  if (typeof v !== 'number') return String(v)
  if (unit === 'currency') return money(v, cur, false)
  if (unit.startsWith('currency/')) return `${cur} ${num(v)} / ${unit.split('/').slice(1).join('/').replace('area', 'm²')}`
  if (unit.startsWith('%')) return `${num(v, v % 1 ? 2 : 0)}${unit}`
  if (unit === 'area') return area(v)
  return `${num(v, v % 1 ? 2 : 0)} ${unit.replace('area', 'm²')}`.trim()
}

export function monthLabel(m: number): string {
  return `M${m}`
}

export const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
export const NAVY = '#17345e'
export const GRID = '#e8ebf0'
export const AXIS = '#7a8699'

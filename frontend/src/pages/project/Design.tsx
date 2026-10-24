import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Play, Save, Trash2 } from 'lucide-react'
import { api, applyChanges, notifyProjectChanged, type Json } from '../../api'
import UnitMixEditor, { type UnitRow } from '../../components/a/UnitMixEditor'
import { useProject } from '../../components/Layout'
import { Callout, Card, ChartTip, FieldGroup, Legend, ModelIncomplete, PageHead } from '../../components/ui'
import { area, AXIS, GRID, money, num, pct, SERIES } from '../../format'
import { useFetch } from '../../state'

const DEV_KEYS = ['dev.buildings', 'dev.stories', 'dev.levels_below', 'dev.footprint', 'dev.efficiency_pct', 'dev.amenity_area',
  'dev.parking_spaces', 'dev.parking_area_per_space', 'dev.quality']
const CONFIG_KEYS = ['dev.stories', 'dev.efficiency_pct', 'dev.levels_below', 'dev.parking_spaces', 'dev.amenity_area', 'unit_mix']

export default function Design() {
  const { data } = useProject()
  const p = data.project
  const a = p.assumptions
  const cur = p.profile.currency || 'MXN'
  const au = p.profile.area_unit || 'm²'
  const res = data.results
  const ok = res?.status === 'ok'
  const d = res?.design || {}
  const rent = data.mode === 'rent'
  const sellLabel = rent ? 'Leasable' : 'Saleable'

  // ---- unit mix editor ----
  const [rows, setRows] = useState<UnitRow[]>(a.unit_mix || [])
  const [mixMsg, setMixMsg] = useState<{ tone: 'good' | 'bad'; text: string } | null>(null)
  useEffect(() => { setRows(a.unit_mix || []) }, [p.updated_at]) // eslint-disable-line react-hooks/exhaustive-deps
  const saveMix = async (mix: UnitRow[] = rows) => {
    setMixMsg(null)
    try {
      const r = await applyChanges(p.id, [{ key: 'unit_mix', value: mix }], { reason: 'unit mix edited' })
      if (r.rejected?.length) setMixMsg({ tone: 'bad', text: r.rejected.map((x: Json) => x.error).join('; ') })
      else setMixMsg({ tone: 'good', text: r.applied?.length ? 'Unit mix saved — model recalculated.' : 'No changes.' })
    } catch (e) { setMixMsg({ tone: 'bad', text: (e as Error).message }) }
  }

  // ---- optimizer ----
  const [metric, setMetric] = useState('equity_irr')
  const [opt, setOpt] = useState<Json>(null)
  const [optBusy, setOptBusy] = useState(false)
  const runOpt = async () => {
    setOptBusy(true)
    try { setOpt(await api.get(`/api/projects/${p.id}/unit-mix?metric=${metric}`)) } finally { setOptBusy(false) }
  }
  const applyShares = async (shares: number[]) => {
    const mix = (a.unit_mix || []).map((t: UnitRow, i: number) => ({ ...t, share_pct: shares[i] }))
    await saveMix(mix)
  }

  // ---- saved configurations ----
  const { data: variants, reload: reloadVariants } = useFetch<Json[]>(`/api/projects/${p.id}/variants`)
  const configs = (variants || []).filter((v) => v.kind === 'configuration')
  const [cfgName, setCfgName] = useState('')
  const [compare, setCompare] = useState<Record<number, Json>>({})
  useEffect(() => {
    let alive = true
    Promise.all(configs.map((c) => api.post(`/api/projects/${p.id}/what-if`, {
      changes: Object.entries(c.payload).map(([key, value]) => ({ key, value })),
    }).then((r) => [c.id, r] as const).catch(() => [c.id, null] as const))).then((pairs) => {
      if (alive) setCompare(Object.fromEntries(pairs))
    })
    return () => { alive = false }
  }, [variants, p.updated_at]) // eslint-disable-line react-hooks/exhaustive-deps
  const saveConfig = async () => {
    const payload: Record<string, unknown> = {}
    for (const k of CONFIG_KEYS) if (a[k] !== null && a[k] !== undefined) payload[k] = a[k]
    await api.post(`/api/projects/${p.id}/variants`, { kind: 'configuration', name: cfgName || `Configuration ${configs.length + 1}`, payload })
    setCfgName('')
    reloadVariants()
  }
  const applyConfig = async (vid: number) => { await api.post(`/api/projects/${p.id}/variants/${vid}/apply`); notifyProjectChanged(p.id) }
  const delConfig = async (vid: number) => { await api.del(`/api/variants/${vid}`); reloadVariants() }

  const common = ok ? Math.max((d.gba_above || 0) - (d.saleable || 0) - (d.amenity_area || 0), 0) : 0
  const areaData = ok ? [{ name: 'Gross area', saleable: d.saleable, common, amenity: d.amenity_area || 0, below: d.below_area || 0 }] : []
  const m = res?.metrics || {}

  return (
    <div>
      <PageHead eyebrow="Step 2 · Development configuration" title="Building program & unit mix">
        Enter the physical program. Units, {sellLabel.toLowerCase()} area and parking needs are calculated — never typed in.
      </PageHead>
      <ModelIncomplete results={res} />

      <div className="grid g2" style={{ marginTop: 12 }}>
        <FieldGroup data={data} keys={DEV_KEYS} title="Building specifications" sub="Footprint empty = maximum allowed coverage" cols={1} />
        <div className="col" style={{ gap: 16 }}>
          <Card title="Calculated program" sub="Engine outputs from the approved assumptions" actions={<span className="badge calculated">calculated</span>}>
            {ok || d.land_area ? (
              <table className="t"><tbody>
                {[['Building footprint', area(d.footprint, au)], ['Above-ground GBA', area(d.gba_above, au)],
                  ['Below-grade area (parking)', area(d.below_area, au)], [`${sellLabel} area`, area(d.saleable, au)],
                  ['Units', num(d.units)], ['Area not allocated to whole units', area(d.unsold_remainder, au)],
                  ['Terrace area', area(d.terrace_area, au)], ['Parking spaces', num(d.parking_spaces)],
                  ['Underground levels needed', num(d.levels_below_needed)]].map(([k, v]) => (
                  <tr key={k}><td className="muted">{k}</td><td className="num">{v}</td></tr>
                ))}
              </tbody></table>
            ) : <Callout tone="warn">Enter land area, stories and efficiency to calculate the program.</Callout>}
          </Card>
          {ok && (
            <Card title="Area breakdown" sub={`Total gross ${area((d.gba_above || 0) + (d.below_area || 0), au)}`}>
              <ResponsiveContainer width="100%" height={90}>
                <BarChart data={areaData} layout="vertical" margin={{ left: 0, right: 10, top: 0, bottom: 0 }} barGap={2}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="name" hide />
                  <Tooltip content={<ChartTip fmt={(v) => area(v, au)} />} cursor={false} />
                  <Bar dataKey="saleable" name={sellLabel} stackId="a" fill={SERIES[0]} stroke="#fff" strokeWidth={2} barSize={28} />
                  <Bar dataKey="common" name="Common / circulation" stackId="a" fill={SERIES[2]} stroke="#fff" strokeWidth={2} />
                  <Bar dataKey="amenity" name="Amenities" stackId="a" fill={SERIES[3]} stroke="#fff" strokeWidth={2} />
                  <Bar dataKey="below" name="Below-grade parking" stackId="a" fill={SERIES[6]} stroke="#fff" strokeWidth={2} radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <Legend items={[{ label: sellLabel, color: SERIES[0] }, { label: 'Common / circulation', color: SERIES[2] }, { label: 'Amenities', color: SERIES[3] }, { label: 'Below-grade parking', color: SERIES[6] }]} />
            </Card>
          )}
        </div>
      </div>

      <Card title="Unit mix" className="" sub="Shares of saleable area by unit type; premiums adjust price per m² for each type." actions={<button className="btn primary sm" onClick={() => saveMix()}><Save size={13} /> Save unit mix</button>}>
        <UnitMixEditor rows={rows} onChange={setRows} sizeLabel={au} />
        {mixMsg && <div style={{ marginTop: 8 }}><Callout tone={mixMsg.tone}>{mixMsg.text}</Callout></div>}
        {ok && d.unit_types?.length > 0 && (
          <>
            <div className="divider" />
            <h3 style={{ marginBottom: 6 }}>Resulting units <span className="badge calculated">calculated</span></h3>
            <table className="t">
              <thead><tr><th>Type</th><th className="num">Units</th><th className="num">Size</th><th className="num">Area</th>{!rent && <th className="num">Unit price (today)</th>}{!rent && <th className="num">Effective price / {au}</th>}</tr></thead>
              <tbody>
                {d.unit_types.map((t: Json) => (
                  <tr key={t.name}><td>{t.name}</td><td className="num">{t.units}</td><td className="num">{area(t.size, au)}</td><td className="num">{area(t.area, au)}</td>
                    {!rent && <td className="num">{money(t.unit_price, cur)}</td>}{!rent && <td className="num">{t.price_per_area_effective ? money(t.price_per_area_effective, cur, false) : '—'}</td>}</tr>
                ))}
                <tr className="total"><td>Total</td><td className="num">{d.units}</td><td /><td className="num">{area(d.sold_area, au)}</td>{!rent && <td />}{!rent && <td />}</tr>
              </tbody>
            </table>
          </>
        )}
      </Card>

      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Unit-mix optimizer" sub="Enumerates share combinations (10% steps) through the full financial model"
          actions={<>
            <select className="input" style={{ width: 150, height: 28 }} value={metric} onChange={(e) => setMetric(e.target.value)}>
              <option value="equity_irr">Max equity IRR</option><option value="profit">Max profit</option><option value="npv">Max NPV</option>
            </select>
            <button className="btn primary sm" disabled={optBusy || !ok} onClick={runOpt}><Play size={13} /> {optBusy ? 'Running…' : 'Optimize'}</button>
          </>}>
          {!opt && <div className="small muted">{ok ? 'Run the optimizer to compare unit-mix alternatives.' : 'Complete the model first.'}</div>}
          {opt?.status && opt.status !== 'ok' && <Callout tone="warn">{opt.message}</Callout>}
          {opt?.status === 'ok' && (
            <>
              <div className="small muted" style={{ marginBottom: 8 }}>{opt.evaluated} mixes evaluated. {opt.note}</div>
              <div className="table-wrap">
                <table className="t">
                  <thead><tr><th>Shares ({opt.types.join(' / ')})</th><th className="num">Units</th><th className="num">GDV</th><th className="num">Profit</th><th className="num">Eq. IRR</th><th className="num">Sell-out</th><th /></tr></thead>
                  <tbody>
                    <tr style={{ background: 'var(--accent-soft)' }}>
                      <td><b>Current</b> {opt.current.shares.map((s: number) => `${num(s)}%`).join(' / ')}</td><td className="num">{opt.current.units}</td>
                      <td className="num">{money(opt.current.gdv, cur)}</td><td className="num">{money(opt.current.profit, cur)}</td>
                      <td className="num">{pct(opt.current.equity_irr)}</td><td className="num">{opt.current.sellout_months ?? '—'} mo</td><td />
                    </tr>
                    {opt.top.map((r: Json, i: number) => (
                      <tr key={i}>
                        <td>{r.shares.map((s: number) => `${s}%`).join(' / ')}{!r.compliant && <span className="badge bad" style={{ marginLeft: 6 }}>noncompliant</span>}</td>
                        <td className="num">{r.units}</td><td className="num">{money(r.gdv, cur)}</td><td className="num">{money(r.profit, cur)}</td>
                        <td className="num">{pct(r.equity_irr)}</td><td className="num">{r.sellout_months ?? '—'} mo</td>
                        <td><button className="btn sm" onClick={() => applyShares(r.shares)}>Apply this mix</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Card>

        <Card title="Saved configurations" sub="Save alternatives and compare them against the current design (what-if runs, nothing saved)">
          <div className="row" style={{ gap: 6, marginBottom: 10 }}>
            <input className="input" placeholder="Configuration name" value={cfgName} onChange={(e) => setCfgName(e.target.value)} />
            <button className="btn primary sm" onClick={saveConfig}><Save size={13} /> Save current</button>
          </div>
          {configs.length === 0 ? <div className="small muted">No saved configurations yet.</div> : (
            <div className="table-wrap">
              <table className="t">
                <thead><tr><th>Configuration</th><th className="num">Units</th><th className="num">GDV</th><th className="num">Profit</th><th className="num">Eq. IRR</th><th /></tr></thead>
                <tbody>
                  <tr style={{ background: 'var(--accent-soft)' }}><td><b>Current design</b></td><td className="num">{num(m.units)}</td><td className="num">{money(m.gdv, cur)}</td><td className="num">{money(m.profit, cur)}</td><td className="num">{pct(m.equity_irr)}</td><td /></tr>
                  {configs.map((c) => {
                    const w = compare[c.id]
                    const wm = w?.metrics || {}
                    const pl = c.payload || {}
                    return (
                      <tr key={c.id}>
                        <td><b>{c.name}</b>
                          <div className="tiny muted">{[pl['dev.stories'] && `${pl['dev.stories']} stories`, pl['dev.efficiency_pct'] && `${pl['dev.efficiency_pct']}% eff.`,
                            pl['dev.parking_spaces'] != null && `${pl['dev.parking_spaces']} spaces`, pl.unit_mix && `${pl.unit_mix.length} unit types`].filter(Boolean).join(' · ')}</div></td>
                        <td className="num">{w?.status === 'ok' ? num(wm.units) : '—'}</td><td className="num">{money(wm.gdv, cur)}</td>
                        <td className="num">{money(wm.profit, cur)}</td><td className="num">{pct(wm.equity_irr)}</td>
                        <td className="right" style={{ whiteSpace: 'nowrap' }}>
                          <button className="btn sm" onClick={() => applyConfig(c.id)}>Apply</button>{' '}
                          <button className="btn ghost sm danger" onClick={() => delConfig(c.id)} title="Delete"><Trash2 size={13} /></button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
      {ok && d.unit_types?.length > 0 && (
        <Card title="Units by type" sub="Calculated unit count per type" className="" bodyClass="">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={d.unit_types} margin={{ left: 0, right: 10, top: 8, bottom: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="name" tick={{ fill: AXIS, fontSize: 11 }} />
              <YAxis tick={{ fill: AXIS, fontSize: 11 }} width={36} allowDecimals={false} />
              <Tooltip content={<ChartTip fmt={(v) => num(v)} />} cursor={{ fill: 'rgba(42,120,214,.06)' }} />
              <Bar dataKey="units" name="Units" fill={SERIES[0]} radius={[4, 4, 0, 0]} barSize={36} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}
    </div>
  )
}

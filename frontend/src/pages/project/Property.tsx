import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCheck, ExternalLink, FlaskConical, PencilLine, ShieldAlert } from 'lucide-react'
import { api, notifyProjectChanged, type Json } from '../../api'
import ResearchButton from '../../components/a/ResearchButton'
import SiteMap from '../../components/a/SiteMap'
import { useProject } from '../../components/Layout'
import { Callout, Card, FieldGroup, PageHead, StatusBadge } from '../../components/ui'
import { area, money, num } from '../../format'
import { useFetch } from '../../state'

const REG_KEYS = ['reg.max_stories', 'reg.min_open_area_pct', 'reg.max_far', 'reg.max_height_m', 'reg.min_land_per_unit', 'reg.max_units',
  'reg.max_underground_levels', 'reg.parking_min_per_unit', 'reg.parking_max_per_unit']
const SITE_KEYS = ['site.land_area', 'site.land_price', 'site.transfer_tax_pct', 'site.legal_notary_pct', 'site.brokerage_pct', 'site.due_diligence']
const LABEL: Record<string, string> = {
  ground_up: 'Ground-up development', acquisition: 'Acquisition', renovation: 'Renovation', capex: 'CAPEX improvement',
  repositioning: 'Repositioning', acquisition_renovation: 'Acquisition + renovation', owned: 'Owned', under_contract: 'Under contract',
  negotiating: 'Negotiating', identified: 'Identified',
}

function verBadge(v: string) {
  return <span className={`badge ${v === 'verified' ? 'good' : v === 'preliminary' ? 'warn' : 'bad'}`}>{v === 'not_found' ? 'not found' : v}</span>
}

export default function Property() {
  const { data } = useProject()
  const nav = useNavigate()
  const p = data.project
  const prof = p.profile
  const cur = prof.currency || 'MXN'
  const res = data.results
  const groundUp = (prof.strategy || 'ground_up') === 'ground_up'
  const { data: research } = useFetch<Json>(`/api/projects/${p.id}/research`)
  const reg = research?.regulatory
  const z = reg?.payload
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const pendingReg = REG_KEYS.filter((k) => p.meta[k]?.proposal?.status === 'pending')
  const overrides = Object.entries(p.meta || {}).filter(([, m]) => (m as Json)?.noncompliant_override)
  const d = res?.design || {}

  const approveAll = async () => {
    setBusy('approve')
    try {
      for (const k of pendingReg) await api.post(`/api/projects/${p.id}/proposals/${k}/approve`)
      setNote(`Approved ${pendingReg.length} researched regulatory value(s).`)
      notifyProjectChanged(p.id)
    } catch (e) { setNote((e as Error).message) } finally { setBusy(null) }
  }
  const hypothetical = async () => {
    setBusy('hypo')
    try {
      const r = await api.post(`/api/projects/${p.id}/duplicate`, { name: `${p.name} (hypothetical)` })
      await api.post(`/api/projects/${r.id}/status`, { status: 'hypothetical' })
      nav(`/p/${r.id}/property`)
    } catch (e) { setNote((e as Error).message) } finally { setBusy(null) }
  }
  const query = [prof.address, prof.neighborhood, prof.city, prof.country].filter(Boolean).join(', ')

  return (
    <div>
      <PageHead eyebrow="Step 1 · Property intelligence" title={p.name}>
        {[prof.address, prof.neighborhood, prof.city].filter(Boolean).join(' · ') || 'No address yet'}
      </PageHead>

      <div className="grid g3" style={{ marginBottom: 16 }}>
        <Card title="Location" className="span2" bodyClass="">
          <SiteMap lat={prof.lat} lon={prof.lon} query={query} height={300} />
        </Card>
        <Card title="Property facts">
          <table className="t"><tbody>
            {[['Address', prof.address], ['Neighborhood', prof.neighborhood], ['City', [prof.city, prof.state].filter(Boolean).join(', ')],
              ['Land area', area(p.assumptions['site.land_area'], prof.area_unit || 'm²')],
              ['Acquisition price', money(p.assumptions['site.land_price'], cur)],
              ['Price per land m²', p.assumptions['site.land_price'] && p.assumptions['site.land_area'] ? money(p.assumptions['site.land_price'] / p.assumptions['site.land_area'], cur, false) : '—'],
              ['Ownership', LABEL[prof.ownership_status] || prof.ownership_status], ['Strategy', LABEL[prof.strategy] || prof.strategy],
              ['Property type', prof.property_type]].map(([k, v]) => (
              <tr key={k as string}><td className="muted" style={{ width: 130 }}>{k}</td><td>{v || '—'}</td></tr>
            ))}
            {prof.details && Object.entries(prof.details).map(([k, v]) => <tr key={k}><td className="muted">{k}</td><td>{String(v)}</td></tr>)}
          </tbody></table>
          {prof.demo && <div style={{ marginTop: 8 }}><span className="badge demo">fictional demo case</span></div>}
        </Card>
      </div>

      {groundUp && (
        <Card title="Zoning & development regulations" className=""
          sub={z ? `Regulatory & Development agent · ${reg.from_cache ? 'cached' : 'live'} research · ${reg.created_at?.slice(0, 10)}` : 'Researched from official sources when available — never invented.'}
          actions={<ResearchButton pid={p.id} kind="regulatory" label="Run Regulatory agent" />}>
          {!z && <Callout tone="info">No regulatory research yet. Run the agent, or enter the legal limits manually below (manual entry is always available).</Callout>}
          {z && (
            <div className="col" style={{ gap: 12 }}>
              {z.suspicious_fields?.length > 0 && (
                <Callout tone="bad">Instruction-like text from a website was removed from {z.suspicious_fields.length} field(s). Treat this source with caution.</Callout>
              )}
              <div className="row wrap" style={{ gap: 16 }}>
                <div><div className="tiny muted">ZONING CODE</div><div style={{ fontSize: 18, fontWeight: 650 }}>{z.zoning_code || 'Not verified'}</div></div>
                <div className="grow small" style={{ color: 'var(--text-2)' }}>{z.zoning_summary}</div>
              </div>
              {z.permitted_uses?.length > 0 && <div className="small"><b>Permitted uses:</b> {z.permitted_uses.join(' · ')}</div>}
              <div className="table-wrap">
                <table className="t">
                  <thead><tr><th>Parameter</th><th>Finding</th><th>Status</th><th>Source</th><th>Note</th></tr></thead>
                  <tbody>
                    {(z.findings || []).map((f: Json, i: number) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 550 }}>{f.parameter}{f.key && <div className="tiny muted">{f.key}</div>}</td>
                        <td className="num">{f.value != null ? `${num(f.value, f.value % 1 ? 2 : 0)} ${f.unit || ''}` : ''}{f.value_text && <div className="small" style={{ textAlign: 'left' }}>{f.value_text}</div>}</td>
                        <td>{verBadge(f.verification)}</td>
                        <td className="small">{f.source_url ? <a href={f.source_url} target="_blank" rel="noreferrer">{f.source_title || 'link'} <ExternalLink size={10} /></a> : <span className="muted">—</span>}</td>
                        <td className="small muted" style={{ maxWidth: 320 }}>{f.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {z.missing?.length > 0 && <Callout tone="warn"><b>Not verified / missing:</b><ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{z.missing.map((m: string, i: number) => <li key={i}>{m}</li>)}</ul></Callout>}
              {z.caveats?.length > 0 && <div className="tiny muted">Caveats: {z.caveats.join(' · ')}</div>}
            </div>
          )}

          <div className="divider" />
          <h3 style={{ marginBottom: 8 }}>How do you want to proceed?</h3>
          <div className="grid g3">
            <div className="card flat" style={{ padding: 12 }}>
              <div className="row" style={{ gap: 8, marginBottom: 6 }}><CheckCheck size={16} color="var(--good-text)" /><b>1. Use researched assumptions</b></div>
              <div className="small muted" style={{ marginBottom: 8 }}>Approve the agent's pending proposals. Approved values become the legal reference used for compliance checks.</div>
              <button className="btn sm primary" disabled={!pendingReg.length || busy !== null} onClick={approveAll}>
                {busy === 'approve' ? 'Approving…' : `Approve ${pendingReg.length} pending value(s)`}
              </button>
            </div>
            <div className="card flat" style={{ padding: 12 }}>
              <div className="row" style={{ gap: 8, marginBottom: 6 }}><PencilLine size={16} color="var(--accent)" /><b>2. Modify specific assumptions</b></div>
              <div className="small muted">Edit any value in "Regulatory assumptions" below. Relaxing an approved legal limit asks for confirmation and flags the scenario.</div>
            </div>
            <div className="card flat" style={{ padding: 12 }}>
              <div className="row" style={{ gap: 8, marginBottom: 6 }}><FlaskConical size={16} color="var(--series-7)" /><b>3. Create a hypothetical scenario</b></div>
              <div className="small muted" style={{ marginBottom: 8 }}>Duplicate this project as a hypothetical copy to test designs beyond current rules without touching the base case.</div>
              <button className="btn sm" disabled={busy !== null} onClick={hypothetical}>{busy === 'hypo' ? 'Creating…' : 'Create hypothetical copy'}</button>
            </div>
          </div>
          {note && <div style={{ marginTop: 10 }}><Callout tone="info">{note}</Callout></div>}
        </Card>
      )}

      <div className="grid g2" style={{ marginTop: 16 }}>
        {groundUp && <FieldGroup data={data} keys={REG_KEYS} title="Regulatory assumptions" sub="Legal limits used by the engine. Badges show source and verification." cols={1} />}
        <div className="col" style={{ gap: 16 }}>
          {groundUp && (
            <Card title="Development capacity" sub="Estimated capacity — calculated by the engine from the approved assumptions">
              {res?.status === 'ok' || d.land_area ? (
                <>
                  <table className="t"><tbody>
                    {[['Land area', area(d.land_area)], ['Max site coverage (footprint)', area(d.max_coverage_area)],
                      ['Max FAR', d.max_far != null ? `${num(d.max_far, 2)}x` : '—'],
                      ['Max buildable GBA (capacity)', area(d.capacity_gba)], ['Designed above-ground GBA', area(d.gba_above)],
                      ['FAR used', d.far_used != null ? `${num(d.far_used, 2)}x` : '—'],
                      ['Density limit (max dwellings)', d.max_units_density != null ? num(d.max_units_density) : 'No density limit entered'],
                      ['Designed units', num(d.units)]].map(([k, v]) => (
                      <tr key={k}><td className="muted">{k}</td><td className="num">{v}</td></tr>
                    ))}
                  </tbody></table>
                  <div style={{ marginTop: 10 }} className="col">
                    {(res?.compliance || []).length > 0
                      ? <Callout tone="bad"><b>Design exceeds researched limits:</b><ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{res.compliance.map((c: Json, i: number) => <li key={i}>{c.detail}</li>)}</ul></Callout>
                      : res?.status === 'ok' && <StatusBadge level="good">Design within researched limits</StatusBadge>}
                    {overrides.length > 0 && <Callout tone="bad" icon={<ShieldAlert size={16} />}><b>Potentially noncompliant (hypothetical):</b> legal limits overridden for {overrides.map(([k]) => k).join(', ')}.</Callout>}
                  </div>
                </>
              ) : <Callout tone="warn">Enter land area and legal limits to estimate development capacity.</Callout>}
              <div className="tiny muted" style={{ marginTop: 8 }}>
                <span className="badge good">verified</span> official source for this location · <span className="badge warn">preliminary</span> general rule or interpretation · <span className="badge calculated">calculated</span> engine estimate
              </div>
            </Card>
          )}
          <FieldGroup data={data} keys={SITE_KEYS} title="Site & acquisition" sub="Acquisition price and closing costs" cols={1} />
        </div>
      </div>
    </div>
  )
}

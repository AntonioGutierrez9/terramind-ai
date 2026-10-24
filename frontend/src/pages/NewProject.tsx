import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check } from 'lucide-react'
import { api, type Json } from '../api'
import UnitMixEditor, { DEFAULT_MIX, type UnitRow } from '../components/a/UnitMixEditor'
import { Callout, Card, PageHead } from '../components/ui'
import { useMeta } from '../state'

const LABELS: Record<string, string> = {
  residential: 'Residential', commercial: 'Commercial', industrial: 'Industrial', mixed_use: 'Mixed-use',
  ground_up: 'Ground-up development', acquisition: 'Acquisition', renovation: 'Renovation', capex: 'CAPEX improvement',
  repositioning: 'Repositioning', acquisition_renovation: 'Acquisition + renovation',
  build_to_sell: 'Build-to-sell', develop_and_sell: 'Develop & sell', build_to_rent: 'Build-to-rent',
  acquire_and_hold: 'Acquire & hold', value_add: 'Value-add',
  owned: 'Owned', under_contract: 'Under contract', negotiating: 'Negotiating', identified: 'Identified',
}
const SALE_MODELS = ['build_to_sell', 'develop_and_sell']
const STEPS = ['Basics', 'Strategy', 'Fundamentals', 'Review']

type F = Record<string, string>

function Field({ label, k, f, set, type = 'text', hint, unit }: { label: string; k: string; f: F; set: (k: string, v: string) => void; type?: string; hint?: string; unit?: string }) {
  return (
    <label className="field">
      <span>{label}{unit && <span className="muted"> ({unit})</span>}</span>
      <input className="input" type={type} step="any" value={f[k] ?? ''} onChange={(e) => set(k, e.target.value)} placeholder={hint} />
    </label>
  )
}

function Choice({ label, k, f, set, options }: { label: string; k: string; f: F; set: (k: string, v: string) => void; options: string[] }) {
  return (
    <div className="field" style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, color: 'var(--text-2)', fontWeight: 550 }}>
      <span>{label}</span>
      <div className="row wrap" style={{ gap: 6 }}>
        {options.map((o) => (
          <button key={o} type="button" className={`btn sm ${f[k] === o ? 'primary' : ''}`} onClick={() => set(k, o)}>{LABELS[o] || o}</button>
        ))}
      </div>
    </div>
  )
}

export default function NewProject() {
  const meta = useMeta()
  const nav = useNavigate()
  const ch = meta.profile_choices
  const [step, setStep] = useState(0)
  const [f, setF] = useState<F>({
    name: '', country: 'Mexico', state: 'Ciudad de México', city: 'Mexico City', neighborhood: '', address: '',
    currency: 'MXN', area_unit: 'm²', property_type: 'residential', strategy: 'ground_up', business_model: 'build_to_sell',
    ownership_status: 'identified', horizon_years: '5', mixed_primary: 'residential',
  })
  const [mix, setMix] = useState<UnitRow[]>(DEFAULT_MIX)
  const [applySuggested, setApplySuggested] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rejected, setRejected] = useState<Json[] | null>(null)
  const set = (k: string, v: string) => setF((o) => ({ ...o, [k]: v }))

  const groundUp = f.strategy === 'ground_up'
  const sale = SALE_MODELS.includes(f.business_model)
  const industrial = f.property_type === 'industrial'
  const commercial = f.property_type === 'commercial'
  const mixed = f.property_type === 'mixed_use'
  const cur = f.currency

  // Assumptions the wizard collects for this combination of answers (registry keys).
  const fieldsFor = useMemo(() => {
    const L: { k: string; label: string; unit?: string; hint?: string }[] = []
    if (groundUp) {
      L.push({ k: 'site.land_area', label: 'Land area', unit: f.area_unit }, { k: 'site.land_price', label: 'Land acquisition price', unit: cur, hint: 'e.g. 120000000 or 120m' })
      L.push({ k: 'reg.max_stories', label: 'Max stories allowed (if known)', hint: 'optional — agent can research' },
        { k: 'reg.min_open_area_pct', label: 'Min open area (if known)', unit: '%', hint: 'optional' })
      L.push({ k: 'dev.stories', label: 'Planned stories above ground' }, { k: 'dev.efficiency_pct', label: 'Saleable / gross efficiency', unit: '%', hint: 'e.g. 80' })
      L.push({ k: 'sch.predev_months', label: 'Design & permits', unit: 'months' }, { k: 'sch.construction_months', label: 'Construction duration', unit: 'months' })
      L.push({ k: 'cost.hard_per_area', label: 'Hard cost per m² GBA (optional)', unit: `${cur}/${f.area_unit}`, hint: 'agent can research' })
    } else {
      L.push({ k: 'site.land_area', label: 'Site area', unit: f.area_unit }, { k: 'site.land_price', label: 'Acquisition price', unit: cur })
      L.push({ k: 'dev.existing_rentable_area', label: 'Existing rentable area', unit: f.area_unit })
      L.push({ k: 'cost.renovation_budget', label: 'Renovation / CAPEX budget', unit: cur }, { k: 'sch.construction_months', label: 'Renovation duration', unit: 'months' })
    }
    if (sale) {
      L.push({ k: 'rev.price_per_area', label: 'Base sale price', unit: `${cur}/${f.area_unit}` }, { k: 'rev.absorption_per_month', label: 'Expected sales pace', unit: 'units / month' })
    } else {
      L.push({ k: 'rent.rent_per_area_month', label: groundUp ? 'Market rent' : 'In-place / market rent', unit: `${cur}/${f.area_unit}/month` })
      L.push({ k: 'rent.vacancy_pct', label: groundUp ? 'Stabilized vacancy' : 'Vacancy (100 − occupancy)', unit: '%' })
      L.push({ k: 'rent.exit_cap_pct', label: 'Exit cap rate', unit: '%' })
    }
    return L
  }, [groundUp, sale, cur, f.area_unit])

  const detailFields = industrial
    ? [{ k: 'd_clear_height', label: 'Clear height', unit: 'm' }, { k: 'd_docks', label: 'Loading docks', unit: 'count' }, { k: 'd_coverage', label: 'Land coverage', unit: '%' }, { k: 'd_tenant', label: 'Tenant / specification' }]
    : commercial ? [{ k: 'd_tenants', label: 'Number of tenants' }, { k: 'd_walt', label: 'WALT', unit: 'years' }, { k: 'd_leases', label: 'Main lease terms' }]
      : []

  const assumptions = () => {
    const a: Record<string, unknown> = {}
    for (const fd of fieldsFor) if (f[fd.k] !== undefined && f[fd.k] !== '') a[fd.k] = f[fd.k]
    // for-sale projects need a unit mix; ground-up rentals use it as the unit program
    if (groundUp || sale) a.unit_mix = mix
    return a
  }
  const profile = () => {
    const p: Record<string, unknown> = {
      name: f.name || 'Untitled project', country: f.country, state: f.state, city: f.city, neighborhood: f.neighborhood, address: f.address,
      currency: f.currency, area_unit: f.area_unit, property_type: f.property_type, strategy: f.strategy, business_model: f.business_model,
      ownership_status: f.ownership_status, horizon_years: Number(f.horizon_years) || 5,
    }
    const details: Record<string, string> = {}
    for (const d of detailFields) if (f[d.k]) details[d.label] = f[d.k] + (d.unit ? ` ${d.unit}` : '')
    if (mixed) details['Primary component modeled'] = f.mixed_primary
    if (Object.keys(details).length) p.details = details
    return p
  }

  const submit = async () => {
    setBusy(true); setError(null); setRejected(null)
    try {
      const r = await api.post('/api/projects', { profile: profile(), assumptions: assumptions(), apply_suggested: applySuggested })
      if (r.rejected?.length) { setRejected(r.rejected); setTimeout(() => nav(`/p/${r.id}/property`), 4000) }
      else nav(`/p/${r.id}/property`)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const canNext = step === 0 ? !!f.name.trim() && !!f.city.trim() : true
  const filled = fieldsFor.filter((fd) => f[fd.k])

  return (
    <div style={{ maxWidth: 980 }}>
      <PageHead eyebrow="New investment" title="Project creation wizard">
        You provide fundamentals; TerraMind calculates outputs. Agents can research the rest on the next pages.
      </PageHead>
      <div className="stepper">{STEPS.map((s, i) => <div key={s} className={`s ${i <= step ? 'on' : ''}`} title={s} />)}</div>
      <div className="row small muted" style={{ marginBottom: 12, gap: 18 }}>
        {STEPS.map((s, i) => <span key={s} style={{ fontWeight: i === step ? 650 : 400, color: i === step ? 'var(--navy-700)' : undefined }}>{i + 1}. {s}</span>)}
      </div>

      {step === 0 && (
        <Card title="Project basics" sub="Location drives the zoning, market, cost and financing research.">
          <div className="grid g3">
            <Field label="Project name" k="name" f={f} set={set} hint="e.g. Roma Norte Residences" />
            <Field label="Country" k="country" f={f} set={set} />
            <Field label="State" k="state" f={f} set={set} />
            <Field label="City" k="city" f={f} set={set} />
            <Field label="Neighborhood" k="neighborhood" f={f} set={set} hint="e.g. Polanco" />
            <Field label="Property address" k="address" f={f} set={set} />
            <label className="field"><span>Currency</span>
              <select className="input" value={f.currency} onChange={(e) => set('currency', e.target.value)}><option>MXN</option><option>USD</option></select></label>
            <label className="field"><span>Area unit</span>
              <select className="input" value={f.area_unit} onChange={(e) => set('area_unit', e.target.value)}><option>m²</option><option>ft²</option></select></label>
          </div>
        </Card>
      )}

      {step === 1 && (
        <Card title="Investment strategy" sub="The next questions change with these answers.">
          <div className="col" style={{ gap: 16 }}>
            <Choice label="Property type" k="property_type" f={f} set={set} options={ch.property_type} />
            <Choice label="Investment strategy" k="strategy" f={f} set={set} options={ch.strategy} />
            <Choice label="Business model" k="business_model" f={f} set={set} options={ch.business_model} />
            <Choice label="Property ownership status" k="ownership_status" f={f} set={set} options={ch.ownership_status} />
            <div style={{ maxWidth: 220 }}><Field label="Investment horizon" k="horizon_years" f={f} set={set} type="number" unit="years" /></div>
            {mixed && (
              <>
                <Callout tone="info">Mixed-use multi-component modeling (separate revenues and costs per component) is on the roadmap. This version models the <b>primary component</b> you choose here.</Callout>
                <Choice label="Primary component" k="mixed_primary" f={f} set={set} options={['residential', 'commercial', 'industrial']} />
              </>
            )}
            {!groundUp && sale && <Callout tone="warn">Acquire-and-sell of an existing building uses the for-sale model with your unit program and renovation budget.</Callout>}
          </div>
        </Card>
      )}

      {step === 2 && (
        <div className="col" style={{ gap: 16 }}>
          <Card title={`${LABELS[f.property_type]} · ${LABELS[f.strategy]} · ${LABELS[f.business_model]}`}
            sub="Leave anything you don't know empty — the model lists what is missing, and the agents can research it.">
            <div className="grid g3">
              {fieldsFor.map((fd) => <Field key={fd.k} label={fd.label} k={fd.k} f={f} set={set} unit={fd.unit} hint={fd.hint} />)}
            </div>
          </Card>
          {detailFields.length > 0 && (
            <Card title={industrial ? 'Industrial specifications' : 'Tenancy'} sub="Captured on the project profile (informational; the engine uses area-based rent).">
              <div className="grid g4">{detailFields.map((d) => <Field key={d.k} label={d.label} k={d.k} f={f} set={set} unit={d.unit} />)}</div>
            </Card>
          )}
          {groundUp && (
            <Card title={sale ? 'Unit mix' : 'Unit program'} sub="Units are calculated from saleable area × share ÷ unit size — you don't enter unit counts.">
              <UnitMixEditor rows={mix} onChange={setMix} sizeLabel={f.area_unit} />
            </Card>
          )}
        </div>
      )}

      {step === 3 && (
        <Card title="Review" sub="Nothing is calculated by AI — the deterministic engine computes outputs once inputs are complete.">
          <div className="grid g2">
            <div>
              <h3 style={{ marginBottom: 8 }}>Profile</h3>
              <table className="t"><tbody>
                {[['Name', f.name], ['Location', [f.address, f.neighborhood, f.city, f.state, f.country].filter(Boolean).join(', ')],
                  ['Type', LABELS[f.property_type]], ['Strategy', LABELS[f.strategy]], ['Business model', LABELS[f.business_model]],
                  ['Ownership', LABELS[f.ownership_status]], ['Horizon', `${f.horizon_years} years`], ['Currency / unit', `${f.currency} · ${f.area_unit}`]]
                  .map(([k, v]) => <tr key={k}><td className="muted">{k}</td><td>{v || '—'}</td></tr>)}
              </tbody></table>
            </div>
            <div>
              <h3 style={{ marginBottom: 8 }}>Assumptions you entered ({filled.length}{groundUp ? ` + ${mix.length} unit types` : ''})</h3>
              <table className="t"><tbody>
                {filled.map((fd) => <tr key={fd.k}><td className="muted">{fd.label}</td><td className="num">{f[fd.k]} {fd.unit}</td></tr>)}
                {filled.length === 0 && <tr><td className="muted">None yet — you can add them on the project pages or by chat.</td></tr>}
              </tbody></table>
            </div>
          </div>
          <label className="row small" style={{ marginTop: 14, gap: 8 }}>
            <input type="checkbox" checked={applySuggested} onChange={(e) => setApplySuggested(e.target.checked)} />
            Apply suggested default assumptions (fees, payment schedule, soft-cost %, etc.). They are labeled <span className="badge default">default (unverified)</span> and editable.
          </label>
          {error && <div style={{ marginTop: 10 }}><Callout tone="bad">{error}</Callout></div>}
          {rejected && (
            <div style={{ marginTop: 10 }}><Callout tone="warn">
              Project created, but some values were rejected by validation: {rejected.map((r) => `${r.key}: ${r.error}`).join('; ')}. Opening the project…
            </Callout></div>
          )}
        </Card>
      )}

      <div className="row between" style={{ marginTop: 16 }}>
        <button className="btn" disabled={step === 0} onClick={() => setStep((s) => s - 1)}><ArrowLeft size={14} /> Back</button>
        {step < 3 ? (
          <button className="btn primary" disabled={!canNext} onClick={() => setStep((s) => s + 1)}>Next <ArrowRight size={14} /></button>
        ) : (
          <button className="btn primary" disabled={busy} onClick={submit}><Check size={14} /> {busy ? 'Creating…' : 'Create project'}</button>
        )}
      </div>
    </div>
  )
}

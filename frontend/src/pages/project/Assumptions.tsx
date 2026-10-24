import { Fragment, useMemo, useState } from 'react'
import { ExternalLink, Pencil, Wand2 } from 'lucide-react'
import { useProject } from '../../components/Layout'
import { Callout, Card, Loading, Modal, PageHead, ProposalRow, SourceBadge, StatusBadge } from '../../components/ui'
import { METRIC_LABELS, fmtMetric, shortDate } from '../../components/c/helpers'
import { api, applyChanges, notifyProjectChanged, type Json } from '../../api'
import { fmtValue } from '../../format'
import { useFetch } from '../../state'

const SOURCES = ['all', 'user', 'researched', 'demo', 'default', 'chatbot', 'empty']

export default function Assumptions() {
  const { data } = useProject()
  const pid = data.project.id
  const cur = data.project.profile.currency || 'MXN'
  const { data: tbl, loading } = useFetch<Json>(`/api/projects/${pid}/assumptions`)
  const [section, setSection] = useState('all')
  const [source, setSource] = useState('all')
  const [pendingOnly, setPendingOnly] = useState(false)
  const [missingOnly, setMissingOnly] = useState(false)
  const [q, setQ] = useState('')
  const [edit, setEdit] = useState<Json>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const rows: Json[] = useMemo(() => tbl?.rows || [], [tbl])
  const srcOf = (r: Json) => (r.value == null ? 'empty' : (r.source || '').startsWith('default') ? 'default' : (r.source || '').startsWith('chatbot') ? 'chatbot' : r.source)
  const filtered = rows.filter((r) =>
    (section === 'all' || r.section === section) && (source === 'all' || srcOf(r) === source) && (!pendingOnly || r.proposal) &&
    (!missingOnly || r.missing) && (!q || `${r.label} ${r.key}`.toLowerCase().includes(q.toLowerCase())))
  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    rows.forEach((r) => { const s = srcOf(r); c[s] = (c[s] || 0) + 1 })
    return c
  }, [rows])
  const sections = Array.from(new Map(rows.map((r) => [r.section, r.section_label])).entries())
  const pendingCount = rows.filter((r) => r.proposal).length
  const missingCount = rows.filter((r) => r.missing).length

  const applyDefaults = async () => {
    const r = await api.post(`/api/projects/${pid}/suggested-defaults`)
    setMsg(`Applied ${r.applied?.length ?? 0} suggested defaults (labelled "default (unverified)").`)
    notifyProjectChanged(pid)
  }

  if (loading && !tbl) return <Loading />
  let lastSection = ''
  return (
    <>
      <PageHead eyebrow="Governance" title="Assumption Control Center"
        actions={<button className="btn" onClick={applyDefaults}><Wand2 size={14} /> Apply suggested defaults to empty fields</button>}>
        Every input in one place, with its source, date and verification status. AI-researched values stay pending until you approve them; outputs are calculated and never editable.
      </PageHead>
      <div className="col" style={{ gap: 16 }}>
        {msg && <Callout tone="good">{msg}</Callout>}
        <div className="row wrap" style={{ gap: 6 }}>
          {Object.entries(counts).map(([k, v]) => <span key={k} className="badge">{k === 'demo' ? 'fictional demo' : k}: {v}</span>)}
          <span className={`badge ${pendingCount ? 'pending' : ''}`}>pending AI proposals: {pendingCount}</span>
          <span className={`badge ${missingCount ? 'bad' : 'good'}`}>missing required: {missingCount}</span>
        </div>
        <Card>
          <div className="row wrap" style={{ marginBottom: 12, alignItems: 'flex-end' }}>
            <label className="field" style={{ width: 210 }}>Section
              <select className="input" value={section} onChange={(e) => setSection(e.target.value)}>
                <option value="all">All sections</option>{sections.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select></label>
            <label className="field" style={{ width: 170 }}>Source
              <select className="input" value={source} onChange={(e) => setSource(e.target.value)}>{SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
            <label className="field grow" style={{ minWidth: 180 }}>Search<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="variable or key…" /></label>
            <label className="row small" style={{ gap: 4 }}><input type="checkbox" checked={pendingOnly} onChange={(e) => setPendingOnly(e.target.checked)} /> Pending proposals only</label>
            <label className="row small" style={{ gap: 4 }}><input type="checkbox" checked={missingOnly} onChange={(e) => setMissingOnly(e.target.checked)} /> Missing only</label>
          </div>
          <div className="table-wrap" style={{ maxHeight: 640 }}>
            <table className="t">
              <thead><tr><th>Variable</th><th className="num">Current value</th><th>Unit</th><th>Source</th><th>Date</th><th>Verification</th><th>Modified by</th><th>Flags</th><th /></tr></thead>
              <tbody>
                {filtered.map((r) => {
                  const header = r.section !== lastSection
                  lastSection = r.section
                  return (
                    <Fragment key={r.key}>
                      {header && <tr className="group"><td colSpan={9}>{r.section_label}</td></tr>}
                      <tr style={r.missing ? { background: 'var(--critical-soft)' } : undefined}>
                        <td><div style={{ fontWeight: 550 }}>{r.label}</div><div className="tiny muted">{r.key}</div></td>
                        <td className="num" style={{ fontWeight: 600 }}>{fmtValue(r.value, r.unit, cur)}</td>
                        <td className="small muted">{r.unit.replace('area', 'm²').replace('currency', cur)}</td>
                        <td><SourceBadge source={r.value == null ? null : r.source} />
                          {r.source_url && <a className="tiny" href={r.source_url} target="_blank" rel="noreferrer" style={{ marginLeft: 4 }}><ExternalLink size={11} /></a>}</td>
                        <td className="small">{shortDate(r.updated_at)}</td>
                        <td className="small">{r.verification ? <span className={`badge ${['verified', 'published_rate', 'published_benchmark'].includes(r.verification) ? 'good' : 'warn'}`}>{r.verification}</span> : r.confidence ? <span className="muted">{r.confidence}</span> : '—'}</td>
                        <td className="small">{r.updated_by || '—'}</td>
                        <td className="small">
                          <div className="row wrap" style={{ gap: 4 }}>
                            {r.required && <span className="badge">required</span>}
                            {r.material && <span className="badge warn">material</span>}
                            {r.regulatory && <span className="badge">legal limit</span>}
                            {r.noncompliant_override && <StatusBadge level="bad">override of {String(r.override_of)}</StatusBadge>}
                            {r.missing && <StatusBadge level="red">missing</StatusBadge>}
                          </div>
                        </td>
                        <td><button className="btn ghost sm" onClick={() => setEdit(r)} title="Edit"><Pencil size={13} /></button></td>
                      </tr>
                      {r.proposal && (
                        <tr><td colSpan={9} style={{ paddingTop: 0 }}><ProposalRow pid={pid} k={r.key} proposal={r.proposal} unit={r.unit} cur={cur} /></td></tr>
                      )}
                    </Fragment>
                  )
                })}
                {!filtered.length && <tr><td colSpan={9} className="empty">No variables match the filters.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Calculated outputs" sub="Produced by the deterministic engine from the inputs above — not editable.">
          {tbl?.calculated?.length ? (
            <table className="t"><thead><tr><th>Output</th><th className="num">Value</th><th>Source</th></tr></thead>
              <tbody>{tbl.calculated.map((c: Json) => {
                const k = c.key.replace('calc.', '')
                return <tr key={c.key}><td>{METRIC_LABELS[k] || c.label}</td><td className="num">{k === 'saleable_area' ? fmtValue(c.value, 'area') : fmtMetric(k, c.value, cur)}</td><td><SourceBadge source="calculated" /></td></tr>
              })}</tbody></table>
          ) : <div className="small muted">The model is incomplete — outputs appear once all required inputs are provided.</div>}
        </Card>
      </div>
      {edit && <EditModal row={edit} pid={pid} cur={cur} onClose={() => setEdit(null)} />}
    </>
  )
}

function EditModal({ row, pid, cur, onClose }: { row: Json; pid: number; cur: string; onClose: () => void }) {
  const [draft, setDraft] = useState(row.value == null ? '' : String(row.value))
  const [err, setErr] = useState<string | null>(null)
  const [warn, setWarn] = useState<string[]>([])
  const [confirm, setConfirm] = useState<Json>(null)
  const [busy, setBusy] = useState(false)
  const save = async (override = false) => {
    setBusy(true); setErr(null)
    try {
      let v: unknown = draft === '' ? null : draft
      if (row.kind === 'bool') v = draft === 'true'
      const res = await applyChanges(pid, [{ key: row.key, value: v }], { confirm_override: override, reason: 'Assumption Control Center edit' })
      if (res.rejected?.length) setErr(res.rejected[0].error)
      else if (res.needs_confirmation?.length) setConfirm(res.needs_confirmation[0])
      else if (res.warnings?.length) { setWarn(res.warnings); setTimeout(onClose, 1800) }
      else onClose()
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  if (confirm) return (
    <Modal title="Override a legal limit?" onClose={onClose}
      actions={<><button className="btn" onClick={onClose}>Keep legal value</button>
        <button className="btn primary" style={{ background: 'var(--critical)', borderColor: 'var(--critical)' }} onClick={() => save(true)} disabled={busy}>Create hypothetical scenario</button></>}>
      <Callout tone="bad"><b>{confirm.label}</b>: the approved research value is <b>{String(confirm.legal_reference)}</b>. Setting <b>{String(confirm.new)}</b> relaxes a legal restriction and flags the project as <b>potentially noncompliant</b>.</Callout>
    </Modal>
  )
  return (
    <Modal title={`Edit: ${row.label}`} onClose={onClose}
      actions={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={() => save()} disabled={busy}>Save</button></>}>
      <div className="col">
        <div className="small muted">{row.key} · current {fmtValue(row.value, row.unit, cur)} · range {row.min ?? '—'}–{row.max ?? '—'}{row.typical ? ` · typical ${row.typical[0]}–${row.typical[1]}` : ''}</div>
        {row.kind === 'choice' ? (
          <select className="input" value={draft} onChange={(e) => setDraft(e.target.value)}><option value="">—</option>{row.choices.map((c: string) => <option key={c}>{c}</option>)}</select>
        ) : row.kind === 'bool' ? (
          <select className="input" value={draft} onChange={(e) => setDraft(e.target.value)}><option value="true">Yes</option><option value="false">No</option></select>
        ) : (
          <input className="input" autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && save()}
            placeholder={row.suggested != null ? `suggested ${row.suggested} (unverified)` : ''} />
        )}
        {row.help && <div className="tiny muted">{row.help}</div>}
        {row.material && <Callout tone="warn">Material variable: changes are recorded in the audit trail.</Callout>}
        {err && <Callout tone="bad">{err}</Callout>}
        {warn.length > 0 && <Callout tone="warn">Saved with warnings: {warn.join(' ')}</Callout>}
      </div>
    </Modal>
  )
}

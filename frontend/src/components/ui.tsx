/* eslint-disable react-refresh/only-export-components */
import { useState, type ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, CircleAlert, ExternalLink, Info, Pencil, ShieldAlert, X } from 'lucide-react'
import { applyChanges, type Json } from '../api'
import { fmtValue } from '../format'
import { useMeta, type ProjectData } from '../state'

export function PageHead({ eyebrow, title, children, actions }: { eyebrow?: string; title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {children && <p>{children}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </div>
  )
}

export function Card({ title, sub, actions, children, className = '', bodyClass = '' }: {
  title?: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string
}) {
  return (
    <div className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-h">
          <div>{typeof title === 'string' ? <h2>{title}</h2> : title}{sub && <div className="card-sub">{sub}</div>}</div>
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      <div className={`card-b ${bodyClass}`}>{children}</div>
    </div>
  )
}

export function Kpi({ label, value, sub, hero, tone }: { label: string; value: ReactNode; sub?: ReactNode; hero?: boolean; tone?: 'good' | 'bad' | 'warn' }) {
  const color = tone === 'good' ? 'var(--good-text)' : tone === 'bad' ? 'var(--critical)' : tone === 'warn' ? 'var(--warning-text)' : undefined
  return (
    <div className={`card kpi ${hero ? 'hero' : ''}`}>
      <div className="label">{label}</div>
      <div className="value" style={{ color }}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

const SOURCE_CLASS: Record<string, string> = {
  user: 'user', researched: 'researched', demo: 'demo', 'default (unverified)': 'default', chatbot: 'chatbot',
  'chatbot (confirmed)': 'chatbot', calculated: 'calculated', system: 'default',
}
export function SourceBadge({ source }: { source?: string | null }) {
  if (!source) return <span className="badge default">empty</span>
  const label = source === 'demo' ? 'fictional demo' : source
  return <span className={`badge ${SOURCE_CLASS[source] || ''}`}>{label}</span>
}

export function StatusBadge({ level, children }: { level: 'good' | 'warn' | 'bad' | 'red' | 'amber' | 'info'; children: ReactNode }) {
  const cls = level === 'red' ? 'bad' : level === 'amber' ? 'warn' : level === 'info' ? '' : level
  const Icon = cls === 'good' ? CheckCircle2 : cls === 'bad' ? CircleAlert : cls === 'warn' ? AlertTriangle : Info
  return <span className={`badge ${cls}`}><Icon size={11} />{children}</span>
}

export function Callout({ tone = 'info', children, icon }: { tone?: 'info' | 'warn' | 'bad' | 'good'; children: ReactNode; icon?: ReactNode }) {
  const Icon = tone === 'bad' ? ShieldAlert : tone === 'warn' ? AlertTriangle : tone === 'good' ? CheckCircle2 : Info
  return <div className={`callout ${tone}`}>{icon ?? <Icon size={16} style={{ flexShrink: 0, marginTop: 1 }} />}<div>{children}</div></div>
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <div className="empty"><span className="spinner" /> <span style={{ marginLeft: 8 }}>{label}</span></div>
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function Modal({ title, children, onClose, actions }: { title: string; children: ReactNode; onClose: () => void; actions?: ReactNode }) {
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="row between" style={{ marginBottom: 12 }}><h2>{title}</h2><button className="btn ghost sm" onClick={onClose}><X size={14} /></button></div>
        {children}
        {actions && <div className="row" style={{ justifyContent: 'flex-end', marginTop: 16 }}>{actions}</div>}
      </div>
    </div>
  )
}

export function ModelIncomplete({ results }: { results: Json }) {
  if (!results || results.status === 'ok') return null
  const items: string[] = results.missing_labels || results.errors || []
  return (
    <Callout tone="warn">
      <b>The financial model can't run yet.</b> {results.status === 'incomplete' ? 'Missing inputs: ' : ''}
      {items.join(', ')}. No metrics are shown until these are provided — TerraMind never fills them in silently.
    </Callout>
  )
}

/** Inline editor for one registry variable. Uses the validated write path; regulatory loosening asks for confirmation. */
export function FieldEditor({ data, k, compact }: { data: ProjectData; k: string; compact?: boolean }) {
  const meta = useMeta()
  const spec = meta.registry[k]
  const p = data.project
  const value = p.assumptions[k]
  const m = p.meta[k] || {}
  const cur = p.profile.currency || 'MXN'
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<string>('')
  const [err, setErr] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<Json>(null)
  const [busy, setBusy] = useState(false)
  if (!spec) return null

  const start = () => { setDraft(value === null || value === undefined ? '' : String(value)); setErr(null); setEditing(true) }
  const save = async (override = false) => {
    setBusy(true)
    try {
      let v: unknown = draft
      if (spec.kind === 'bool') v = draft === 'true'
      if (draft === '') v = null
      const res = await applyChanges(p.id, [{ key: k, value: v }], { confirm_override: override })
      if (res.rejected?.length) setErr(res.rejected[0].error)
      else if (res.needs_confirmation?.length) setConfirm(res.needs_confirmation[0])
      else { setEditing(false); setConfirm(null) }
    } catch (e) { setErr(String((e as Error).message)) } finally { setBusy(false) }
  }
  const proposal = m.proposal && m.proposal.status === 'pending' ? m.proposal : null
  return (
    <div style={{ padding: compact ? '6px 0' : '8px 0', borderBottom: '1px solid var(--border)' }}>
      <div className="row between" style={{ alignItems: 'flex-start' }}>
        <div className="grow">
          <div className="small" style={{ color: 'var(--text-2)', fontWeight: 550 }}>
            {spec.label}{spec.material && <span className="tiny muted"> · material</span>}{spec.regulatory && <span className="tiny muted"> · legal limit</span>}
          </div>
          {!editing && (
            <div className="row" style={{ gap: 8, marginTop: 2 }}>
              <span className="num" style={{ fontWeight: 600, fontSize: 14 }}>{fmtValue(value, spec.unit, cur)}</span>
              <SourceBadge source={value == null ? null : m.source} />
              {m.verification && <span className={`badge ${m.verification === 'verified' || m.verification === 'published_rate' ? 'good' : 'warn'}`}>{m.verification}</span>}
              {m.noncompliant_override && <StatusBadge level="bad">override of {String(m.override_of)}</StatusBadge>}
              {m.source_url && <a href={m.source_url} target="_blank" rel="noreferrer" className="tiny"><ExternalLink size={11} /> source</a>}
            </div>
          )}
        </div>
        {!editing && <button className="btn ghost sm" onClick={start} title="Edit"><Pencil size={13} /></button>}
      </div>
      {editing && (
        <div className="row" style={{ marginTop: 6, gap: 6 }}>
          {spec.kind === 'choice' ? (
            <select className="input" value={draft} onChange={(e) => setDraft(e.target.value)}>
              <option value="">—</option>{spec.choices!.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          ) : spec.kind === 'bool' ? (
            <select className="input" value={draft} onChange={(e) => setDraft(e.target.value)}><option value="true">Yes</option><option value="false">No</option></select>
          ) : (
            <input className="input" autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && save()}
              placeholder={spec.suggested != null ? `suggested ${spec.suggested}` : spec.unit} />
          )}
          <span className="tiny muted" style={{ whiteSpace: 'nowrap' }}>{spec.unit.replace('area', 'm²').replace('currency', cur)}</span>
          <button className="btn primary sm" disabled={busy} onClick={() => save()}>Save</button>
          <button className="btn ghost sm" onClick={() => setEditing(false)}>Cancel</button>
        </div>
      )}
      {editing && spec.help && <div className="tiny muted" style={{ marginTop: 4 }}>{spec.help}</div>}
      {err && <div className="tiny" style={{ color: 'var(--critical)', marginTop: 4 }}>{err}</div>}
      {proposal && <ProposalRow pid={p.id} k={k} proposal={proposal} unit={spec.unit} cur={cur} />}
      {confirm && (
        <Modal title="Override a legal limit?" onClose={() => setConfirm(null)}
          actions={<><button className="btn" onClick={() => setConfirm(null)}>Keep legal value</button>
            <button className="btn primary" style={{ background: 'var(--critical)', borderColor: 'var(--critical)' }} onClick={() => save(true)}>Create hypothetical scenario</button></>}>
          <Callout tone="bad">
            <b>{confirm.label}</b>: the approved research value is <b>{String(confirm.legal_reference)}</b>. Setting it to <b>{String(confirm.new)}</b> relaxes a
            legal restriction. The project will be flagged <b>potentially noncompliant</b> and shown as a hypothetical scenario.
          </Callout>
        </Modal>
      )}
    </div>
  )
}

export function ProposalRow({ pid, k, proposal, unit, cur }: { pid: number; k: string; proposal: Json; unit: string; cur: string }) {
  const [busy, setBusy] = useState(false)
  const act = async (action: 'approve' | 'reject') => {
    setBusy(true)
    try {
      const { api, notifyProjectChanged } = await import('../api')
      await api.post(`/api/projects/${pid}/proposals/${k}/${action}`)
      notifyProjectChanged(pid)
    } finally { setBusy(false) }
  }
  return (
    <div className="callout info" style={{ marginTop: 6, padding: '6px 10px', alignItems: 'center' }}>
      <div className="grow small">
        <b>AI proposal:</b> {fmtValue(proposal.value, unit, cur)} <span className={`badge ${proposal.verification === 'verified' || proposal.verification === 'published_rate' ? 'good' : 'warn'}`}>{proposal.verification}</span>{' '}
        <span className="muted">{proposal.agent}{proposal.source_title ? ` · ${proposal.source_title}` : ''}</span>
        {proposal.source_url && <> · <a href={proposal.source_url} target="_blank" rel="noreferrer">source</a></>}
        {proposal.note && <div className="tiny muted">{proposal.note}</div>}
      </div>
      <button className="btn sm primary" disabled={busy} onClick={() => act('approve')}>Approve</button>
      <button className="btn sm" disabled={busy} onClick={() => act('reject')}>Reject</button>
    </div>
  )
}

export function FieldGroup({ data, keys, title, sub, cols = 2 }: { data: ProjectData; keys: string[]; title?: string; sub?: string; cols?: number }) {
  return (
    <Card title={title} sub={sub}>
      <div className="grid" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, columnGap: 24, rowGap: 0 }}>
        {keys.map((k) => <FieldEditor key={k} data={data} k={k} compact />)}
      </div>
    </Card>
  )
}

export function ChartTip({ active, payload, label, fmt, labelFmt }: { active?: boolean; payload?: Json[]; label?: Json; fmt?: (v: number, name: string) => string; labelFmt?: (l: Json) => string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tip">
      <div className="tt">{labelFmt ? labelFmt(label) : label}</div>
      {payload.map((p: Json) => (
        <div key={p.dataKey} className="row" style={{ gap: 6 }}>
          <span className="sw" style={{ width: 8, height: 8, borderRadius: 2, background: p.color || p.fill, display: 'inline-block' }} />
          <span className="muted">{p.name}</span><span className="num" style={{ marginLeft: 'auto', fontWeight: 600 }}>{fmt ? fmt(p.value, p.name) : p.value}</span>
        </div>
      ))}
    </div>
  )
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return <div className="legend">{items.map((i) => <span key={i.label}><span className="sw" style={{ background: i.color }} />{i.label}</span>)}</div>
}

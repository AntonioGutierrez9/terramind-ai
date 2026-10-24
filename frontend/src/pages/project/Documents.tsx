import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, Download, FileSpreadsheet, FileText, Image as ImageIcon, MessageSquareQuote, ShieldAlert, Trash2, Upload } from 'lucide-react'
import { api, notifyProjectChanged, uploadDocument, type Json } from '../../api'
import { useProject } from '../../components/Layout'
import { Callout, Card, Empty, PageHead, StatusBadge } from '../../components/ui'
import { fmtValue } from '../../format'
import { useFetch, useMeta } from '../../state'

const TYPE_LABEL: Record<string, string> = {
  zoning_certificate: 'Zoning certificate', building_permit: 'Building permit', license: 'License', financial_model: 'Financial model',
  construction_budget: 'Construction budget', contract: 'Contract', loan_term_sheet: 'Loan term sheet', appraisal: 'Appraisal',
  title: 'Title document', market_study: 'Market study', other: 'Other',
}
const KIND_ICON: Record<string, typeof FileText> = { excel: FileSpreadsheet, image: ImageIcon }

function kb(n: number) { return n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB` }

export default function Documents() {
  const { data } = useProject()
  const p = data.project
  const { data: docs, reload } = useFetch<Json[]>(`/api/projects/${p.id}/documents`)
  const [sel, setSel] = useState<number | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [auto, setAuto] = useState(true)
  const [drag, setDrag] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => { if (docs?.length && sel == null) setSel(docs[0].id) }, [docs, sel])
  useEffect(() => {
    if (!busy) return
    const t0 = Date.now(); const iv = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 500)
    return () => clearInterval(iv)
  }, [busy])

  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setErr(null)
    for (const f of Array.from(files)) {
      setBusy(f.name)
      try {
        const r = await uploadDocument(p.id, f, auto)
        setSel(r.document.id)
        if (r.status === 'limit_reached') setErr(`Uploaded, but analysis stopped: ${r.detail}`)
      } catch (e) { setErr(`${f.name}: ${(e as Error).message}`) }
    }
    setBusy(null)
    reload()
  }

  return (
    <div>
      <PageHead eyebrow="Documents" title="Documents & files">
        Upload permits, zoning certificates, contracts, appraisals, budgets or an Excel model. The Document agent extracts the facts,
        proposes values for your model (pending until you approve them), reviews contracts, and answers questions with quotes.
      </PageHead>

      <div className="card" style={{ padding: 18, marginBottom: 16, borderStyle: 'dashed', borderWidth: 2, borderColor: drag ? 'var(--accent)' : 'var(--border-strong)', background: drag ? 'var(--accent-soft)' : 'var(--surface)' }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files) }}>
        <div className="row between wrap">
          <div className="row" style={{ gap: 14 }}>
            <div className="brand-mark" style={{ width: 44, height: 44 }}><Upload size={20} color="#fff" /></div>
            <div>
              <div style={{ fontWeight: 600 }}>Drop files here or choose from your computer</div>
              <div className="small muted">PDF (including scans), Excel .xlsx, Word .docx, CSV, TXT, or photos (PNG/JPG) · up to 15 MB · stored privately for your account</div>
            </div>
          </div>
          <div className="row">
            <label className="small row" style={{ gap: 6 }}><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> Analyze automatically</label>
            <button className="btn primary" disabled={!!busy} onClick={() => input.current?.click()}><Upload size={14} /> Upload</button>
            <input ref={input} type="file" multiple hidden accept=".pdf,.xlsx,.xlsm,.docx,.csv,.txt,.md,.png,.jpg,.jpeg,.webp" onChange={(e) => { upload(e.target.files); e.target.value = '' }} />
          </div>
        </div>
        {busy && <div className="callout info small" style={{ marginTop: 12 }}><span className="spinner" /> Reading <b>{busy}</b>{auto ? ' and analyzing it with the Document agent' : ''}… {elapsed}s</div>}
        {err && <div className="callout warn small" style={{ marginTop: 12 }}>{err}</div>}
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'minmax(260px, 320px) minmax(0, 1fr)', alignItems: 'start' }}>
        <Card title="Files" sub={`${docs?.length ?? 0} uploaded`}>
          {!docs?.length && <Empty>No files yet. Try the fictional samples in <code>docs/samples/</code>.</Empty>}
          <div className="col" style={{ gap: 6 }}>
            {docs?.map((d) => {
              const Icon = KIND_ICON[d.kind] || FileText
              return (
                <button key={d.id} onClick={() => setSel(d.id)} className="card flat" style={{ textAlign: 'left', padding: 10, cursor: 'pointer', borderColor: sel === d.id ? 'var(--accent)' : undefined, background: sel === d.id ? 'var(--accent-soft)' : undefined }}>
                  <div className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                    <Icon size={16} style={{ marginTop: 2, flexShrink: 0 }} />
                    <div className="grow">
                      <div style={{ fontWeight: 600, fontSize: 13, wordBreak: 'break-word' }}>{d.filename}</div>
                      <div className="tiny muted">{d.analysis ? TYPE_LABEL[d.analysis.doc_type] || d.analysis.doc_type : 'not analyzed'} · {kb(d.size)} · {d.created_at.slice(0, 10)}</div>
                      {d.meta?.injection_warning && <div className="tiny" style={{ color: 'var(--critical)' }}><ShieldAlert size={11} /> contains instructions aimed at AI</div>}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        </Card>
        {sel ? <DocumentDetail key={sel} docId={sel} pid={p.id} onDeleted={() => { setSel(null); reload() }} onChanged={reload} meta={p.meta} cur={p.profile.currency || 'MXN'} assumptions={p.assumptions} />
          : <Card><Empty>Select a file to see its analysis.</Empty></Card>}
      </div>
    </div>
  )
}

function DocumentDetail({ docId, pid, onDeleted, onChanged, meta, cur, assumptions }: {
  docId: number; pid: number; onDeleted: () => void; onChanged: () => void; meta: Json; cur: string; assumptions: Json
}) {
  const reg = useMeta().registry
  const { data: d, reload } = useFetch<Json>(`/api/documents/${docId}`)
  const [busy, setBusy] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [answer, setAnswer] = useState<Json>(null)
  const [err, setErr] = useState<string | null>(null)
  if (!d) return <Card><div className="empty"><span className="spinner" /></div></Card>
  const a = d.analysis
  const cr = a?.contract_review

  const analyze = async () => {
    setBusy('analyze'); setErr(null)
    try { const r = await api.post(`/api/documents/${docId}/analyze`); if (r.status === 'limit_reached') setErr(r.detail); reload(); onChanged(); notifyProjectChanged(pid) }
    catch (e) { setErr((e as Error).message) } finally { setBusy(null) }
  }
  const ask = async () => {
    if (!q.trim()) return
    setBusy('ask'); setErr(null); setAnswer(null)
    try { setAnswer(await api.post(`/api/documents/${docId}/ask`, { question: q })) } catch (e) { setErr((e as Error).message) } finally { setBusy(null) }
  }
  const del = async () => { if (!confirm(`Delete ${d.filename}?`)) return; await api.del(`/api/documents/${docId}`); onDeleted() }
  const act = async (key: string, action: 'approve' | 'reject') => {
    await api.post(`/api/projects/${pid}/proposals/${key}/${action}`); notifyProjectChanged(pid); onChanged()
  }
  const applyCode = async () => {
    await api.post(`/api/projects/${pid}/zoning-code`, { code: a.parsed_zoning_code?.code || a.zoning_code }); notifyProjectChanged(pid)
  }

  return (
    <div className="col" style={{ gap: 16 }}>
      <Card title={d.filename} sub={`${d.kind.toUpperCase()} · ${kb(d.size)} · uploaded ${d.created_at.slice(0, 16).replace('T', ' ')}`}
        actions={<>
          <a className="btn sm" href={`/api/documents/${docId}/file`}><Download size={13} /> File</a>
          <button className="btn sm" disabled={!!busy} onClick={analyze}>{busy === 'analyze' ? 'Analyzing…' : a ? 'Re-analyze' : 'Analyze'}</button>
          <button className="btn sm danger" onClick={del}><Trash2 size={13} /></button></>}>
        {d.meta?.injection_warning && (
          <Callout tone="bad"><b>This file contains text that tries to instruct AI systems</b> (e.g. "{String(d.meta.injection_warning[0]).slice(0, 120)}…").
            TerraMind treats file content as data: it cannot change your model or approve anything. Review the source carefully.</Callout>
        )}
        {d.meta?.note && <div className="small muted" style={{ marginTop: 6 }}>{d.meta.note}</div>}
        {err && <Callout tone="warn">{err}</Callout>}
        {!a && <Callout tone="info">Not analyzed yet. Click <b>Analyze</b> to extract facts and proposals (≈ $0.001–0.002 per file).</Callout>}
        {a && (
          <div className="col" style={{ gap: 10, marginTop: 6 }}>
            <div className="row wrap" style={{ gap: 8 }}>
              <span className="badge">{TYPE_LABEL[a.doc_type] || a.doc_type}</span>
              {a.vision && <span className="badge warn">read from image / scan</span>}
              {a.usage && <span className="tiny muted">analysis cost ${a.usage.cost_usd?.toFixed(4)} · {a.usage.seconds}s</span>}
            </div>
            <div style={{ fontWeight: 600 }}>{a.title}</div>
            <div className="small" style={{ color: 'var(--text-2)' }}>{a.summary}</div>
          </div>
        )}
      </Card>

      {a?.accepted_proposals?.length > 0 && (
        <Card title="Values for your model" sub="Each value was found verbatim in the document. Nothing changes until you approve it.">
          <table className="t">
            <thead><tr><th>Variable</th><th className="num">Current</th><th className="num">From document</th><th>Evidence</th><th>Status</th></tr></thead>
            <tbody>
              {a.accepted_proposals.map((pr: Json) => {
                const m = meta[pr.key] || {}
                const pending = m.proposal?.status === 'pending' && m.proposal?.agent === `document: ${d.filename}`
                const unit = reg[pr.key]?.unit || ''
                return (
                  <tr key={pr.key}>
                    <td style={{ fontWeight: 550 }}>{reg[pr.key]?.label || pr.key}<div className="tiny muted">{pr.key}</div></td>
                    <td className="num">{fmtValue(assumptions[pr.key], unit, cur)}</td>
                    <td className="num" style={{ fontWeight: 600 }}>{fmtValue(pr.value, unit, cur)}</td>
                    <td className="small muted" style={{ maxWidth: 320 }}>{pr.note}</td>
                    <td>
                      {pending && assumptions[pr.key] === pr.value ? (
                        <div className="row" style={{ gap: 4 }}><StatusBadge level="good">matches model</StatusBadge>
                          <button className="btn sm ghost" title="Record the document as the source" onClick={() => act(pr.key, 'approve')}>Cite</button></div>
                      ) : pending ? (
                        <div className="row" style={{ gap: 4 }}>
                          <button className="btn sm primary" onClick={() => act(pr.key, 'approve')}>Approve</button>
                          <button className="btn sm" onClick={() => act(pr.key, 'reject')}>Reject</button>
                        </div>
                      ) : assumptions[pr.key] === pr.value ? <StatusBadge level="good">in model</StatusBadge> : <span className="badge default">resolved</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {a.parsed_zoning_code && (
            <div className="callout info small" style={{ marginTop: 10 }}>
              Zoning code <b>{a.parsed_zoning_code.code}</b> found in the document. <button className="btn sm" onClick={applyCode}>Apply code to legal limits</button>
            </div>
          )}
          {a.rejected_proposals?.length > 0 && (
            <details className="small" style={{ marginTop: 10 }}>
              <summary className="muted" style={{ cursor: 'pointer' }}>{a.rejected_proposals.length} value(s) discarded by TerraMind's checks</summary>
              {a.rejected_proposals.map((r: Json, i: number) => <div key={i} className="tiny muted">• {r.key} = {String(r.value)}: {r.reason}</div>)}
            </details>
          )}
        </Card>
      )}

      {a?.key_facts?.length > 0 && (
        <Card title="Key facts">
          <table className="t"><tbody>
            {a.key_facts.map((f: Json, i: number) => <tr key={i}><td className="muted" style={{ width: '35%' }}>{f.label}</td><td>{f.value}</td><td className="tiny muted">{f.location}</td></tr>)}
          </tbody></table>
        </Card>
      )}

      {a?.permit && (a.permit.permit_type || a.permit.number) && (
        <Card title="Permit / license">
          <table className="t"><tbody>
            {[['Type', a.permit.permit_type], ['Number', a.permit.number], ['Issuer', a.permit.issuer], ['Issued', a.permit.issue_date], ['Expires', a.permit.expiry_date]].map(([k, v]) => v ? <tr key={k}><td className="muted">{k}</td><td>{v}</td></tr> : null)}
          </tbody></table>
          {a.permit.conditions?.length > 0 && <ul className="small">{a.permit.conditions.map((c: string, i: number) => <li key={i}>{c}</li>)}</ul>}
        </Card>
      )}

      {cr && (cr.risks?.length > 0 || cr.parties?.length > 0) && (
        <Card title="Contract review" sub="Decision support for your conversation with counsel, not legal advice">
          {cr.parties?.length > 0 && <div className="small" style={{ marginBottom: 8 }}><b>Parties:</b> {cr.parties.join(' · ')}</div>}
          {cr.risks?.length > 0 && (
            <table className="t">
              <thead><tr><th>Severity</th><th>Clause</th><th>Issue</th><th>Suggestion</th></tr></thead>
              <tbody>{cr.risks.map((r: Json, i: number) => (
                <tr key={i}><td><span className={`badge ${r.severity === 'high' ? 'bad' : r.severity === 'medium' ? 'warn' : ''}`}>{r.severity}</span></td>
                  <td style={{ fontWeight: 550 }}>{r.clause}</td><td className="small">{r.issue}</td><td className="small">{r.suggestion}</td></tr>))}</tbody>
            </table>
          )}
          <div className="grid g3" style={{ marginTop: 10 }}>
            {[['Deadlines', (cr.deadlines || []).map((x: Json) => `${x.what}: ${x.date}`)], ['Payment terms', cr.payment_terms || []], ['Missing protections', cr.missing_protections || []]].map(([t, items]) => (
              <div key={t as string}><div className="small" style={{ fontWeight: 600 }}>{t}</div><ul className="small" style={{ paddingLeft: 16, margin: '4px 0' }}>{(items as string[]).map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            ))}
          </div>
          {cr.questions_for_counsel?.length > 0 && <div className="small"><b>Questions for your lawyer:</b><ul style={{ paddingLeft: 16 }}>{cr.questions_for_counsel.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></div>}
        </Card>
      )}

      {a?.model_notes?.length > 0 && (
        <Card title="Model comparison" sub="Assumptions in the uploaded model vs. TerraMind's current values">
          <ul className="small" style={{ paddingLeft: 16 }}>{a.model_notes.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
        </Card>
      )}

      <Card title="Ask about this file" sub="Answers come only from the document, with quotes TerraMind checks against the text">
        <div className="row" style={{ gap: 6 }}>
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && ask()}
            placeholder={a?.doc_type === 'contract' ? 'e.g. What happens to the deposit if we cannot close?' : 'e.g. When does the permit expire?'} />
          <button className="btn primary" disabled={busy === 'ask' || !q.trim()} onClick={ask}><MessageSquareQuote size={14} /> {busy === 'ask' ? 'Reading…' : 'Ask'}</button>
        </div>
        {answer && (
          <div className="col" style={{ gap: 8, marginTop: 12 }}>
            <div className="small" style={{ whiteSpace: 'pre-wrap' }}>{answer.answer}</div>
            {!answer.found_in_document && <Callout tone="warn">The document does not answer this directly.</Callout>}
            {answer.quotes?.map((qt: Json, i: number) => (
              <div key={i} className="callout small" style={{ padding: '6px 10px' }}>
                {qt.verified ? <CheckCircle2 size={14} color="var(--good)" /> : <ShieldAlert size={14} color="var(--warning-text)" />}
                <div><i>"{qt.quote}"</i> <span className="tiny muted">{qt.location} · {qt.verified ? 'quote found in the document' : 'quote not matched verbatim'}</span></div>
              </div>
            ))}
            {answer.turn_usage && <div className="tiny muted">cost ${answer.turn_usage.total.cost_usd.toFixed(4)}</div>}
          </div>
        )}
      </Card>

      {a?.caveats?.length > 0 && <Callout tone="info"><b>Caveats:</b> {a.caveats.join(' · ')}</Callout>}
      <details className="card" style={{ padding: 12 }}>
        <summary className="small" style={{ cursor: 'pointer', fontWeight: 600 }}>Extracted text (first 5,000 characters)</summary>
        <pre className="small" style={{ whiteSpace: 'pre-wrap', maxHeight: 360, overflow: 'auto', marginTop: 8 }}>{d.text_preview || '(no text layer: read by the vision model)'}</pre>
      </details>
    </div>
  )
}

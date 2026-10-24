import { Fragment, useState } from 'react'
import { ShieldCheck, Undo2 } from 'lucide-react'
import { useProject } from '../../components/Layout'
import { Callout, Card, Loading, PageHead } from '../../components/ui'
import { ActorBadge, shortDate, shortVal } from '../../components/c/helpers'
import { api, notifyProjectChanged, type Json } from '../../api'
import { useFetch } from '../../state'

export default function History() {
  const { data } = useProject()
  const pid = data.project.id
  const { data: hist, loading } = useFetch<Json[]>(`/api/projects/${pid}/history`)
  const { data: pending } = useFetch<Json[]>(`/api/projects/${pid}/pending`)
  const [msg, setMsg] = useState<string | null>(null)

  const undo = async () => {
    const r = await api.post(`/api/projects/${pid}/undo`)
    setMsg(r.undone?.length ? `Undid: ${r.undone.map((u: Json) => u.label).join(', ')}` : 'Nothing to undo.')
    notifyProjectChanged(pid)
  }
  const resolve = async (id: number, action: 'confirm' | 'reject') => {
    await api.post(`/api/pending/${id}/${action}`)
    notifyProjectChanged(pid)
  }

  const batches: { id: string; rows: Json[] }[] = []
  for (const r of hist || []) {
    const last = batches[batches.length - 1]
    if (last && last.id === r.batch_id) last.rows.push(r)
    else batches.push({ id: r.batch_id, rows: [r] })
  }

  return (
    <>
      <PageHead eyebrow="Governance" title="Audit trail" actions={<button className="btn" onClick={undo}><Undo2 size={14} /> Undo last change</button>}>
        Every change to the project — from forms, the chatbot or agents — with who made it, the old and new value and the reason. Changes made together form one batch and are undone together.
      </PageHead>
      <div className="col" style={{ gap: 16 }}>
        {msg && <Callout tone="good">{msg}</Callout>}
        {pending && pending.length > 0 && (
          <Card title="Pending confirmations" sub="Material changes requested by the chatbot. Only you can confirm them.">
            <div className="col" style={{ gap: 8 }}>
              {pending.map((p) => (
                <div key={p.id} className="callout warn" style={{ alignItems: 'center' }}>
                  <ShieldCheck size={16} style={{ flexShrink: 0 }} />
                  <div className="grow small">
                    <b>#{p.id}</b> requested by {p.requested_by} · {shortDate(p.created_at)}{p.reason ? ` · ${p.reason}` : ''}
                    <div>{p.kind === 'status' ? `Project status → ${p.changes.status}` :
                      p.changes.map((c: Json) => `${c.label}: ${shortVal(c.old)} → ${shortVal(c.new)}`).join(' · ')}</div>
                  </div>
                  <button className="btn sm primary" onClick={() => resolve(p.id, 'confirm')}>Confirm</button>
                  <button className="btn sm" onClick={() => resolve(p.id, 'reject')}>Reject</button>
                </div>
              ))}
            </div>
          </Card>
        )}
        <Card title="Change history" sub={`${hist?.length ?? 0} entries (latest first)`}>
          {loading && !hist ? <Loading /> : !hist?.length ? <div className="small muted">No changes recorded yet.</div> : (
            <div className="table-wrap" style={{ maxHeight: 680 }}>
              <table className="t">
                <thead><tr><th>Time</th><th>Actor</th><th>Variable</th><th className="num">Old</th><th /><th className="num">New</th><th>Reason</th></tr></thead>
                <tbody>
                  {batches.map((b) => (
                    <Fragment key={b.id}>
                      {b.rows.map((r, i) => (
                        <tr key={r.id} style={{ opacity: r.undone ? 0.55 : 1, textDecoration: r.undone ? 'line-through' : undefined, borderTop: i === 0 ? '2px solid var(--border-strong)' : undefined }}>
                          <td className="small">{i === 0 ? shortDate(r.at) : ''}</td>
                          <td>{i === 0 ? <ActorBadge actor={r.actor} /> : null}</td>
                          <td><div style={{ fontWeight: 550 }}>{r.label}</div><div className="tiny muted">{r.key}</div></td>
                          <td className="num small">{shortVal(r.old)}</td><td className="muted">→</td><td className="num small" style={{ fontWeight: 600 }}>{shortVal(r.new)}</td>
                          <td className="small muted">{r.reason || '—'}{r.undone ? ' (undone)' : ''}</td>
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  )
}

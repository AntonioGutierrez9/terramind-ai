import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bot, Check, Languages, Loader2, Mic, MicOff, Paperclip, Send, ShieldCheck, Wrench, X } from 'lucide-react'
import { api, notifyProjectChanged, streamChat, uploadDocument, type Json } from '../api'
import { useHealth } from '../state'
import { getLang, t } from '../i18n'

interface Msg { id?: number; role: 'user' | 'assistant'; content: string; extra?: Json; original?: string | null; lang?: string }
const toMsg = (x: Json): Msg => ({ id: x.id, role: x.role, content: x.content, extra: x.extra, original: x.original, lang: x.lang })

const SUGGESTIONS_PROJECT = [
  'Increase construction costs by 10%',
  'Assume we sell 4 apartments per month',
  'What happens to our equity IRR if construction takes six months longer?',
  "What's the maximum we should pay for the land for an 18% equity IRR?",
  'Compare the project with and without solar panels',
  'Change the average apartment size to 110 m²',
]
const SUGGESTIONS_HOME = [
  "I'm evaluating a 2,500 m² residential property in Polanco, Mexico City. The land costs MXN 120 million, and I want to use 60% bank financing.",
  'Which project in the portfolio has the most risk?',
]

const PAGE_LABEL: Record<string, string> = {
  property: 'Property & Zoning', design: 'Development Config', market: 'Market & Revenue', budget: 'Budget & Schedule',
  financing: 'Financing', model: 'Financial Model', sustainability: 'Sustainability', committee: 'Investment Committee',
  asset: 'Asset Management', assumptions: 'Assumption Center', portfolio: 'Portfolio', advisor: 'Recommendations', documents: 'Documents',
}

/* ---------- tiny markdown (bold, bullets, paragraphs) ---------- */
function md(text: string) {
  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const inline = (s: string) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`(.+?)`/g, '<code>$1</code>')
  const lines = text.split('\n')
  let html = '', inList = false, table: string[][] = []
  const flushTable = () => {
    if (!table.length) return
    const rows = table.filter((r) => !r.every((c) => /^\s*:?-{2,}:?\s*$/.test(c)))
    html += '<table class="t" style="margin:6px 0;font-size:12px"><thead><tr>' + rows[0].map((c) => `<th>${inline(c.trim())}</th>`).join('') + '</tr></thead><tbody>'
      + rows.slice(1).map((r) => '<tr>' + r.map((c) => `<td>${inline(c.trim())}</td>`).join('') + '</tr>').join('') + '</tbody></table>'
    table = []
  }
  for (const raw of lines) {
    const l = raw.trimEnd()
    if (/^\s*\|.*\|\s*$/.test(l)) { if (inList) { html += '</ul>'; inList = false } table.push(l.trim().slice(1, -1).split('|')); continue }
    flushTable()
    const m = l.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)/)
    if (m) { if (!inList) { html += '<ul>'; inList = true } html += `<li>${inline(m[1])}</li>`; continue }
    if (inList) { html += '</ul>'; inList = false }
    if (l.trim()) html += `<p>${inline(l)}</p>`
  }
  if (inList) html += '</ul>'
  flushTable()
  return { __html: html }
}

/* ---------- speech-to-text (browser Web Speech API; audio is never stored) ---------- */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const SR: any = typeof window !== 'undefined' ? ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition) : null

export default function ChatPanel({ projectId, onClose }: { projectId: number | null; onClose: () => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [live, setLive] = useState<Json[]>([])
  const [listening, setListening] = useState(false)
  const [micError, setMicError] = useState<string | null>(null)
  const [lang, setLang] = useState<'en-US' | 'es-MX'>(getLang() === 'es' ? 'es-MX' : 'en-US')
  const recRef = useRef<Json>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState<string | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const health = useHealth()
  const aiOff = health && health.ai_available === false

  const [translating, setTranslating] = useState(false)

  // Keep the whole conversation in the selected interface language: translate (cached per message on the server)
  // whenever the history is loaded, the language is switched, or a new turn finishes.
  const syncLanguage = async (keepRetry?: string, quiet = false) => {
    if (!quiet) setTranslating(true)
    try {
      const r = await api.post('/api/chat/translate', { project_id: projectId })
      const list: Msg[] = r.messages.map(toMsg)
      if (keepRetry && list.length && list[list.length - 1].role === 'assistant') list[list.length - 1].extra = { ...list[list.length - 1].extra, retry: keepRetry }
      setMsgs(list)
    } catch { /* keep the messages as they are */ } finally { setTranslating(false) }
  }
  useEffect(() => {
    api.get(`/api/chat/messages${projectId ? `?project_id=${projectId}` : ''}`).then((m: Json[]) => {
      setMsgs(m.map(toMsg))
      if (m.some((x) => x.lang !== getLang())) syncLanguage()
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])
  useEffect(() => {
    const h = () => { setLang(getLang() === 'es' ? 'es-MX' : 'en-US'); syncLanguage() }
    window.addEventListener('tm:lang', h)
    return () => window.removeEventListener('tm:lang', h)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])
  useEffect(() => { bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: 'smooth' }) }, [msgs, live, busy])

  const send = async (text?: string, mult = 1, isRetry = false) => {
    const message = (text ?? input).trim()
    if (!message || busy) return
    setInput('')
    if (!isRetry) setMsgs((m) => [...m, { role: 'user', content: message }])
    setBusy(true)
    setLive([])
    let finished = false
    try {
      await streamChat({ message, project_id: projectId, limit_multiplier: mult }, (ev) => {
        if (ev.type === 'final') {
          setMsgs((m) => [...m, { role: 'assistant', content: ev.data.answer, extra: { ...ev.data, retry: message } }])
          notifyProjectChanged(ev.data.project_id ?? projectId)
          finished = true
        } else if (ev.type === 'error') {
          setMsgs((m) => [...m, { role: 'assistant', content: `⚠️ ${ev.data.message}` }])
        } else {
          setLive((l) => [...l, ev])
          if (ev.type === 'tool_end') notifyProjectChanged(projectId)
        }
      })
    } catch (e) {
      const raw = (e as Error).message || ''
      const offline = raw.includes('Failed to fetch') || raw.includes('NetworkError') || raw.includes('502') || raw.includes('network')
      setMsgs((m) => [...m, {
        role: 'assistant',
        content: offline
          ? '⚠️ I lost the connection to the TerraMind server before I could answer. Make sure the server is still running (`python run.py`), then press **Retry**.'
          : `⚠️ ${raw}`,
        extra: offline ? { retry_failed: message } : undefined,
      }])
    } finally {
      setBusy(false)
      setLive([])
    }
    if (finished) syncLanguage(message, true)  // quiet: usually nothing to translate after a turn
  }

  const toggleMic = () => {
    setMicError(null)
    if (!SR) { setMicError('Voice input is not supported in this browser. Use Chrome or Edge, or type your instruction.'); return }
    if (listening) { recRef.current?.stop(); return }
    const rec = new SR()
    rec.lang = lang
    rec.interimResults = true
    rec.continuous = false
    const base = input ? input.trimEnd() + ' ' : ''
    rec.onresult = (e: Json) => {
      let t = ''
      for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript
      setInput(base + t)
    }
    rec.onerror = (e: Json) => {
      setMicError(e.error === 'not-allowed' || e.error === 'service-not-allowed'
        ? 'Microphone permission was denied. Allow microphone access in the browser address bar and try again.'
        : e.error === 'no-speech' ? 'No speech detected. Try again.' : `Voice input error: ${e.error}`)
    }
    rec.onend = () => setListening(false)
    recRef.current = rec
    try { rec.start(); setListening(true) } catch (err) { setMicError(String(err)) }
  }

  const attach = async (files: FileList | null) => {
    const f = files?.[0]
    if (!f) return
    setMicError(null)
    if (!projectId) { setMicError('Open a project first, then attach files to it (permits, contracts, Excel models…).'); return }
    setUploading(f.name)
    try {
      const r = await uploadDocument(projectId, f, true)
      setUploading(null)
      const note = input.trim() ? ` ${input.trim()}` : ' What does it say, and what should we update or watch out for?'
      setInput('')
      await send(`I uploaded "${r.document.filename}" (document #${r.document.id}).${note}`)
    } catch (e) {
      setUploading(null)
      setMicError(`Upload failed: ${(e as Error).message}`)
    }
  }

  const last = msgs[msgs.length - 1]
  return (
    <aside className="chat">
      <div className="chat-head">
        <div className="brand-mark" style={{ width: 28, height: 28 }}><Bot size={15} color="#fff" /></div>
        <div className="grow">
          <div style={{ fontWeight: 620, fontSize: 14 }}>Investment Manager</div>
          <div className="tiny muted">{projectId ? `Connected to project #${projectId} · tools + engine` : 'Portfolio context · can create projects'}</div>
        </div>
        <button className="btn ghost sm" onClick={onClose} title="Close"><X size={15} /></button>
      </div>
      <div className="chat-body" ref={bodyRef}>
        {msgs.length === 0 && (
          <div className="col" style={{ gap: 10 }}>
            <div className="msg assistant">
              <p>{t("I manage your project data through the platform's tools. Tell me about a deal or ask for a change — I update the fields, recalculate the deterministic model and show what changed.")}</p>
              <p className="small muted">{t('Material changes (financing, legal limits, approvals) wait for your confirmation click.')}</p>
            </div>
          </div>
        )}
        {translating && msgs.length > 0 && <div className="toolchip" style={{ alignSelf: 'center' }}><Languages size={13} /> Translating the conversation…</div>}
        {msgs.map((m, i) => <Message key={i} m={m} onRetry={(t, mult = 2) => send(t, mult, true)} isLast={i === msgs.length - 1} />)}
        {busy && (
          <div className="col" style={{ gap: 6 }}>
            {live.filter((e) => ['tool_start', 'tool_end', 'specialist_start', 'specialist_done'].includes(e.type)).slice(-6).map((e, i) => (
              <div key={i} className="toolchip">
                {e.type.endsWith('start') ? <Loader2 size={13} className="spin" style={{ animation: 'spin 1s linear infinite' }} /> : <Check size={13} color="var(--good)" />}
                <span>{e.type === 'tool_start' ? `Running ${e.data.tool}` : e.type === 'tool_end' ? `${e.data.tool}: ${e.data.summary}`
                  : e.type === 'specialist_start' ? `${e.data.agent} agent researching…` : `${e.data.agent} done${e.data.from_cache ? ' (cache)' : ''}`}</span>
              </div>
            ))}
            <div className="msg assistant typing" aria-label="AI is working"><span /><span /><span /></div>
          </div>
        )}
      </div>
      <div className="chat-foot">
        {!busy && (msgs.length === 0 || last?.role === 'assistant') && (
          <div className="suggest" style={{ marginBottom: 8 }}>
            {(projectId ? SUGGESTIONS_PROJECT : SUGGESTIONS_HOME).slice(0, 4).map((s) => (
              <button key={s} onClick={() => setInput(s)} title="Put in the input box">{s.length > 60 ? s.slice(0, 58) + '…' : s}</button>
            ))}
          </div>
        )}
        {aiOff && <div className="callout warn small" style={{ marginBottom: 8 }}>AI is off: add PORTKEY_API_KEY to a .env file (repo folder or the folder above).</div>}
        {micError && <div className="callout warn small" style={{ marginBottom: 8 }}><MicOff size={14} /> {micError}</div>}
        {uploading && <div className="callout info small" style={{ marginBottom: 8 }}><span className="spinner" /> Reading and analyzing <b>{uploading}</b>…</div>}
        {listening && <div className="callout info small" style={{ marginBottom: 8 }}><Mic size={14} /> Listening ({lang === 'es-MX' ? 'Español' : 'English'})… speak, then review the text and press Send.</div>}
        <div className="chat-input">
          <textarea rows={1} value={input} placeholder={listening ? 'Listening…' : 'Ask or instruct… (Enter to send)'} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
          <button className="icon-btn" onClick={() => fileRef.current?.click()} disabled={busy || !!uploading}
            title={projectId ? 'Attach a file (permit, certificate, contract, Excel model, photo)' : 'Open a project to attach files'}><Paperclip size={16} /></button>
          <input ref={fileRef} type="file" hidden accept=".pdf,.xlsx,.xlsm,.docx,.csv,.txt,.md,.png,.jpg,.jpeg,.webp" onChange={(e) => { attach(e.target.files); e.target.value = '' }} />
          <button className={`icon-btn ${listening ? 'rec' : ''}`} onClick={toggleMic} title={listening ? 'Stop dictation' : 'Dictate (speech-to-text)'} aria-pressed={listening}>
            {listening ? <MicOff size={16} /> : <Mic size={16} />}
          </button>
          <button className="icon-btn send" onClick={() => send()} disabled={busy || !input.trim()} title="Send"><Send size={15} /></button>
        </div>
        <div className="row between tiny muted" style={{ marginTop: 6 }}>
          <span>Voice: <button className="btn ghost sm" style={{ height: 20, padding: '0 4px' }} onClick={() => setLang(lang === 'en-US' ? 'es-MX' : 'en-US')}>{lang === 'en-US' ? 'English' : 'Español'}</button> · audio is never stored</span>
          <span>{health?.ai?.model}</span>
        </div>
      </div>
    </aside>
  )
}

/** "Translated · show original" toggle under a message whose stored text was in the other language. */
function useOriginal(m: Msg) {
  const [showOrig, setShowOrig] = useState(false)
  const text = showOrig && m.original ? m.original : m.content
  const toggle = m.original ? (
    <button className="tiny muted" style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', textAlign: 'inherit' }} onClick={() => setShowOrig((s) => !s)}>
      <Languages size={11} /> {showOrig ? 'Original · show translation' : 'Translated · show original'}
    </button>
  ) : null
  return { text, toggle }
}

function Message({ m, onRetry, isLast }: { m: Msg; onRetry: (t: string, mult?: number) => void; isLast: boolean }) {
  const { text, toggle } = useOriginal(m)
  if (m.role === 'user') return <div className="col" style={{ gap: 2, alignSelf: 'flex-end', alignItems: 'flex-end', maxWidth: '88%' }}><div className="msg user" style={{ maxWidth: '100%' }}>{text}</div>{toggle}</div>
  const x = m.extra || {}
  return (
    <div className="col" style={{ gap: 6, alignSelf: 'flex-start', maxWidth: '96%' }}>
      {x.tool_log?.length > 0 && (
        <details className="toolchip" style={{ display: 'block' }}>
          <summary style={{ cursor: 'pointer' }}><Wrench size={12} /> {x.tool_log.length} tool call{x.tool_log.length > 1 ? 's' : ''}
            {x.usage?.total && <span className="muted"> · {(x.usage.total.input_tokens + x.usage.total.output_tokens).toLocaleString()} tokens · ${x.usage.total.cost_usd.toFixed(4)}</span>}
          </summary>
          {x.tool_log.map((t: Json, i: number) => <div key={i} className="tiny" style={{ marginTop: 3 }}>• <b>{t.tool}</b>: {t.summary}</div>)}
        </details>
      )}
      <div className="msg assistant" dangerouslySetInnerHTML={md(text)} />
      {toggle}
      {x.changes?.length > 0 && (
        <div className="callout good small" style={{ padding: '6px 10px' }}>
          <div><b>Updated:</b> {x.changes.map((c: Json) => `${c.label}: ${short(c.old)} → ${short(c.new)}`).join(' · ')}</div>
        </div>
      )}
      {x.pending_ids?.map((id: number) => <PendingCard key={id} id={id} projectId={x.project_id} />)}
      {x.limit_hit && isLast && (
        <div className="callout warn small">
          <div><b>Limit reached:</b> {x.limit_hit.detail}<br />
            <button className="btn sm" style={{ marginTop: 6 }} onClick={() => onRetry(x.retry)}>Continue with higher limits (2×)</button></div>
        </div>
      )}
      {x.retry_failed && isLast && (
        <button className="btn sm" style={{ alignSelf: 'flex-start' }} onClick={() => onRetry(x.retry_failed, 1)}>Retry</button>
      )}
      {x.links?.length > 0 && x.project_id && (
        <div className="row wrap" style={{ gap: 6 }}>
          {x.links.includes('excel') && <a className="badge good" href={`/api/projects/${x.project_id}/export.xlsx`}>Download Excel model ↓</a>}
          {x.links.filter((l: string) => PAGE_LABEL[l] || l.startsWith('project:')).map((l: string) => (
            <Link key={l} className="badge" to={l.startsWith('project:') ? `/p/${l.split(':')[1]}/property` : `/p/${x.project_id}/${l}`}>
              Open {l.startsWith('project:') ? 'new project' : PAGE_LABEL[l]} →
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

function short(v: Json) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v.toLocaleString('en-US', { maximumFractionDigits: 2 })
  if (Array.isArray(v)) return `${v.length} items`
  return String(v)
}

function PendingCard({ id, projectId }: { id: number; projectId: number | null }) {
  const [state, setState] = useState<'pending' | 'confirmed' | 'rejected' | 'loading'>('loading')
  const [item, setItem] = useState<Json>(null)
  useEffect(() => {
    if (!projectId) return
    api.get(`/api/projects/${projectId}/pending`).then((rows: Json[]) => {
      const r = rows.find((x) => x.id === id)
      if (r) { setItem(r); setState('pending') } else setState('confirmed')
    })
  }, [id, projectId])
  const act = async (a: 'confirm' | 'reject') => {
    await api.post(`/api/pending/${id}/${a}`)
    setState(a === 'confirm' ? 'confirmed' : 'rejected')
    notifyProjectChanged(projectId)
  }
  if (state === 'loading') return null
  if (state !== 'pending') return <div className="tiny muted"><ShieldCheck size={12} /> Material change #{id} {state === 'rejected' ? 'rejected' : 'resolved'}.</div>
  return (
    <div className="callout warn small" style={{ display: 'block' }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}><ShieldCheck size={13} /> Confirmation required (material change)</div>
      {item.kind === 'status' ? <div>Change project status → <b>{item.changes.status}</b></div> :
        item.changes.map((c: Json) => <div key={c.key}>{c.label}: <b>{short(c.old)}</b> → <b>{short(c.new)}</b>{c.regulatory_override && <span className="badge bad" style={{ marginLeft: 6 }}>legal override</span>}</div>)}
      <div className="row" style={{ marginTop: 8, gap: 6 }}>
        <button className="btn sm primary" onClick={() => act('confirm')}>Confirm</button>
        <button className="btn sm" onClick={() => act('reject')}>Reject</button>
      </div>
    </div>
  )
}

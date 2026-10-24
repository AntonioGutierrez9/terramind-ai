// Thin typed client for the FastAPI backend. All numbers shown in the UI come from these endpoints.
/* eslint-disable @typescript-eslint/no-explicit-any */

export type Json = any

import { getLang } from './i18n'
const langHeader = () => ({ 'X-Lang': getLang() })

async function req<T = Json>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json', ...langHeader() } : langHeader(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const text = await r.text()
  const data = text ? JSON.parse(text) : null
  if (r.status === 401 && !url.startsWith('/api/auth/')) window.dispatchEvent(new Event('tm:auth-required'))
  if (!r.ok) throw new Error((data && (data.detail || data.message)) || `${r.status} ${r.statusText}`)
  return data as T
}

export const api = {
  get: <T = Json>(url: string) => req<T>('GET', url),
  post: <T = Json>(url: string, body: unknown = {}) => req<T>('POST', url, body),
  put: <T = Json>(url: string, body: unknown) => req<T>('PUT', url, body),
  patch: <T = Json>(url: string, body: unknown) => req<T>('PATCH', url, body),
  del: <T = Json>(url: string) => req<T>('DELETE', url),
}

export interface Change { key: string; value?: unknown; op?: 'set' | 'pct' | 'add' }

/** Apply user edits through the same validated write path the chatbot uses. */
export async function applyChanges(pid: number, changes: Change[], opts: { confirm_override?: boolean; reason?: string } = {}) {
  const res = await api.post(`/api/projects/${pid}/changes`, { changes, ...opts })
  notifyProjectChanged(pid)
  return res
}

// ---- cross-component refresh: pages listen for this event (fired by forms AND by the chatbot) ----
export function notifyProjectChanged(pid: number | null) {
  window.dispatchEvent(new CustomEvent('tm:project-changed', { detail: { pid } }))
}
export function onProjectChanged(fn: (pid: number | null) => void) {
  const h = (e: Event) => fn((e as CustomEvent).detail?.pid ?? null)
  window.addEventListener('tm:project-changed', h)
  return () => window.removeEventListener('tm:project-changed', h)
}

/** Upload a file to a project (multipart); the backend extracts text and runs the Document agent. */
export async function uploadDocument(pid: number, file: File, analyze = true) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('analyze', analyze ? 'true' : 'false')
  const r = await fetch(`/api/projects/${pid}/documents`, { method: 'POST', body: fd, headers: langHeader() })
  const text = await r.text()
  const data = text ? JSON.parse(text) : null
  if (!r.ok) throw new Error((data && data.detail) || `${r.status} ${r.statusText}`)
  notifyProjectChanged(pid)
  return data
}

/** Stream a chat turn (Server-Sent Events over POST). */
export async function streamChat(
  body: { message: string; project_id: number | null; limit_multiplier?: number },
  onEvent: (ev: { type: string; data: Json }) => void,
  signal?: AbortSignal,
) {
  const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', ...langHeader() }, body: JSON.stringify(body), signal })
  if (!r.ok || !r.body) {
    const t = await r.text()
    let msg = t
    try { msg = JSON.parse(t).detail } catch { /* keep text */ }
    throw new Error(msg || `HTTP ${r.status}`)
  }
  const reader = r.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i)
      buf = buf.slice(i + 2)
      const line = chunk.split('\n').find((l) => l.startsWith('data: '))
      if (line) onEvent(JSON.parse(line.slice(6)))
    }
  }
}

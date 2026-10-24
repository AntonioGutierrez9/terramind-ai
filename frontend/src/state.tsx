/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, onProjectChanged, type Json } from './api'

export interface RegistrySpec {
  label: string; section: string; unit: string; kind: 'number' | 'int' | 'choice' | 'bool' | 'text'
  min: number | null; max: number | null; typical: [number, number] | null; material: boolean; regulatory: boolean
  required: string[]; suggested: unknown; choices: string[] | null; help: string
}
export interface Meta {
  registry: Record<string, RegistrySpec>
  sections: Record<string, string>
  profile_choices: Record<string, string[]>
  hard_cost_split: Record<string, number>
}

export interface ProjectData {
  project: { id: number; name: string; profile: Json; assumptions: Json; meta: Json; status: string; in_portfolio: boolean; updated_at: string }
  results: Json
  pending: Json[]
  mode: 'sale' | 'rent'
}

const MetaCtx = createContext<Meta | null>(null)
const HealthCtx = createContext<Json>(null)

export function AppProviders({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [health, setHealth] = useState<Json>(null)
  useEffect(() => {
    api.get<Meta>('/api/meta').then(setMeta)
    api.get('/api/health').then(setHealth).catch(() => setHealth({ ai_available: false }))
  }, [])
  if (!meta) return <div className="empty"><span className="spinner" /> Loading TerraMind…</div>
  return (
    <MetaCtx.Provider value={meta}>
      <HealthCtx.Provider value={health}>{children}</HealthCtx.Provider>
    </MetaCtx.Provider>
  )
}

export function useMeta(): Meta {
  const m = useContext(MetaCtx)
  if (!m) throw new Error('meta not loaded')
  return m
}
export function useHealth() {
  return useContext(HealthCtx)
}

/** Load a project (+ engine results) and refetch whenever any form or the chatbot changes it. */
export function useProjectData(pid: number | null) {
  const [data, setData] = useState<ProjectData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const reload = useCallback(() => {
    if (pid == null) return
    api.get<ProjectData>(`/api/projects/${pid}`).then((d) => { setData(d); setError(null) }).catch((e) => setError(String(e.message || e)))
  }, [pid])
  useEffect(() => { setData(null); reload() }, [reload])
  useEffect(() => onProjectChanged((changed) => { if (changed == null || changed === pid) reload() }), [pid, reload])
  return { data, error, reload }
}

/** Generic fetch hook that refetches on project changes. */
export function useFetch<T = Json>(url: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const load = useCallback(() => {
    if (!url) return
    setLoading(true)
    api.get<T>(url).then((d) => { setData(d); setError(null) }).catch((e) => setError(String(e.message || e))).finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, ...deps])
  useEffect(() => { load() }, [load])
  useEffect(() => onProjectChanged(() => load()), [load])
  return { data, error, loading, reload: load, setData }
}

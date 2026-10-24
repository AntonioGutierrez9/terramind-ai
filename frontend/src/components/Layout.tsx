/* eslint-disable react-refresh/only-export-components */
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useMatch, useNavigate, useOutletContext, useParams } from 'react-router-dom'
import {
  Banknote, BarChart3, Bot, Building2, ClipboardCheck, Coins, Gauge, History, Landmark, LayoutDashboard, Leaf, ListChecks,
  MapPinned, PanelRightClose, PanelRightOpen, Plus, Ruler, Undo2,
} from 'lucide-react'
import { api, notifyProjectChanged, type Json } from '../api'
import { useHealth, useProjectData, type ProjectData } from '../state'
import ChatPanel from './ChatPanel'
import { StatusBadge } from './ui'

export const PROJECT_PAGES = [
  { path: 'property', label: 'Property & Zoning', icon: MapPinned, step: 1 },
  { path: 'design', label: 'Development Config', icon: Ruler, step: 2 },
  { path: 'market', label: 'Market & Revenue', icon: BarChart3, step: 3 },
  { path: 'budget', label: 'Budget & Schedule', icon: Building2, step: 4 },
  { path: 'financing', label: 'Financing', icon: Landmark, step: 5 },
  { path: 'model', label: 'Financial Model', icon: Gauge, step: 6 },
  { path: 'sustainability', label: 'Sustainability', icon: Leaf, step: 7 },
  { path: 'committee', label: 'Investment Committee', icon: ClipboardCheck, step: 8 },
  { path: 'asset', label: 'Asset Management', icon: Coins, step: 9 },
  { path: 'assumptions', label: 'Assumption Center', icon: ListChecks },
  { path: 'history', label: 'Audit Trail', icon: History },
]

export function useProject() {
  return useOutletContext<{ data: ProjectData; reload: () => void }>()
}

export default function Layout() {
  const [chatOpen, setChatOpen] = useState(() => localStorage.getItem('tm-chat') !== 'closed')
  const [projects, setProjects] = useState<Json[]>([])
  const match = useMatch('/p/:pid/*')
  const pid = match?.params.pid ? Number(match.params.pid) : null
  const loc = useLocation()
  const nav = useNavigate()
  const health = useHealth()
  useEffect(() => { localStorage.setItem('tm-chat', chatOpen ? 'open' : 'closed') }, [chatOpen])
  useEffect(() => { api.get('/api/projects').then(setProjects) }, [loc.pathname])
  const current = projects.find((p) => p.id === pid)

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Leaf size={17} color="#fff" /></div>
          <div><div className="brand-name">TerraMind AI</div><div className="brand-sub">Real estate investment</div></div>
        </div>
        <div className="nav-section">Fund</div>
        <NavLink to="/" end className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><LayoutDashboard size={16} />Portfolio</NavLink>
        <NavLink to="/new" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><Plus size={16} />New Investment</NavLink>
        <NavLink to="/usage" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><Bot size={16} />AI Usage & Limits</NavLink>
        {pid && (
          <>
            <div className="nav-section" style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>Project</span>
            </div>
            <div style={{ padding: '0 18px 8px', color: '#fff', fontSize: 13, fontWeight: 600 }}>{current?.name ?? `#${pid}`}</div>
            {PROJECT_PAGES.map((pg) => (
              <NavLink key={pg.path} to={`/p/${pid}/${pg.path}`} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                <pg.icon size={16} />{pg.label}{pg.step && <span className="step">{pg.step}</span>}
              </NavLink>
            ))}
          </>
        )}
        <div className="sidebar-foot">
          <div>Model: {health?.ai?.model ?? '—'} {health?.ai_available ? '· AI on' : '· AI off'}</div>
          <div>Decision support only. Not investment advice.</div>
        </div>
      </aside>
      <div className="main">
        <div className="topbar">
          <select className="input" style={{ width: 290 }} value={pid ?? ''} onChange={(e) => e.target.value ? nav(`/p/${e.target.value}/model`) : nav('/')}>
            <option value="">All projects (portfolio)</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          {current && <ProjectBadges p={current} />}
          <div className="grow" />
          {pid && <UndoButton pid={pid} />}
          <button className="btn" onClick={() => setChatOpen((o) => !o)}>
            {chatOpen ? <PanelRightClose size={15} /> : <PanelRightOpen size={15} />} AI Assistant
          </button>
        </div>
        <div className="content">
          <Outlet />
        </div>
      </div>
      {chatOpen && <ChatPanel projectId={pid} onClose={() => setChatOpen(false)} />}
    </div>
  )
}

function ProjectBadges({ p }: { p: Json }) {
  return (
    <div className="row" style={{ gap: 6 }}>
      <span className="badge">{p.status}</span>
      {p.profile?.demo && <span className="badge demo">fictional demo</span>}
      {p.model_status === 'ok' ? <StatusBadge level="good">model complete</StatusBadge> : <StatusBadge level="amber">model incomplete</StatusBadge>}
    </div>
  )
}

function UndoButton({ pid }: { pid: number }) {
  const [msg, setMsg] = useState<string | null>(null)
  const undo = async () => {
    const r = await api.post(`/api/projects/${pid}/undo`)
    setMsg(r.undone?.length ? `Undid ${r.undone.map((u: Json) => u.label).join(', ')}` : 'Nothing to undo')
    notifyProjectChanged(pid)
    setTimeout(() => setMsg(null), 3500)
  }
  return (
    <div className="row" style={{ gap: 6 }}>
      {msg && <span className="small muted">{msg}</span>}
      <button className="btn" onClick={undo} title="Undo the last change (form or chatbot)"><Undo2 size={15} /> Undo</button>
    </div>
  )
}

/** Wraps project pages: loads data once, passes it via outlet context. */
export function ProjectLayout() {
  const { pid } = useParams()
  const { data, error, reload } = useProjectData(Number(pid))
  if (error) return <div className="callout bad">{error}</div>
  if (!data) return <div className="empty"><span className="spinner" /></div>
  return <Outlet context={{ data, reload }} />
}

export { Banknote }

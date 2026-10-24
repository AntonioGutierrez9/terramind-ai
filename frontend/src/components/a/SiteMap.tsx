import { useCallback, useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { MapPin, RefreshCw } from 'lucide-react'
import { api, notifyProjectChanged } from '../../api'

const CDMX = { lat: 19.4326, lon: -99.1332 }
const PRECISION: Record<string, string> = {
  address: 'located from the full address', street: 'located on the street (number not found)',
  neighborhood: 'approximate: colonia / alcaldía center', city: 'approximate: city center', manual: 'pin placed manually',
}

/**
 * Plain Leaflet (BSD-2) with OpenStreetMap tiles. The backend geocodes with fallbacks (address → street → colonia → city)
 * and saves the result to the project, so each project is looked up once. Click the map to place or correct the pin.
 */
export default function SiteMap({ lat, lon, query, height = 300, projectId, precision }: {
  lat?: number | null; lon?: number | null; query: string; height?: number; projectId?: number; precision?: string
}) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const [pos, setPos] = useState<{ lat: number; lon: number; precision?: string } | null>(lat != null && lon != null ? { lat, lon, precision } : null)
  const [status, setStatus] = useState<{ kind: 'loading' | 'notfound' | 'error'; msg: string } | null>(null)
  const [saving, setSaving] = useState(false)

  const locate = useCallback(() => {
    if (!query.trim() && projectId == null) { setStatus({ kind: 'notfound', msg: 'No address yet. Click the map to place the lot.' }); return }
    setStatus({ kind: 'loading', msg: 'Locating the address…' })
    const qs = new URLSearchParams({ q: query })
    if (projectId != null) qs.set('project_id', String(projectId))
    api.get(`/api/geocode?${qs}`).then((g) => {
      if (g.found) { setPos({ lat: g.lat, lon: g.lon, precision: g.precision }); setStatus(null); if (projectId != null) notifyProjectChanged(projectId) }
      else setStatus({ kind: 'notfound', msg: 'The address was not found on OpenStreetMap. Click the map to place the lot.' })
    }).catch((e) => {
      const offline = String(e.message || '').includes('Failed to fetch') || String(e.message || '').includes('502')
      setStatus({ kind: 'error', msg: offline ? 'Cannot reach the TerraMind server. Is it still running (python run.py)?' : e.message || 'Map service unavailable.' })
    })
  }, [query, projectId])

  useEffect(() => {
    if (lat != null && lon != null) { setPos({ lat, lon, precision }); setStatus(null); return }
    locate()
  }, [lat, lon, precision, locate])

  // map: show the pin, or the city so the user can click to place it
  const center = pos || (status && status.kind !== 'loading' ? CDMX : null)
  useEffect(() => {
    if (!el.current || !center) return
    if (!map.current) {
      map.current = L.map(el.current, { zoomControl: true, scrollWheelZoom: false }).setView([center.lat, center.lon], pos ? 16 : 11)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(map.current)
      layer.current = L.layerGroup().addTo(map.current)
    } else {
      map.current.setView([center.lat, center.lon], pos ? Math.max(map.current.getZoom(), 16) : 11)
    }
    layer.current?.clearLayers()
    if (pos) {
      L.circle([pos.lat, pos.lon], { radius: 60, color: '#2a78d6', weight: 1, fillOpacity: 0.08 }).addTo(layer.current!)
      L.circleMarker([pos.lat, pos.lon], { radius: 9, color: '#fff', weight: 2, fillColor: '#17345e', fillOpacity: 1 }).addTo(layer.current!)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pos, center?.lat, center?.lon])

  // click to place / correct the pin (saved to the project)
  useEffect(() => {
    const m = map.current
    if (!m || projectId == null) return
    const onClick = async (e: L.LeafletMouseEvent) => {
      const p = { lat: +e.latlng.lat.toFixed(6), lon: +e.latlng.lng.toFixed(6), precision: 'manual' }
      setPos(p); setStatus(null); setSaving(true)
      try { await api.patch(`/api/projects/${projectId}/profile`, { lat: p.lat, lon: p.lon, geo_precision: 'manual' }); notifyProjectChanged(projectId) }
      finally { setSaving(false) }
    }
    m.on('click', onClick)
    return () => { m.off('click', onClick) }
  }, [projectId, center?.lat, center?.lon])

  useEffect(() => () => { map.current?.remove(); map.current = null }, [])

  return (
    <div>
      {center
        ? <div ref={el} style={{ height, borderRadius: 8, border: '1px solid var(--border)', cursor: projectId != null ? 'crosshair' : undefined }} />
        : <div className="empty" style={{ height, display: 'grid', placeItems: 'center', background: 'var(--surface-2)', borderRadius: 8 }}><span><span className="spinner" /> {status?.msg}</span></div>}
      <div className="row between" style={{ marginTop: 6, gap: 8 }}>
        <div className="tiny muted">
          {pos ? <><MapPin size={11} /> {PRECISION[pos.precision || ''] || 'located'}{projectId != null ? ' · click the map to correct the pin' : ''}{saving ? ' · saving…' : ''}</>
            : status && status.kind !== 'loading' ? <span style={{ color: status.kind === 'error' ? 'var(--critical)' : undefined }}>{status.msg}</span> : null}
        </div>
        {(status?.kind === 'error' || status?.kind === 'notfound' || (pos && pos.precision !== 'manual' && pos.precision !== 'address')) && (
          <button className="btn sm ghost" onClick={locate}><RefreshCw size={12} /> Locate again</button>
        )}
      </div>
    </div>
  )
}

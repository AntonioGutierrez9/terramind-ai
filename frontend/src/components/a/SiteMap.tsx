import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { api } from '../../api'

// Plain Leaflet (BSD-2) with OpenStreetMap tiles. A circle marker avoids bundling marker image assets.
export default function SiteMap({ lat, lon, query, height = 300 }: { lat?: number | null; lon?: number | null; query: string; height?: number }) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const [pos, setPos] = useState<{ lat: number; lon: number; approx: boolean; label?: string } | null>(
    lat != null && lon != null ? { lat, lon, approx: false } : null,
  )
  const [status, setStatus] = useState<string | null>(null)

  useEffect(() => {
    if (lat != null && lon != null) { setPos({ lat, lon, approx: false }); return }
    if (!query.trim()) { setStatus('No address to locate.'); return }
    setStatus('Locating…')
    api.get(`/api/geocode?q=${encodeURIComponent(query)}`).then((g) => {
      if (g.found) { setPos({ lat: g.lat, lon: g.lon, approx: true, label: g.display_name }); setStatus(null) }
      else setStatus('Address not found by the geocoder.')
    }).catch(() => setStatus('Geocoder unavailable.'))
  }, [lat, lon, query])

  useEffect(() => {
    if (!el.current || !pos) return
    if (!map.current) {
      map.current = L.map(el.current, { zoomControl: true, scrollWheelZoom: false }).setView([pos.lat, pos.lon], 16)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(map.current)
    } else {
      map.current.setView([pos.lat, pos.lon], 16)
    }
    const m = L.circleMarker([pos.lat, pos.lon], { radius: 9, color: '#fff', weight: 2, fillColor: '#17345e', fillOpacity: 1 }).addTo(map.current)
    const c = L.circle([pos.lat, pos.lon], { radius: 60, color: '#2a78d6', weight: 1, fillOpacity: 0.08 }).addTo(map.current)
    return () => { m.remove(); c.remove() }
  }, [pos])

  useEffect(() => () => { map.current?.remove(); map.current = null }, [])

  return (
    <div>
      {pos ? <div ref={el} style={{ height, borderRadius: 8, border: '1px solid var(--border)' }} />
        : <div className="empty" style={{ height, display: 'grid', placeItems: 'center', background: 'var(--surface-2)', borderRadius: 8 }}>{status}</div>}
      {pos?.approx && <div className="tiny muted" style={{ marginTop: 4 }}>Location approximate (geocoded from the address{pos.label ? `: ${pos.label}` : ''}).</div>}
    </div>
  )
}

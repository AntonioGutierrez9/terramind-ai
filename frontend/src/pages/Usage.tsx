import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Save } from 'lucide-react'
import { Callout, Card, ChartTip, Kpi, Loading, PageHead } from '../components/ui'
import { shortDate } from '../components/c/helpers'
import { api, type Json } from '../api'
import { AXIS, GRID, SERIES, num } from '../format'
import { useFetch } from '../state'

const LIMIT_INFO: Record<string, { label: string; help: string; step: number }> = {
  max_specialist_calls: { label: 'Specialist research calls per chat turn', help: 'Web-research agents (zoning, market, cost, financing, sustainability) the Investment Manager may call in one turn. Cached results do not count.', step: 1 },
  max_tool_calls: { label: 'Tool calls per chat turn', help: 'Structured tool calls (read/update assumptions, what-if, solver…) per turn.', step: 1 },
  max_requests: { label: 'Model requests per chat turn', help: 'Round trips to the language model in one turn; prevents runaway agent loops.', step: 1 },
  max_tokens: { label: 'Tokens per turn', help: 'Input + output tokens across all agents in one turn.', step: 10000 },
  max_usd: { label: 'USD per turn', help: 'Measured spend across the manager and every specialist in one turn.', step: 0.01 },
}

const usd = (v: number | null | undefined, d = 4) => (v == null ? '—' : `$${v.toFixed(d)}`)

export default function Usage() {
  const { data: u, loading } = useFetch<Json>('/api/usage')
  if (loading && !u) return <Loading />
  const t = u?.total || {}
  const tokens = (t.input_tokens || 0) + (t.output_tokens || 0)
  const cacheRate = t.input_tokens ? (t.cached_tokens || 0) / t.input_tokens : null
  const byAgent: Json[] = u?.by_agent || []
  const runs: Json[] = u?.by_run || []

  return (
    <>
      <PageHead eyebrow="Tokenomics" title="AI usage & limits">
        Every model call is measured (input, cached input and output tokens, web searches) and priced. These are the real numbers used in the report. Limits stop a turn safely and ask for permission before spending more.
      </PageHead>
      <div className="col" style={{ gap: 16 }}>
        <div className="grid g5">
          <Kpi label="AI runs" value={num(t.runs || 0)} sub="chat turns, research, committee" />
          <Kpi label="Total tokens" value={num(tokens)} sub={`${num(t.input_tokens || 0)} in · ${num(t.output_tokens || 0)} out`} />
          <Kpi label="Cache hit rate" value={cacheRate == null ? '—' : `${(cacheRate * 100).toFixed(1)}%`} sub="cached ÷ input tokens" tone={cacheRate && cacheRate > 0.4 ? 'good' : undefined} />
          <Kpi label="Total cost" value={usd(t.cost_usd, 4)} sub={`${num(t.web_searches || 0)} web searches`} />
          <Kpi label="Average cost per run" value={t.runs ? usd((t.cost_usd || 0) / t.runs, 5) : '—'} />
        </div>
        <Callout>Pricing (gpt-6-luna via Portkey): $0.10 per 1M input tokens, $0.01 per 1M cached input tokens, $0.50 per 1M output tokens. Web search calls are added at a planning estimate per call. Financial calculations use no tokens — they run in the deterministic engine.</Callout>

        <div className="grid g2">
          <Card title="Usage by agent">
            {!byAgent.length ? <div className="small muted">No AI calls recorded yet.</div> : (
              <div className="table-wrap">
                <table className="t">
                  <thead><tr><th>Agent</th><th className="num">Calls</th><th className="num">Input</th><th className="num">Cached</th><th className="num">Output</th><th className="num">Searches</th><th className="num">Cost</th><th className="num">Avg s</th></tr></thead>
                  <tbody>{byAgent.map((a) => (
                    <tr key={a.agent}><td>{a.agent}</td><td className="num">{num(a.calls)}</td><td className="num">{num(a.input_tokens)}</td><td className="num">{num(a.cached_tokens)}</td>
                      <td className="num">{num(a.output_tokens)}</td><td className="num">{num(a.web_searches)}</td><td className="num">{usd(a.cost_usd)}</td><td className="num">{num(a.avg_seconds, 1)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </Card>
          <Card title="Cost by agent" sub="USD, all runs">
            {!byAgent.length ? <div className="small muted">No data yet.</div> : (
              <ResponsiveContainer width="100%" height={Math.max(160, byAgent.length * 34)}>
                <BarChart data={byAgent} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
                  <CartesianGrid stroke={GRID} horizontal={false} />
                  <XAxis type="number" stroke={AXIS} fontSize={11} tickFormatter={(v) => `$${v.toFixed(3)}`} />
                  <YAxis type="category" dataKey="agent" width={170} stroke={AXIS} fontSize={11} />
                  <Tooltip content={<ChartTip fmt={(v) => usd(v, 5)} />} cursor={{ fill: 'rgba(42,120,214,.06)' }} />
                  <Bar dataKey="cost_usd" name="Cost" fill={SERIES[0]} barSize={14} radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>
        </div>

        <div className="grid g2">
          <LimitsCard />
          <Projection runs={runs} />
        </div>

        <Card title="Recent runs" sub="One row per chat turn / research / committee run">
          {!runs.length ? <div className="small muted">No runs yet.</div> : (
            <div className="table-wrap" style={{ maxHeight: 420 }}>
              <table className="t">
                <thead><tr><th>Time</th><th>Purpose</th><th>Agents</th><th className="num">Requests</th><th className="num">Input</th><th className="num">Cached</th><th className="num">Output</th><th className="num">Searches</th><th className="num">Cost</th></tr></thead>
                <tbody>{runs.map((r) => (
                  <tr key={r.run_id}><td className="small">{shortDate(r.at)}</td><td><span className="badge">{r.purpose}</span></td><td className="small">{r.agents}</td>
                    <td className="num">{num(r.requests)}</td><td className="num">{num(r.input_tokens)}</td><td className="num">{num(r.cached_tokens)}</td><td className="num">{num(r.output_tokens)}</td>
                    <td className="num">{num(r.web_searches)}</td><td className="num">{usd(r.cost_usd, 5)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  )
}

function LimitsCard() {
  const [lim, setLim] = useState<Record<string, string> | null>(null)
  const [msg, setMsg] = useState<{ tone: 'good' | 'bad'; text: string } | null>(null)
  useEffect(() => { api.get('/api/settings/limits').then((l: Json) => setLim(Object.fromEntries(Object.entries(l).map(([k, v]) => [k, String(v)])))) }, [])
  const save = async () => {
    try {
      const body = Object.fromEntries(Object.entries(lim || {}).map(([k, v]) => [k, Number(v)]))
      const r = await api.put('/api/settings/limits', body)
      setLim(Object.fromEntries(Object.entries(r).map(([k, v]) => [k, String(v)])))
      setMsg({ tone: 'good', text: 'Limits saved.' })
    } catch (e) { setMsg({ tone: 'bad', text: (e as Error).message }) }
  }
  return (
    <Card title="Agent limits" sub="Applied to every chat turn and agent run" actions={<button className="btn primary sm" onClick={save}><Save size={13} /> Save</button>}>
      {!lim ? <Loading /> : (
        <div className="col" style={{ gap: 10 }}>
          {Object.keys(LIMIT_INFO).map((k) => (
            <div key={k} className="row" style={{ alignItems: 'flex-start' }}>
              <div className="grow"><div className="small" style={{ fontWeight: 600 }}>{LIMIT_INFO[k].label}</div><div className="tiny muted">{LIMIT_INFO[k].help}</div></div>
              <input className="input" type="number" step={LIMIT_INFO[k].step} style={{ width: 120 }} value={lim[k] ?? ''} onChange={(e) => setLim({ ...lim, [k]: e.target.value })} />
            </div>
          ))}
          <Callout>When a limit is reached the turn stops safely, keeps the changes already validated, and shows <b>Continue with higher limits</b> — nothing more is spent without your permission. Specialists cannot delegate, so circular delegation is impossible.</Callout>
          {msg && <Callout tone={msg.tone}>{msg.text}</Callout>}
        </div>
      )}
    </Card>
  )
}

function Projection({ runs }: { runs: Json[] }) {
  const avg = useMemo(() => {
    const groups: Record<string, number[]> = { chat: [], research: [], committee: [] }
    for (const r of runs) {
      const p = String(r.purpose || '')
      const g = p.startsWith('chat') ? 'chat' : p.startsWith('research') ? 'research' : p.startsWith('committee') ? 'committee' : null
      if (g) groups[g].push(r.cost_usd || 0)
    }
    return Object.fromEntries(Object.entries(groups).map(([k, v]) => [k, { n: v.length, avg: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null }]))
  }, [runs])
  const [per, setPer] = useState<Record<string, string>>({ chat: '40', research: '6', committee: '2' })
  const perUser = Object.keys(per).reduce((s, k) => s + (avg[k].avg ?? 0) * Number(per[k] || 0), 0)
  const missing = Object.keys(per).filter((k) => avg[k].avg == null && Number(per[k]) > 0)
  return (
    <Card title="Cost projection" sub="Measured average cost per run × assumed runs per user per month">
      <table className="t">
        <thead><tr><th>Run type</th><th className="num">Measured runs</th><th className="num">Avg cost / run</th><th className="num">Runs / user / month</th></tr></thead>
        <tbody>{Object.keys(per).map((k) => (
          <tr key={k}><td style={{ textTransform: 'capitalize' }}>{k}</td><td className="num">{avg[k].n}</td><td className="num">{usd(avg[k].avg, 5)}</td>
            <td className="num"><input className="input" style={{ width: 80, height: 26 }} value={per[k]} onChange={(e) => setPer({ ...per, [k]: e.target.value })} /></td></tr>
        ))}</tbody>
      </table>
      <div className="grid g3" style={{ marginTop: 12 }}>
        <Kpi label="Per user / month" value={usd(perUser, 3)} />
        <Kpi label="100 users / month" value={usd(perUser * 100, 2)} />
        <Kpi label="10,000 users / month" value={usd(perUser * 10000, 0)} />
      </div>
      {missing.length > 0 && <div style={{ marginTop: 10 }}><Callout tone="warn">No measured runs yet for: {missing.join(', ')} — they are counted as $0 until measured.</Callout></div>}
    </Card>
  )
}

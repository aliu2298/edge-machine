import { useState } from 'react'
import { CheckCircle2, Sparkles, Brain, Download, RotateCw, Target, Globe } from 'lucide-react'
import { useApi, postJSON } from '@/lib/api'
import type { Stats, Prediction } from '@/lib/api'
import { usd } from '@/lib/utils'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { BadgeProps } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { StatTile, SectionTitle, Empty } from '@/components/bits'

function statusBadge(s: string) {
  const map: Record<string, { v: BadgeProps['variant']; t: string }> = {
    win: { v: 'yes', t: 'Win' },
    half_win: { v: 'yes', t: '½ Win' },
    loss: { v: 'no', t: 'Loss' },
    half_loss: { v: 'no', t: '½ Loss' },
    pending: { v: 'warn', t: 'Pending' },
    void: { v: 'default', t: 'Void' },
  }
  const m = map[s] ?? { v: 'default' as const, t: s }
  return <Badge variant={m.v}>{m.t}</Badge>
}

const tagVariant = (t: string): BadgeProps['variant'] => {
  const k = t.toLowerCase()
  if (k.includes('siege') || k === 'best') return 'yes'
  if (k.includes('coin') || k.includes('lean')) return 'warn'
  if (k.includes('cap') || k === 'value') return 'default'
  return 'outline'
}

// Human label for the bet market — shown small above each leg's pick.
const marketLabel = (m: string): string =>
  ({
    corner_1x2: 'Corner 1X2',
    team_corners: 'Team corners',
    total_corners: 'Total corners',
    corners: 'Match corners',
    team_total: 'Team total',
    first_goal: 'First goal',
    handicap: 'Handicap',
    total: 'Total goals',
    '1x2': 'Match result',
    win: 'Match result',
    btts: 'Both teams score',
    draw: 'Draw',
  }[m] ?? m.replace(/_/g, ' '))

const scoreInput =
  'h-8 w-14 rounded-md border border-input bg-card px-2 text-center text-sm tnum focus:outline-none focus:ring-2 focus:ring-ring'

function teams(match: string): [string, string] {
  const m = match.split(/\s+(?:v|vs|@)\.?\s+/i)
  return [m[0]?.trim() || 'Home', m[1]?.trim() || 'Away']
}
const short = (name: string) => name.replace(/\b(FC|CF|United|City)\b/gi, '').trim().slice(0, 12)

type ScoreGrid = { home: string; away: string; picked: string; pred: string; buckets: Record<string, number | null> }

// Correct Score Group grid — 6 buckets (fav/dog win low, win by 3, draw, any other) with derived odds.
function ScoreGroupGrid({ raw }: { raw: string | null }) {
  let g: ScoreGrid | null = null
  try { g = raw ? (JSON.parse(raw) as ScoreGrid) : null } catch { g = null }
  if (!g) return <div className="py-3 text-center text-[11px] text-muted-foreground">No score-group market yet</div>
  const b = g.buckets || {}
  const cells = [
    { k: 'home_low', label: `${short(g.home)} 1-0·2-0·2-1` },
    { k: 'away_low', label: `${short(g.away)} 1-0·2-0·2-1` },
    { k: 'home_big', label: `${short(g.home)} 3-0·3-1·3-2` },
    { k: 'away_big', label: `${short(g.away)} 3-0·3-1·3-2` },
    { k: 'draw', label: 'Draw 1-1·2-2·3-3' },
    { k: 'other', label: 'Any other' },
  ]
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {cells.map((c) => {
        const picked = c.k === g!.picked
        const odd = b[c.k]
        return (
          <div
            key={c.k}
            className={`flex items-center justify-between gap-1 rounded-md border px-2 py-1.5 ${picked ? 'border-yes bg-yes-soft' : 'border-border bg-card/40'}`}
          >
            <span className={`text-[9px] leading-tight ${picked ? 'font-semibold text-foreground' : 'text-muted-foreground'}`}>{c.label}</span>
            <span className={`tnum text-[12px] font-bold ${picked ? 'text-yes' : ''}`}>{odd != null ? odd.toFixed(2) : '—'}</span>
          </div>
        )
      })}
    </div>
  )
}

// A card now represents a GAME and shows every leg (the pre-game pair) on one face.
function GameCard({
  legs,
  flipped,
  onFlip,
  onSettle,
}: {
  legs: Prediction[]
  flipped: boolean
  onFlip: () => void
  onSettle: () => void
}) {
  const g = legs[0] // game-level fields (match, archetypes, predictions) are shared across legs
  const settledLeg = legs.find((l) => l.home_score != null) ?? g
  const [home, away] = teams(g.match)
  const settled = settledLeg.home_score != null && settledLeg.away_score != null
  const exact = settled && g.pred_score === `${settledLeg.home_score}-${settledLeg.away_score}`
  const anyPending = legs.some((l) => l.status === 'pending')

  return (
    <div className="h-[244px] [perspective:1200px]">
      <div
        role="button"
        tabIndex={0}
        onClick={onFlip}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onFlip())}
        className={`relative h-full w-full cursor-pointer rounded-xl transition-transform duration-500 [transform-style:preserve-3d] ${
          flipped ? '[transform:rotateY(180deg)]' : ''
        }`}
      >
        {/* ---------- FRONT ---------- */}
        <Card className="absolute inset-0 flex flex-col p-4 [backface-visibility:hidden]">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{g.event_date}</span>
            {legs.length > 1 && <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{legs.length}-leg pair</span>}
          </div>

          <div className="mt-1 truncate text-sm font-semibold leading-tight">{g.match}</div>

          <div className="mt-2 flex min-h-0 flex-1 flex-col justify-start gap-2 overflow-hidden">
            {legs.map((leg) => {
              const pnlTone = leg.profit > 0 ? 'text-yes' : leg.profit < 0 ? 'text-no' : 'text-muted-foreground'
              return (
                <div key={leg.id} className="rounded-lg border bg-card/40 p-2.5">
                  <div className="flex items-center justify-between gap-1.5">
                    <span className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">{marketLabel(leg.market)}</span>
                    {leg.tag && <Badge variant={tagVariant(leg.tag)}>{leg.tag}</Badge>}
                  </div>
                  <div className="mt-1 line-clamp-2 text-[13px] font-bold leading-snug">{leg.pick}</div>
                  <div className="mt-1.5 flex items-center justify-between border-t pt-1.5 text-[11px]">
                    <span className="text-muted-foreground">
                      <span className="tnum font-bold text-foreground">{leg.odds ? leg.odds.toFixed(2) : '—'}</span>
                      <span className="px-1.5 opacity-50">·</span>
                      <span className="tnum">{leg.stake ? usd(leg.stake) : '—'}</span>
                    </span>
                    {leg.status === 'pending' ? statusBadge('pending') : <span className={`tnum font-bold ${pnlTone}`}>{usd(leg.profit, true)}</span>}
                  </div>
                </div>
              )
            })}
          </div>

          {anyPending && (
            <div className="mt-2 flex justify-end border-t pt-2">
              <Button
                size="sm"
                variant="outline"
                onClick={(e) => {
                  e.stopPropagation()
                  onSettle()
                }}
              >
                Settle
              </Button>
            </div>
          )}

          <RotateCw className="pointer-events-none absolute bottom-2 right-2 h-3.5 w-3.5 text-muted-foreground/50" />
        </Card>

        {/* ---------- BACK ---------- */}
        <Card className="absolute inset-0 flex flex-col bg-secondary/30 p-4 [backface-visibility:hidden] [transform:rotateY(180deg)]">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Prediction</span>
            <span className="truncate text-[10px] text-muted-foreground">{short(home)} v {short(away)}</span>
          </div>

          <div className="mt-2 flex items-center justify-between text-[10px] uppercase tracking-wide text-muted-foreground">
            <span className="flex items-center gap-1"><Target className="h-3 w-3" /> Score group</span>
            <span className="tnum normal-case">
              pred <span className="font-bold text-foreground">{g.pred_score || '—'}</span>
              {settled && <span className="text-amber-400"> · act {settledLeg.home_score}-{settledLeg.away_score}</span>}
              {exact && <span className="text-yes"> ✓</span>}
            </span>
          </div>
          <div className="mt-2 flex-1">
            <ScoreGroupGrid raw={g.grid_json} />
          </div>

          <RotateCw className="pointer-events-none absolute bottom-2 right-2 h-3.5 w-3.5 text-muted-foreground/50" />
        </Card>
      </div>
    </div>
  )
}

export function PicksView() {
  const [key, setKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [flipped, setFlipped] = useState<Set<string>>(new Set())
  const [openKey, setOpenKey] = useState<string | null>(null)
  const [hs, setHs] = useState('')
  const [as_, setAs] = useState('')
  const { data: stats } = useApi<Stats>('/api/stats', key)
  const { data: preds } = useApi<Prediction[]>('/api/predictions', key)
  const rows = (preds ?? []).filter((r) => !r.archived).slice().reverse()

  // Group legs into one card per game (date + match).
  const gameKey = (r: Prediction) => `${r.event_date}||${r.match}`
  const games = new Map<string, Prediction[]>()
  rows.forEach((r) => {
    const k = gameKey(r)
    if (!games.has(k)) games.set(k, [])
    games.get(k)!.push(r)
  })
  const byDate: Record<string, [string, Prediction[]][]> = {}
  for (const [k, legs] of games) {
    ;(byDate[legs[0].event_date] ||= []).push([k, legs])
  }

  const toggleFlip = (k: string) =>
    setFlipped((s) => {
      const n = new Set(s)
      n.has(k) ? n.delete(k) : n.add(k)
      return n
    })

  const settle = async () => {
    setBusy(true)
    try {
      const r = await postJSON<{ settled?: unknown[] }>('/api/settle-all-af')
      const n = Array.isArray(r.settled) ? r.settled.length : 0
      alert(n ? `✅ Settled ${n} pick(s).` : 'No pending picks were ready. Use “Settle” on a card to enter the score manually.')
    } catch {
      alert('Settle failed.')
    }
    setBusy(false)
    setKey((k) => k + 1)
  }
  const queue = (action: string, note: string, msg: string) =>
    postJSON('/api/request', { action, note }).then(() => alert(msg + '\n\n📥 Queued for Claude.'))

  // Re-export the public picks board and push it to Netlify — settled games drop
  // off and the next pending pick takes the open slot.
  const publish = async () => {
    setBusy(true)
    try {
      const r = await postJSON<{ deployed?: boolean; url?: string; note?: string; error?: string }>('/api/publish-site')
      if (r.deployed) alert(`🌐 Published → ${r.url}`)
      else alert(r.note || r.error || 'Exported; deploy skipped.')
    } catch {
      alert('Publish failed.')
    }
    setBusy(false)
  }

  // Settle every pending leg of the game with the entered score.
  const settleScore = async (legs: Prediction[]) => {
    if (hs === '' || as_ === '') return alert('Enter both scores.')
    const pending = legs.filter((l) => l.status === 'pending')
    let err = ''
    for (const l of pending) {
      try {
        const r = await postJSON<{ error?: string }>(`/api/predictions/${l.id}/settle-with-score`, {
          home_score: Number(hs),
          away_score: Number(as_),
        })
        if (r.error) err = r.error
      } catch {
        err = 'Settle failed.'
      }
    }
    if (err) alert(err)
    setOpenKey(null)
    setHs('')
    setAs('')
    setKey((k) => k + 1)
  }

  const settleGame = openKey != null ? games.get(openKey) : null

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        <Button onClick={settle} disabled={busy}>
          <CheckCircle2 /> {busy ? 'Settling…' : 'Settle results'}
        </Button>
        <Button onClick={publish} disabled={busy}>
          <Globe /> Publish site
        </Button>
        <Button variant="outline" onClick={() => queue('predict', "Generate the next day's picks", '🔮 Predict')}>
          <Sparkles /> Predict
        </Button>
        <Button variant="outline" onClick={() => queue('learn', 'Analyze settled results and log lessons', '🧠 Learn')}>
          <Brain /> Learn
        </Button>
        <Button variant="outline" onClick={() => (window.location.href = '/api/export.csv')}>
          <Download /> CSV
        </Button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <StatTile label="Bankroll" value={usd(stats.balance)} tone={stats.profit >= 0 ? 'pos' : 'neg'} />
          <StatTile label="P&L" value={usd(stats.profit, true)} tone={stats.profit >= 0 ? 'pos' : 'neg'} />
          <StatTile label="ROI" value={`${stats.roi}%`} tone={stats.roi >= 0 ? 'pos' : 'neg'} />
          <StatTile label="Record" value={`${stats.wins}–${stats.losses}`} sub={`${stats.win_rate}% win`} />
          <StatTile label="Pending" value={stats.pending} />
        </div>
      )}

      <div>
        <SectionTitle hint={stats ? `${games.size} games · tap a card to flip` : ''}>Picks</SectionTitle>
        {rows.length === 0 ? (
          <Empty>No active picks. Settled picks are archived off the board each day.</Empty>
        ) : (
          <div className="space-y-6">
            {Object.keys(byDate).map((d) => (
              <div key={d}>
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{d}</div>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                  {byDate[d].map(([k, legs]) => (
                    <GameCard
                      key={k}
                      legs={legs}
                      flipped={flipped.has(k)}
                      onFlip={() => toggleFlip(k)}
                      onSettle={() => {
                        setOpenKey(k)
                        setHs('')
                        setAs('')
                      }}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {settleGame && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setOpenKey(null)}>
          <Card className="w-full max-w-sm p-5" onClick={(e) => e.stopPropagation()}>
            <div className="text-sm font-semibold">Final score</div>
            <div className="mt-0.5 text-xs text-muted-foreground">{settleGame[0].match} · settles all legs</div>
            <div className="mt-4 flex items-center justify-center gap-3">
              <input className={scoreInput} type="number" min={0} value={hs} onChange={(e) => setHs(e.target.value)} placeholder="home" />
              <span className="text-muted-foreground">–</span>
              <input className={scoreInput} type="number" min={0} value={as_} onChange={(e) => setAs(e.target.value)} placeholder="away" />
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setOpenKey(null)}>
                Cancel
              </Button>
              <Button size="sm" onClick={() => settleScore(settleGame)}>
                Grade
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}

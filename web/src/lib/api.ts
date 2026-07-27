import { useCallback, useEffect, useState } from 'react'

export async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(String(r.status))
  return (await r.json()) as T
}

export async function postJSON<T = unknown>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  return (await r.json()) as T
}

export function patchJSON<T = unknown>(url: string, body: unknown): Promise<T> {
  return fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((r) => r.json() as Promise<T>)
}

/** Fetch on mount and whenever `key` changes. */
export function useApi<T>(url: string, key = 0) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const load = useCallback(() => {
    setLoading(true)
    getJSON<T>(url)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [url])
  useEffect(() => {
    load()
  }, [load, key])
  return { data, loading, reload: load }
}

// ---- models (match the Python JSON) ----
export interface Stats {
  total: number; pending: number; settled: number; wins: number; losses: number
  win_rate: number; staked: number; profit: number; roi: number
  bankroll_start: number; balance: number; growth_pct: number
}
export interface Prediction {
  id: number; event_date: string; sport: string; match: string; pick: string
  market: string; selection: string | null; line: number | null; odds: number | null
  stake: number | null; tag: string; status: string; kickoff: string | null
  rationale: string | null; profit: number; archived: number | null
  home_score: number | null; away_score: number | null; result_note: string | null
  settled_at: string | null
  pred_score: string | null; pred_corners_home: number | null; pred_corners_away: number | null
  home_corners: number | null; away_corners: number | null
  grid_json: string | null
}
export interface SlateGame {
  id: number; date: string; sport: string; tournament: string | null
  match: string | null; event_ticker: string | null; kickoff: string | null
  checked: number; starred: number; researched: number; note: string | null
}
export interface TagStat { n: number; w: number; l: number; staked: number; pnl: number; roi: number }
export interface Analysis {
  settled_count: number
  by_tag: Record<string, TagStat>; by_market: Record<string, TagStat>
  by_selection: Record<string, TagStat>; by_sport: Record<string, TagStat>; by_odds: Record<string, TagStat>
}
export interface Insight { id: number; created_at: string; summary: string; metrics: string }
export interface CornerBet {
  id: number; date: string; match: string; kickoff: string | null
  side: string; side_name: string | null; price: number; our_prob: number; edge: number
  stake: number; currency: string; status: string; hc: number | null; ac: number | null
  result_side: string | null; implied: number | null; pnl: number; note: string | null
}

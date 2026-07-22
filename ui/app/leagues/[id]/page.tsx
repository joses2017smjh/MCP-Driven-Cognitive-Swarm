"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import useSWR from "swr";
import { TieDetail } from "@/components/features/prediction/tie-detail";
import { Nav } from "@/components/ui/nav";
import { Badge, Panel, Skeleton } from "@/components/ui/panel";
import { jsonFetcher } from "@/lib/hooks";
import type { LeagueDetail, Tie } from "@/lib/types";

export default function LeaguePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, isLoading } = useSWR<LeagueDetail>(
    `/api/leagues/${id}`, jsonFetcher, { revalidateOnFocus: false },
  );

  const [home, setHome] = useState("");
  const [away, setAway] = useState("");
  const [tie, setTie] = useState<Tie | null>(null);
  const [busy, setBusy] = useState(false);
  const [predictError, setPredictError] = useState<string | null>(null);

  // default the selectors to the top two teams once data lands
  useEffect(() => {
    if (data?.standings?.length && !home && !away) {
      setHome(data.standings[0].team);
      setAway(data.standings[1]?.team ?? data.standings[0].team);
    }
  }, [data, home, away]);

  async function runMatchup(h = home, a = away) {
    if (!h || !a || h === a) {
      setPredictError("pick two different teams");
      return;
    }
    setBusy(true);
    setPredictError(null);
    try {
      const res = await fetch(
        `/api/leagues/${id}/predict?home=${encodeURIComponent(h)}&away=${encodeURIComponent(a)}`,
      );
      if (!res.ok) {
        setPredictError(`prediction failed (${res.status})`);
      } else {
        setTie((await res.json()) as Tie);
      }
    } catch {
      setPredictError("network error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Nav />
      <main className="flex-1 py-6">
        <Link href="/" className="text-2xs uppercase tracking-widest text-ink-600
          hover:text-ink-100">← all leagues</Link>

        {isLoading ? (
          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Skeleton className="h-96 lg:col-span-2" />
            <Skeleton className="h-96" />
          </div>
        ) : null}

        {error || (!isLoading && !data) ? (
          <Panel title="League unavailable">
            <p className="text-xs text-edge-neg">
              Could not load this league. Is the gateway running?
            </p>
          </Panel>
        ) : null}

        {data ? (
          <>
            <div className="mb-4 mt-2 flex flex-wrap items-baseline gap-3">
              <h1 className="text-xl font-bold tracking-tight">{data.name}</h1>
              <span className="text-2xs uppercase tracking-widest text-ink-600">
                {data.country} · {data.region}
              </span>
              <Badge>season {data.season}</Badge>
            </div>

            <div className="grid items-start gap-4 lg:grid-cols-3">
              {/* standings */}
              <Panel title="Standings" className="lg:col-span-2">
                <div className="overflow-x-auto">
                  <table className="tnum w-full min-w-[34rem] text-left text-2xs">
                    <thead className="text-ink-600">
                      <tr className="border-b border-line">
                        <th className="py-1.5 pr-2 font-medium">#</th>
                        <th className="py-1.5 pr-4 font-medium">team</th>
                        <th className="py-1.5 pr-2 font-medium">P</th>
                        <th className="py-1.5 pr-2 font-medium">W</th>
                        <th className="py-1.5 pr-2 font-medium">D</th>
                        <th className="py-1.5 pr-2 font-medium">L</th>
                        <th className="py-1.5 pr-2 font-medium">GF</th>
                        <th className="py-1.5 pr-2 font-medium">GA</th>
                        <th className="py-1.5 pr-2 font-medium">GD</th>
                        <th className="py-1.5 pr-2 font-medium">Pts</th>
                        <th className="py-1.5 font-medium">Elo</th>
                      </tr>
                    </thead>
                    <tbody className="text-ink-400">
                      {data.standings.map((row) => (
                        <tr key={row.team} className="border-b border-line/50">
                          <td className="py-1.5 pr-2">{row.rank}</td>
                          <td className="py-1.5 pr-4 font-semibold text-ink-100">
                            {row.team}
                          </td>
                          <td className="py-1.5 pr-2">{row.played}</td>
                          <td className="py-1.5 pr-2">{row.won}</td>
                          <td className="py-1.5 pr-2">{row.drawn}</td>
                          <td className="py-1.5 pr-2">{row.lost}</td>
                          <td className="py-1.5 pr-2">{row.gf}</td>
                          <td className="py-1.5 pr-2">{row.ga}</td>
                          <td className="py-1.5 pr-2">
                            {row.gd > 0 ? `+${row.gd}` : row.gd}
                          </td>
                          <td className="py-1.5 pr-2 font-bold text-ink-100">
                            {row.points}
                          </td>
                          <td className="py-1.5">{data.elo[row.team] ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>

              {/* right rail: fixtures + latest games */}
              <div className="flex flex-col gap-4">
                {data.upcoming_fixtures.length ? (
                  <Panel title="Upcoming fixtures">
                    <ul className="flex flex-col gap-2">
                      {data.upcoming_fixtures.slice(0, 8).map((f, i) => (
                        <li key={i}>
                          <button
                            onClick={() => {
                              setHome(f.home_team); setAway(f.away_team);
                              runMatchup(f.home_team, f.away_team);
                            }}
                            className="w-full rounded border border-line
                              bg-surface-800/60 px-2 py-1.5 text-left text-2xs
                              hover:border-brand/60"
                          >
                            <div className="text-ink-100">
                              {f.home_team} vs {f.away_team}
                            </div>
                            <div className="tnum text-ink-600">
                              {f.date} {f.time}
                              {f.odds_home ? ` · ${f.odds_home}/${f.odds_draw}/${f.odds_away}` : ""}
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </Panel>
                ) : null}

                <Panel title="Latest results">
                  <ul className="flex flex-col gap-1.5">
                    {data.recent_results.map((m, i) => (
                      <li key={i}>
                        <button
                          onClick={() => {
                            setHome(m.home_team); setAway(m.away_team);
                            runMatchup(m.home_team, m.away_team);
                          }}
                          className="flex w-full items-center justify-between gap-2
                            rounded px-1.5 py-1 text-2xs hover:bg-surface-800"
                          title="project this matchup"
                        >
                          <span className="truncate text-ink-100">
                            {m.home_team} <span className="tnum font-bold">
                              {m.home_score}–{m.away_score}</span> {m.away_team}
                          </span>
                          <span className="tnum shrink-0 text-ink-600">{m.date}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </Panel>
              </div>
            </div>

            {/* matchup projector */}
            <div className="mt-4">
              <Panel title="Project a matchup">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <select value={home} onChange={(e) => setHome(e.target.value)}
                    className="rounded border border-line bg-surface-800 px-2 py-1.5
                      text-xs text-ink-100">
                    {data.teams.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <span className="text-2xs uppercase tracking-widest text-ink-600">vs</span>
                  <select value={away} onChange={(e) => setAway(e.target.value)}
                    className="rounded border border-line bg-surface-800 px-2 py-1.5
                      text-xs text-ink-100">
                    {data.teams.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <button onClick={() => runMatchup()} disabled={busy}
                    className="rounded-md bg-brand px-3 py-1.5 text-xs font-semibold
                      text-surface-950 disabled:opacity-40">
                    {busy ? "Projecting…" : "Project"}
                  </button>
                  {predictError ? (
                    <span className="text-2xs text-edge-neg">{predictError}</span>
                  ) : null}
                </div>
                {tie ? <TieDetail tie={tie} /> : (
                  <p className="text-2xs text-ink-600">
                    Pick two teams (or click any result/fixture) to project the match.
                  </p>
                )}
              </Panel>
            </div>

            <p className="mt-4 text-2xs text-ink-600">{data.note}</p>
          </>
        ) : null}
      </main>
    </>
  );
}

"use client";

import { useState } from "react";
import useSWR from "swr";
import { TieDetail } from "@/components/features/prediction/tie-detail";
import { Nav } from "@/components/ui/nav";
import { Badge, Panel, Skeleton } from "@/components/ui/panel";
import { jsonFetcher } from "@/lib/hooks";
import type { Bracket, Tie } from "@/lib/types";
import { pct } from "@/lib/viz";

function MatchCell({ tie, onClick }: { tie: Tie; onClick: () => void }) {
  const winner = tie.projected_winner;
  const row = (team: string, seed?: number) => {
    const isWinner = team === winner;
    return (
      <div className={`flex items-center justify-between gap-2 px-2 py-1
        ${isWinner ? "text-ink-100" : "text-ink-600"}`}>
        <span className="flex min-w-0 items-center gap-1.5">
          {seed ? <span className="tnum text-2xs text-ink-600">{seed}</span> : null}
          <span className={`truncate text-2xs ${isWinner ? "font-bold" : ""}`}>
            {team}
          </span>
        </span>
        <span className="tnum shrink-0 text-2xs">{pct(tie.advance[team] ?? 0)}</span>
      </div>
    );
  };
  return (
    <button
      onClick={onClick}
      className="w-full rounded border border-line bg-surface-900 py-1
        text-left transition-colors hover:border-brand/60 hover:bg-surface-800"
      title="click to dive into the data"
    >
      {row(tie.home, tie.seeds?.home)}
      <div className="mx-2 border-t border-line/60" />
      {row(tie.away, tie.seeds?.away)}
    </button>
  );
}

export default function BracketPage() {
  const { data, error, isLoading } = useSWR<Bracket>("/api/bracket", jsonFetcher, {
    revalidateOnFocus: false,
  });
  const [selected, setSelected] = useState<Tie | null>(null);

  return (
    <>
      <Nav />
      <main className="flex-1 py-6">
        <div className="mb-4">
          <h1 className="text-xl font-bold tracking-tight">
            Women&apos;s World Cup — bracket projection
          </h1>
          {data ? (
            <p className="mt-1 max-w-3xl text-xs text-ink-400">{data.disclaimer}</p>
          ) : null}
        </div>

        {isLoading ? (
          <>
            <p className="mb-3 text-2xs text-ink-600">
              Building the bracket (Elo over ~11.6k internationals) — first load
              takes a few seconds…
            </p>
            <div className="grid gap-3 md:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-72" />
              ))}
            </div>
          </>
        ) : null}

        {error ? (
          <Panel title="Bracket unavailable">
            <p className="text-xs text-edge-neg">
              Could not build the bracket — the gateway may be offline or the
              data source unreachable.
            </p>
          </Panel>
        ) : null}

        {data ? (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <Badge tone="brand">projected champion · {data.champion}</Badge>
              <span className="text-2xs text-ink-600">
                strength: {String(data.model.strength_metric)} · ρ ={" "}
                {String(data.model.dixon_coles_rho)}
              </span>
            </div>

            {/* the tree: one column per round */}
            <div className="overflow-x-auto pb-2">
              <div className="grid min-w-[56rem] grid-cols-4 gap-3">
                {data.rounds.map((rnd) => (
                  <div key={rnd.round} className="flex flex-col">
                    <h2 className="mb-2 text-2xs font-semibold uppercase
                      tracking-widest text-ink-600">{rnd.round}</h2>
                    <div className="flex flex-1 flex-col justify-around gap-2">
                      {rnd.matches.map((tie, i) => (
                        <MatchCell key={i} tie={tie} onClick={() => setSelected(tie)} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <p className="mt-2 text-2xs text-ink-600">
              Percentages are each team&apos;s probability to advance (including
              extra time and penalties). Click any tie to dive into the data.
            </p>

            {/* seeding */}
            <div className="mt-5">
              <Panel title="Seeded field — opponent-adjusted Elo">
                <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-4">
                  {data.seeding.map((s) => (
                    <div key={s.team} className="flex items-baseline justify-between
                      gap-2 border-b border-line/40 py-1">
                      <span className="truncate text-2xs text-ink-100">
                        <span className="tnum mr-1.5 text-ink-600">{s.rank}</span>
                        {s.team}
                      </span>
                      <span className="tnum shrink-0 text-2xs text-ink-400">
                        {s.elo}
                      </span>
                    </div>
                  ))}
                </div>
              </Panel>
            </div>
          </>
        ) : null}

        {/* drill-down modal */}
        {selected ? (
          <div
            className="fixed inset-0 z-50 flex items-start justify-center
              overflow-y-auto bg-surface-950/80 p-4 backdrop-blur-sm"
            onClick={() => setSelected(null)}
          >
            <div
              className="panel my-8 w-full max-w-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="panel-header">
                <span>Match detail</span>
                <button onClick={() => setSelected(null)}
                  className="rounded border border-line px-1.5 py-0.5 text-2xs
                    text-ink-400 hover:border-line-strong hover:text-ink-100">
                  close
                </button>
              </div>
              <div className="p-4">
                <TieDetail tie={selected} />
              </div>
            </div>
          </div>
        ) : null}
      </main>
    </>
  );
}

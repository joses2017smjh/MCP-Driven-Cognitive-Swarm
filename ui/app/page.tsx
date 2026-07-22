"use client";

import Link from "next/link";
import useSWR from "swr";
import { Nav } from "@/components/ui/nav";
import { Panel, Skeleton } from "@/components/ui/panel";
import { jsonFetcher } from "@/lib/hooks";
import type { LeagueDirectory } from "@/lib/types";

function LeagueCard({ id, name, country }: { id: string; name: string; country: string }) {
  return (
    <Link
      href={`/leagues/${id}`}
      className="group flex items-center justify-between rounded-lg border
        border-line bg-surface-900 px-4 py-3 transition-colors
        hover:border-line-strong hover:bg-surface-800"
    >
      <div>
        <div className="text-sm font-semibold text-ink-100">{name}</div>
        <div className="text-2xs uppercase tracking-widest text-ink-600">{country}</div>
      </div>
      <span className="text-ink-600 transition-transform group-hover:translate-x-0.5
        group-hover:text-brand">→</span>
    </Link>
  );
}

export default function Home() {
  const { data, isLoading } = useSWR<LeagueDirectory>("/api/leagues", jsonFetcher);

  return (
    <>
      <Nav />
      <main className="flex-1 py-6">
        <div className="mb-6">
          <h1 className="text-xl font-bold tracking-tight">Leagues &amp; Tournaments</h1>
          <p className="mt-1 text-xs text-ink-400">
            Live standings, opponent-adjusted strength, and the latest results —
            click any league to browse games and project a matchup.
          </p>
        </div>

        {isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-16" />)}
          </div>
        ) : null}

        {data?.regions.map((r) => (
          <section key={r.region} className="mb-6">
            <h2 className="mb-2 text-2xs font-semibold uppercase tracking-widest text-ink-600">
              {r.region}
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {r.leagues.map((lg) => <LeagueCard key={lg.id} {...lg} />)}
            </div>
          </section>
        ))}

        {data?.tournaments.length ? (
          <section className="mb-6">
            <h2 className="mb-2 text-2xs font-semibold uppercase tracking-widest text-ink-600">
              International Tournaments
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.tournaments.map((t) =>
                t.type === "bracket" ? (
                  <Link key={t.id} href="/bracket"
                    className="group flex items-center justify-between rounded-lg
                      border border-brand/40 bg-surface-900 px-4 py-3
                      hover:border-brand hover:bg-surface-800">
                    <div>
                      <div className="text-sm font-semibold text-ink-100">{t.name}</div>
                      <div className="text-2xs uppercase tracking-widest text-brand">
                        bracket projection
                      </div>
                    </div>
                    <span className="text-brand">→</span>
                  </Link>
                ) : (
                  <div key={t.id} className="flex items-center justify-between
                    rounded-lg border border-line bg-surface-900 px-4 py-3 opacity-70">
                    <div>
                      <div className="text-sm font-semibold text-ink-100">{t.name}</div>
                      <div className="text-2xs uppercase tracking-widest text-ink-600">
                        report · scripts/wc26_predict
                      </div>
                    </div>
                  </div>
                ),
              )}
            </div>
          </section>
        ) : null}
      </main>

      <footer className="border-t border-line py-3 text-2xs text-ink-600">
        Standings &amp; results are real free data (football-data.co.uk, martj42).
        Matchup projections and scorers are model output, not betting advice.
      </footer>
    </>
  );
}

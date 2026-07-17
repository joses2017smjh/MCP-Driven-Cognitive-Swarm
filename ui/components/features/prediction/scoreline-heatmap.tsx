"use client";

/**
 * Dixon–Coles exact-score heatmap.
 *
 * 6x6 grid (home goals ↓, away goals →), sequential single-hue ramp scaled
 * to the max cell so structure stays readable; 2px surface gaps between
 * cells; the four τ-corrected cells (0-0, 1-0, 0-1, 1-1 — where the ρ
 * dependency parameter bends the independent-Poisson grid) carry a brand
 * ring and a footnote. Direct % labels on cells ≥ 4%; every cell has a
 * hover tooltip; a table toggle provides the accessible view.
 */

import { useMemo, useState } from "react";
import { Panel } from "@/components/ui/panel";
import type { ScorelineGrid } from "@/lib/types";
import { pct, rampColor, rampInk } from "@/lib/viz";

const RHO_CELLS = new Set(["0-0", "1-0", "0-1", "1-1"]);

export function ScorelineHeatmap({
  grid,
  home,
  away,
}: {
  grid: ScorelineGrid;
  home: string;
  away: string;
}) {
  const [view, setView] = useState<"grid" | "table">("grid");
  const [hover, setHover] = useState<{ h: number; a: number } | null>(null);

  const maxProb = useMemo(
    () => Math.max(...grid.probs.flat()),
    [grid],
  );
  const goals = Array.from({ length: grid.max_goals + 1 }, (_, i) => i);

  const flatSorted = useMemo(
    () =>
      goals
        .flatMap((h) => goals.map((a) => ({ h, a, p: grid.probs[h][a] })))
        .sort((x, y) => y.p - x.p),
    [grid, goals],
  );

  return (
    <Panel
      title="Exact score — Dixon-Coles grid"
      right={
        <button
          onClick={() => setView(view === "grid" ? "table" : "grid")}
          className="rounded border border-line px-1.5 py-0.5 text-2xs
            text-ink-400 hover:border-line-strong hover:text-ink-100"
        >
          {view === "grid" ? "table view" : "grid view"}
        </button>
      }
    >
      {view === "grid" ? (
        <div className="relative">
          <div className="mb-1 pl-10 text-2xs uppercase tracking-widest text-ink-600">
            {away} goals →
          </div>
          <div className="flex">
            <div
              className="flex items-center pr-1 text-2xs uppercase
                tracking-widest text-ink-600"
              style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
            >
              {home} goals ↓
            </div>
            <div className="flex-1">
              {/* column headers */}
              <div className="grid grid-cols-[1.25rem_repeat(6,1fr)] gap-0.5">
                <div />
                {goals.map((a) => (
                  <div key={a} className="tnum pb-0.5 text-center text-2xs text-ink-600">
                    {a}
                  </div>
                ))}
              </div>
              {goals.map((h) => (
                <div
                  key={h}
                  className="grid grid-cols-[1.25rem_repeat(6,1fr)] gap-0.5 pb-0.5"
                >
                  <div className="tnum flex items-center justify-center text-2xs text-ink-600">
                    {h}
                  </div>
                  {goals.map((a) => {
                    const p = grid.probs[h][a];
                    const t = maxProb > 0 ? p / maxProb : 0;
                    const key = `${h}-${a}`;
                    const isRho = RHO_CELLS.has(key);
                    return (
                      <div
                        key={key}
                        onMouseEnter={() => setHover({ h, a })}
                        onMouseLeave={() => setHover(null)}
                        className={`tnum relative flex aspect-square items-center
                          justify-center rounded-sm text-2xs font-semibold
                          ${isRho ? "ring-2 ring-inset ring-brand/70" : ""}`}
                        style={{ backgroundColor: rampColor(t), color: rampInk(t) }}
                        aria-label={`${home} ${h} - ${a} ${away}: ${pct(p, 1)}`}
                      >
                        {p >= 0.04 ? pct(p) : null}
                        {hover && hover.h === h && hover.a === a ? (
                          <div
                            className="pointer-events-none absolute bottom-full
                              left-1/2 z-10 mb-1 -translate-x-1/2 whitespace-nowrap
                              rounded border border-line-strong bg-surface-800
                              px-2 py-1 text-2xs font-normal text-ink-100 shadow-lg"
                          >
                            {home} {h}–{a} {away} · <span className="tnum">{pct(p, 1)}</span>
                            {isRho ? (
                              <span className="text-brand"> · ρ-adjusted</span>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
          {/* legend + footnotes */}
          <div className="mt-2 flex items-center gap-2 pl-10">
            <span className="tnum text-2xs text-ink-600">0%</span>
            <div
              className="h-1.5 w-28 rounded-full"
              style={{
                background: `linear-gradient(to right, ${rampColor(0)}, ${rampColor(0.5)}, ${rampColor(1)})`,
              }}
            />
            <span className="tnum text-2xs text-ink-600">{pct(maxProb, 1)}</span>
            <span className="ml-auto text-2xs text-ink-600">
              <span className="mr-1 inline-block h-2 w-2 rounded-sm ring-2 ring-inset ring-brand/70 align-middle" />
              ρ low-score correction
            </span>
          </div>
          {grid.tail_mass > 0.001 ? (
            <p className="mt-1 pl-10 text-2xs text-ink-600">
              {pct(grid.tail_mass, 1)} of probability lies beyond 5 goals a side.
            </p>
          ) : null}
        </div>
      ) : (
        <table className="tnum w-full text-left text-2xs">
          <thead className="text-ink-600">
            <tr className="border-b border-line">
              <th className="py-1 pr-4 font-medium">score</th>
              <th className="py-1 pr-4 font-medium">probability</th>
              <th className="py-1 font-medium">ρ cell</th>
            </tr>
          </thead>
          <tbody className="text-ink-400">
            {flatSorted.slice(0, 12).map(({ h, a, p }) => (
              <tr key={`${h}${a}`} className="border-b border-line/50">
                <td className="py-1 pr-4 text-ink-100">
                  {home} {h}–{a} {away}
                </td>
                <td className="py-1 pr-4">{pct(p, 1)}</td>
                <td className="py-1">{RHO_CELLS.has(`${h}-${a}`) ? "yes" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

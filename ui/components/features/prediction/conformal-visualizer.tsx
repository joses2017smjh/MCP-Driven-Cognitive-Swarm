"use client";

/**
 * Conformal prediction-set visualizer.
 *
 * One 100% bar in fixed home/draw/away order (home ↔ away are poles, draw
 * the neutral gray midpoint — diverging semantics, so identity never rides
 * on the gray alone: every segment is direct-labeled). Segments inside the
 * conformal set sit at full strength under a bracket stating the coverage
 * guarantee; excluded segments are dimmed and hatched out of the guarantee.
 * The point for a non-technical reader: "the real result lands under the
 * bracket at least 90% of the time — if two outcomes are under it, the
 * model genuinely can't separate them."
 */

import { useState } from "react";
import { Badge, Panel } from "@/components/ui/panel";
import type { MatchOutcome } from "@/lib/types";
import { pct, VIZ } from "@/lib/viz";

const ORDER = ["home", "draw", "away"] as const;
type Outcome = (typeof ORDER)[number];

export function ConformalVisualizer({
  outcome,
  home,
  away,
}: {
  outcome: MatchOutcome;
  home: string;
  away: string;
}) {
  const [hover, setHover] = useState<Outcome | null>(null);
  const coverage = 1 - outcome.conformal_alpha;
  const inSet = new Set(outcome.conformal_set);
  const labels: Record<Outcome, string> = { home, draw: "Draw", away };
  const colors: Record<Outcome, string> = {
    home: VIZ.home,
    draw: VIZ.draw,
    away: VIZ.away,
  };
  const setMass = ORDER.filter((o) => inSet.has(o)).reduce(
    (s, o) => s + outcome[o],
    0,
  );

  return (
    <Panel
      title="Uncertainty — conformal set"
      right={<Badge tone="brand">{pct(coverage)} coverage</Badge>}
    >
      <div className="flex flex-col gap-3">
        {/* the bar */}
        <div className="flex h-9 w-full gap-0.5 rounded-sm">
          {ORDER.map((o) => {
            const member = inSet.has(o);
            return (
              <div
                key={o}
                onMouseEnter={() => setHover(o)}
                onMouseLeave={() => setHover(null)}
                className="relative flex items-center justify-center
                  overflow-visible rounded-sm transition-opacity"
                style={{
                  width: `${outcome[o] * 100}%`,
                  backgroundColor: colors[o],
                  opacity: member ? 1 : 0.35,
                }}
              >
                {outcome[o] >= 0.12 ? (
                  <span
                    className="tnum text-2xs font-bold"
                    style={{ color: "#06080C" }}
                  >
                    {labels[o]} {pct(outcome[o])}
                  </span>
                ) : null}
                {hover === o ? (
                  <div
                    className="pointer-events-none absolute bottom-full left-1/2
                      z-10 mb-1 -translate-x-1/2 whitespace-nowrap rounded border
                      border-line-strong bg-surface-800 px-2 py-1 text-2xs
                      text-ink-100 shadow-lg"
                  >
                    {labels[o]} <span className="tnum">{pct(outcome[o], 1)}</span> ·{" "}
                    {member ? "inside the set" : "outside the set"}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>

        {/* bracket under the set members (fixed order keeps them contiguous
            in practice: the set is always the top-probability prefix) */}
        <div className="flex w-full gap-0.5">
          {ORDER.map((o) => (
            <div key={o} style={{ width: `${outcome[o] * 100}%` }}>
              {inSet.has(o) ? (
                <div className="h-1.5 rounded-b-sm border-b-2 border-l-2
                  border-r-2 border-brand/70" />
              ) : null}
            </div>
          ))}
        </div>

        <p className="text-xs leading-5 text-ink-400">
          {inSet.size === 1 ? (
            <>
              At {pct(coverage)} coverage the set is just{" "}
              <span className="font-semibold text-ink-100">
                {labels[[...inSet][0] as Outcome]}
              </span>{" "}
              — a confident call.
            </>
          ) : (
            <>
              The bracket holds{" "}
              <span className="font-semibold text-ink-100">
                {[...inSet].map((o) => labels[o as Outcome]).join(" + ")}
              </span>{" "}
              ({pct(setMass)} combined): in repeated use the true result lands
              under it at least {pct(coverage)} of the time. The model
              genuinely cannot separate these outcomes — treat it as open, not
              a pick.
            </>
          )}
        </p>

        {/* legend */}
        <div className="flex gap-4 text-2xs text-ink-600">
          {ORDER.map((o) => (
            <span key={o} className="flex items-center gap-1.5">
              <span
                className="inline-block h-2 w-2 rounded-sm"
                style={{ backgroundColor: colors[o], opacity: inSet.has(o) ? 1 : 0.35 }}
              />
              {labels[o]}
            </span>
          ))}
        </div>
      </div>
    </Panel>
  );
}

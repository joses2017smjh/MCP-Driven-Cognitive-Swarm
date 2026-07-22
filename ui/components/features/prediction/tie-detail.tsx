"use client";

/**
 * One predicted matchup, rendered in full: outcome bar, advancement,
 * scorelines, the goal-by-goal scenario (minute / scorer role / assist), and
 * a collapsible evidence block so the user can drill into exactly what drove
 * the call. Shared by the league matchup predictor and the bracket view.
 */

import { useState } from "react";
import { Badge } from "@/components/ui/panel";
import type { Tie } from "@/lib/types";
import { pct, VIZ } from "@/lib/viz";

export function TieDetail({ tie, compact = false }: { tie: Tie; compact?: boolean }) {
  const [showEvidence, setShowEvidence] = useState(false);
  const sc = tie.headline_scenario;
  const ev = tie.evidence;
  const o = tie.outcome_90;

  return (
    <div className="flex flex-col gap-3">
      {/* header */}
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-bold text-ink-100">
          {tie.home} <span className="text-ink-600">vs</span> {tie.away}
        </div>
        <Badge tone="brand">{tie.projected_winner} advances</Badge>
      </div>

      {/* outcome bar */}
      <div>
        <div className="flex h-7 w-full gap-0.5">
          {(["home", "draw", "away"] as const).map((k) => (
            <div
              key={k}
              className="flex items-center justify-center rounded-sm"
              style={{
                width: `${o[k] * 100}%`,
                backgroundColor:
                  k === "home" ? VIZ.home : k === "away" ? VIZ.away : VIZ.draw,
              }}
            >
              {o[k] >= 0.14 ? (
                <span className="tnum text-2xs font-bold" style={{ color: "#06080C" }}>
                  {pct(o[k])}
                </span>
              ) : null}
            </div>
          ))}
        </div>
        <div className="mt-1 flex justify-between text-2xs text-ink-600">
          <span>{tie.home} win</span>
          <span>draw</span>
          <span>{tie.away} win</span>
        </div>
      </div>

      {/* key numbers */}
      <div className="grid grid-cols-2 gap-2 text-2xs sm:grid-cols-4">
        <div className="rounded border border-line bg-surface-800/60 px-2 py-1.5">
          <div className="uppercase tracking-widest text-ink-600">xG</div>
          <div className="tnum font-semibold text-ink-100">
            {tie.expected_goals.home.toFixed(2)}–{tie.expected_goals.away.toFixed(2)}
          </div>
        </div>
        {Object.entries(tie.advance).map(([team, p]) => (
          <div key={team} className="rounded border border-line bg-surface-800/60 px-2 py-1.5">
            <div className="truncate uppercase tracking-widest text-ink-600">
              {team} adv.
            </div>
            <div className="tnum font-semibold text-ink-100">{pct(p)}</div>
          </div>
        ))}
        <div className="rounded border border-line bg-surface-800/60 px-2 py-1.5">
          <div className="uppercase tracking-widest text-ink-600">likely score</div>
          <div className="tnum font-semibold text-ink-100">
            {sc.scoreline} ({pct(sc.probability)})
          </div>
        </div>
      </div>

      {/* scenario: who scores, who assists, when */}
      <div className="rounded border border-line bg-surface-800/40 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-2xs font-semibold uppercase tracking-widest text-ink-600">
            Projected scenario
          </span>
          {sc.player_data ? (
            <Badge tone={sc.player_data === "statsbomb" ? "pos" : "neutral"}>
              {sc.player_data === "statsbomb"
                ? "real players · StatsBomb"
                : sc.player_data === "mixed" ? "partly named" : "role-level"}
            </Badge>
          ) : null}
        </div>
        {sc.goals.length ? (
          <ul className="flex flex-col gap-1">
            {sc.goals.map((g, i) => (
              <li key={i} className="text-xs text-ink-100">
                <span className="tnum font-bold text-brand">{g.minute}&prime;</span>{" "}
                {g.scorer_role}{" "}
                <span className="text-ink-600">
                  ({g.team === "home" ? tie.home : tie.away})
                </span>
                {g.assist_role ? (
                  <span className="text-ink-400"> · assist {g.assist_role}</span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-2xs text-ink-600">goalless in the modal scenario</p>
        )}
        {sc.penalties ? (
          <p className="mt-2 text-2xs text-ink-400">
            Level after extra time → <span className="font-semibold text-ink-100">
              {sc.penalties.winner}</span> on penalties ({pct(sc.penalties.p_advance)} to advance)
          </p>
        ) : null}
        <p className="mt-2 text-2xs text-ink-600">{sc.note}</p>
      </div>

      {!compact ? (
        <div className="flex flex-wrap gap-1.5">
          {tie.top_scorelines.map((s) => (
            <span key={s.score}
              className="tnum rounded border border-line px-1.5 py-0.5 text-2xs text-ink-400">
              {s.score} <span className="text-ink-600">{pct(s.prob)}</span>
            </span>
          ))}
        </div>
      ) : null}

      {/* drill-down */}
      <div>
        <button
          onClick={() => setShowEvidence((v) => !v)}
          className="rounded border border-line px-2 py-1 text-2xs text-ink-400
            hover:border-line-strong hover:text-ink-100"
        >
          {showEvidence ? "hide the data" : "dive into the data →"}
        </button>
        {showEvidence ? (
          <div className="mt-2 rounded border border-line bg-surface-800/60 p-3">
            <table className="tnum w-full text-left text-2xs">
              <tbody className="text-ink-400">
                <tr className="border-b border-line/50">
                  <td className="py-1 pr-4 text-ink-600">{tie.home} Elo</td>
                  <td className="py-1 text-ink-100">
                    {ev.home_rating.elo} ({ev.home_rating.matches} matches)
                  </td>
                </tr>
                <tr className="border-b border-line/50">
                  <td className="py-1 pr-4 text-ink-600">{tie.away} Elo</td>
                  <td className="py-1 text-ink-100">
                    {ev.away_rating.elo} ({ev.away_rating.matches} matches)
                  </td>
                </tr>
                <tr className="border-b border-line/50">
                  <td className="py-1 pr-4 text-ink-600">Elo difference</td>
                  <td className="py-1 text-ink-100">{ev.elo_difference}</td>
                </tr>
                <tr className="border-b border-line/50">
                  <td className="py-1 pr-4 text-ink-600">model xG (grid input)</td>
                  <td className="py-1 text-ink-100">
                    {ev.model_xg.home} / {ev.model_xg.away}
                  </td>
                </tr>
                <tr className="border-b border-line/50">
                  <td className="py-1 pr-4 text-ink-600">Dixon–Coles ρ</td>
                  <td className="py-1 text-ink-100">{ev.dixon_coles_rho}</td>
                </tr>
                <tr>
                  <td className="py-1 pr-4 align-top text-ink-600">method</td>
                  <td className="py-1 text-ink-400">{ev.method}</td>
                </tr>
              </tbody>
            </table>
            <p className="mt-2 text-2xs text-ink-600">
              First goal: {tie.home} {pct(tie.first_scorer.home_first)} ·{" "}
              {tie.away} {pct(tie.first_scorer.away_first)} · none{" "}
              {pct(tie.first_scorer.no_goals)}
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

"use client";

/**
 * Headline-scenario timeline — the sequence model rendered as a match report.
 *
 * A vertical spine from KICKOFF to FT; home goals branch left, away goals
 * right, each node carrying minute / scorer / assist with the team's pole
 * color (validated pair; team name is always printed, so identity never
 * rides on color alone). Penalties and Player of the Match close the card.
 * The scenario's probability is stated up front — this is the single most
 * likely story over the model's distributions, not a certainty.
 */

import { Badge, Panel } from "@/components/ui/panel";
import type { HeadlineScenario, ScenarioGoal } from "@/lib/types";
import { pct, VIZ } from "@/lib/viz";

function GoalNode({
  goal,
  team,
}: {
  goal: ScenarioGoal;
  team: string;
}) {
  const color = goal.team === "home" ? VIZ.home : VIZ.away;
  const isHome = goal.team === "home";
  return (
    <div className="relative grid grid-cols-[1fr_2.5rem_1fr] items-center">
      <div className={isHome ? "pr-1 text-right" : ""}>
        {isHome ? <GoalText goal={goal} team={team} align="right" /> : null}
      </div>
      <div className="flex flex-col items-center">
        <span
          className="tnum z-10 rounded-full border-2 px-1.5 py-0.5 text-2xs
            font-bold text-ink-100"
          style={{ borderColor: color, backgroundColor: "#0B0F16" }}
        >
          {goal.minute}&prime;
        </span>
      </div>
      <div className={!isHome ? "pl-1" : ""}>
        {!isHome ? <GoalText goal={goal} team={team} align="left" /> : null}
      </div>
    </div>
  );
}

function GoalText({
  goal,
  team,
  align,
}: {
  goal: ScenarioGoal;
  team: string;
  align: "left" | "right";
}) {
  return (
    <div className={align === "right" ? "text-right" : "text-left"}>
      <div className="text-xs font-semibold text-ink-100">
        {goal.scorer ?? "Goal"}{" "}
        <span className="text-ink-600">({team})</span>
      </div>
      {goal.assist ? (
        <div className="text-2xs text-ink-400">assisted by {goal.assist}</div>
      ) : null}
      {goal.p_scorer_anytime ? (
        <div className="tnum text-2xs text-ink-600">
          {pct(goal.p_scorer_anytime)} anytime
        </div>
      ) : null}
    </div>
  );
}

function SpineLabel({ children }: { children: string }) {
  return (
    <div className="flex justify-center">
      <span className="z-10 rounded border border-line bg-surface-800 px-2
        py-0.5 text-2xs font-semibold uppercase tracking-widest text-ink-600">
        {children}
      </span>
    </div>
  );
}

export function HeadlineTimeline({
  scenario,
  home,
  away,
}: {
  scenario: HeadlineScenario;
  home: string;
  away: string;
}) {
  const [gh, ga] = scenario.scoreline.split("-");
  const pens = scenario.penalties;
  const teamOf = (side: "home" | "away") => (side === "home" ? home : away);

  return (
    <Panel
      title="Headline scenario"
      right={<Badge tone="brand">{pct(scenario.probability)} most likely</Badge>}
    >
      <div className="mb-3 text-center">
        <span className="text-base font-bold text-ink-100">
          {home} {gh}–{ga} {away}
        </span>
        {pens ? (
          <div className="tnum mt-0.5 text-2xs text-ink-400">
            {teamOf(pens.winner)} win on penalties · {pct(pens.p_advance)} to advance
          </div>
        ) : null}
      </div>

      {/* team color key */}
      <div className="mb-2 grid grid-cols-[1fr_2.5rem_1fr] text-2xs font-semibold">
        <div className="text-right" style={{ color: VIZ.home }}>{home}</div>
        <div />
        <div style={{ color: VIZ.away }}>{away}</div>
      </div>

      <div className="relative flex flex-col gap-4 py-1">
        {/* the spine */}
        <div className="absolute bottom-0 left-1/2 top-0 w-px -translate-x-1/2
          bg-line-strong" />
        <SpineLabel>kickoff</SpineLabel>
        {scenario.goals.length ? (
          scenario.goals.map((g, i) => (
            <GoalNode key={i} goal={g} team={teamOf(g.team)} />
          ))
        ) : (
          <p className="z-10 mx-auto rounded bg-surface-800 px-2 text-2xs
            text-ink-600">
            no goals in the modal scenario
          </p>
        )}
        <SpineLabel>{pens ? "ft · pens" : "full time"}</SpineLabel>
      </div>

      {scenario.player_of_the_match ? (
        <div className="mt-3 border-t border-line pt-2 text-2xs text-ink-400">
          <span className="uppercase tracking-widest text-ink-600">
            Player of the Match:{" "}
          </span>
          <span className="font-semibold text-ink-100">
            {scenario.player_of_the_match}
          </span>
        </div>
      ) : null}
    </Panel>
  );
}

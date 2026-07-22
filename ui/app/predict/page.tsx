"use client";

import { PredictConsole } from "@/components/features/prediction/predict-console";
import { Nav } from "@/components/ui/nav";

export default function PredictPage() {
  return (
    <>
      <Nav />
      <main className="flex-1 py-6">
        <div className="mb-4">
          <h1 className="text-xl font-bold tracking-tight">Ask the Agent</h1>
          <p className="mt-1 text-xs text-ink-400">
            Natural-language match prediction through the MCP agent — conformal
            uncertainty, market value, and a full evidence trail.
          </p>
        </div>
        <PredictConsole />
      </main>
      <footer className="border-t border-line py-3 text-2xs text-ink-600">
        Staking suggestions always require human approval. Demo model — not
        betting advice.
      </footer>
    </>
  );
}

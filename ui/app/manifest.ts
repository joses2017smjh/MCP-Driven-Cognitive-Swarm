import type { MetadataRoute } from "next";

/** Lets Android "Add to home screen" install it as a standalone app. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "MatchIntel — Agentic Soccer Prediction",
    short_name: "MatchIntel",
    description:
      "League standings, opponent-adjusted strength, and model match projections.",
    start_url: "/",
    display: "standalone",
    background_color: "#06080C",
    theme_color: "#06080C",
    icons: [],
  };
}

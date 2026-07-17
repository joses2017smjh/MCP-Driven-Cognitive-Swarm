/**
 * Visualization tokens + the sequential ramp.
 *
 * Validated with the dataviz palette validator against this app's dark
 * surface (#0B0F16):
 * - poles home #3987e5 / away #D95926: all checks pass (worst CVD ΔE 26.8)
 * - draw is the neutral diverging midpoint (home ↔ away polarity), so it is
 *   deliberately gray and always direct-labeled — identity never rides on
 *   its color alone
 * - heatmap ramp steps #1c5cab→#b7d3f6 pass the ordinal checks; true zero is
 *   allowed to recede toward the surface (sequential heatmap rule)
 */

export const VIZ = {
  home: "#3987E5",
  away: "#D95926",
  draw: "#5C6880",
  surface: "#0B0F16",
} as const;

/** Ramp anchors, near-zero → max. First anchor recedes toward the surface. */
const RAMP = ["#12294D", "#1C5CAB", "#2A78D6", "#5598E7", "#86B6EF", "#B7D3F6"];

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** t in [0,1] → interpolated ramp color. */
export function rampColor(t: number): string {
  const x = Math.min(1, Math.max(0, t)) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(x));
  const f = x - i;
  const [r1, g1, b1] = hexToRgb(RAMP[i]);
  const [r2, g2, b2] = hexToRgb(RAMP[i + 1]);
  const c = (a: number, b: number) => Math.round(a + (b - a) * f);
  return `rgb(${c(r1, r2)}, ${c(g1, g2)}, ${c(b1, b2)})`;
}

/** Ink that stays readable on a ramp cell: dark text on the light end. */
export function rampInk(t: number): string {
  return t > 0.55 ? "#0B0F16" : "#EDF1F7";
}

export function pct(x: number, digits = 0): string {
  return `${(x * 100).toFixed(digits)}%`;
}

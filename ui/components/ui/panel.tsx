import type { ReactNode } from "react";

export function Panel({
  title,
  right,
  children,
  className = "",
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  // min-w-0 lets a panel shrink below its content's intrinsic width, so any
  // inner overflow-x-auto scrolls itself instead of stretching the page
  // (grid/flex children default to min-width:auto).
  return (
    <section className={`panel min-w-0 ${className}`}>
      <header className="panel-header gap-2">
        <h2 className="truncate">{title}</h2>
        {right}
      </header>
      <div className="min-w-0 p-4">{children}</div>
    </section>
  );
}

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "pos" | "neg" | "brand";
  children: ReactNode;
}) {
  const tones = {
    neutral: "border-line-strong text-ink-400",
    pos: "border-edge-pos/40 text-edge-pos",
    neg: "border-edge-neg/40 text-edge-neg",
    brand: "border-brand/50 text-brand",
  } as const;
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5
        text-2xs font-semibold uppercase tracking-wider ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-md border border-line bg-surface-800/60 px-3 py-2">
      <div className="text-2xs uppercase tracking-widest text-ink-600">{label}</div>
      <div className="tnum text-lg font-semibold text-ink-100">{value}</div>
      {hint ? <div className="text-2xs text-ink-600">{hint}</div> : null}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded bg-surface-800 ${className}`} />
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Badge } from "@/components/ui/panel";
import { useHealth } from "@/lib/hooks";

const LINKS = [
  { href: "/", label: "Leagues" },
  { href: "/bracket", label: "WWC Bracket" },
  { href: "/predict", label: "Ask the Agent" },
];

export function Nav() {
  const pathname = usePathname();
  const { data: health } = useHealth();
  return (
    <header className="flex items-center justify-between border-b border-line py-4">
      <div className="flex items-baseline gap-6">
        <Link href="/" className="text-lg font-bold tracking-tight">
          Match<span className="text-brand">Intel</span>
        </Link>
        <nav className="flex gap-4">
          {LINKS.map((l) => {
            const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`text-xs font-semibold uppercase tracking-widest
                  ${active ? "text-ink-100" : "text-ink-600 hover:text-ink-400"}`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
      {health?.ok ? (
        <Badge tone="pos">gateway up · {health.model_version}</Badge>
      ) : (
        <Badge tone="neg">gateway offline</Badge>
      )}
    </header>
  );
}

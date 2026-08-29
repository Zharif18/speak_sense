import Link from "next/link";
import { MiniWaveform } from "./waveform";

const LINKS = [
  { href: "/record", label: "Record" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/practice", label: "Daily practice" },
];

export function NavBar() {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-paper/90 backdrop-blur">
      <div className="container-page flex h-16 items-center justify-between">
        <Link href="/" className="flex items-center gap-2 font-display text-lg font-medium">
          <MiniWaveform tone="steady" />
          SpeakSense
        </Link>
        <nav className="hidden gap-8 text-sm md:flex">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="text-ink/70 hover:text-ink transition-colors">
              {l.label}
            </Link>
          ))}
        </nav>
        <Link
          href="/record"
          className="rounded-full bg-teal-600 px-4 py-2 text-sm font-medium text-paper hover:bg-teal-700 transition-colors"
        >
          Start a session
        </Link>
      </div>
    </header>
  );
}

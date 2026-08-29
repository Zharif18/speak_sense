"use client";

// The signature device for SpeakSense: a single waveform that reads as
// hesitant (uneven bars, muted color) on the left and steady (even rhythm,
// teal) on the right -- literally the transformation the product promises.
// Reused, smaller and static, wherever we want to signal "this is speech data".

const HESITANT_PATTERN = [18, 42, 12, 55, 8, 30, 46, 14, 60, 20, 10, 38];
const STEADY_PATTERN = [48, 56, 50, 60, 52, 58, 54, 62, 50, 58, 54, 60];

function bar(height: number, index: number, tone: "hesitant" | "steady") {
  const color = tone === "hesitant" ? "#7C93A8" : "#2F6F62";
  const delay = (index % 6) * 0.09;
  return (
    <span
      key={`${tone}-${index}`}
      className="inline-block w-[5px] md:w-[6px] rounded-full animate-wave origin-bottom"
      style={{
        height: `${height}%`,
        backgroundColor: color,
        animationDelay: `${delay}s`,
        opacity: tone === "hesitant" ? 0.55 + index * 0.02 : 0.85,
      }}
    />
  );
}

export function HeroWaveform() {
  return (
    <div
      className="flex h-24 md:h-32 w-full items-end gap-[3px] md:gap-1"
      role="img"
      aria-label="Waveform showing speech becoming steadier from left to right"
    >
      {HESITANT_PATTERN.map((h, i) => bar(h, i, "hesitant"))}
      <div className="mx-1 md:mx-2 flex h-full items-end">
        <svg width="22" height="22" viewBox="0 0 24 24" className="mb-1 text-amber-400">
          <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      {STEADY_PATTERN.map((h, i) => bar(h, i, "steady"))}
    </div>
  );
}

export function MiniWaveform({ tone = "steady" }: { tone?: "hesitant" | "steady" }) {
  const pattern = tone === "hesitant" ? HESITANT_PATTERN.slice(0, 7) : STEADY_PATTERN.slice(0, 7);
  return (
    <div className="flex h-6 items-end gap-[2px]" aria-hidden="true">
      {pattern.map((h, i) => bar(h, i, tone))}
    </div>
  );
}

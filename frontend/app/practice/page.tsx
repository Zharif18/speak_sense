import Link from "next/link";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const CHALLENGES = [
  {
    title: "The one-sentence opener",
    scenario: "Interview",
    difficulty: "Beginner",
    description: "Script and say only your opening line without a filler word. Let the rest be unscripted.",
  },
  {
    title: "Thirty seconds, no notes",
    scenario: "Impromptu",
    difficulty: "Intermediate",
    description: "Speak for 30 seconds on a topic you're handed cold. Aim for two full pauses instead of \"um.\"",
  },
  {
    title: "Introduce yourself, twice",
    scenario: "Introduction",
    difficulty: "Beginner",
    description: "Record the same introduction twice back to back. Compare pacing between the two takes.",
  },
  {
    title: "The pitch under pressure",
    scenario: "Presentation",
    difficulty: "Advanced",
    description: "60-second pitch, timed. If you go over, the challenge is to trim it live, not rush it.",
  },
];

export default function PracticePage() {
  return (
    <main className="container-page py-14 md:py-20">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-teal-600 mb-3">Today&apos;s set</p>
      <h1 className="text-3xl md:text-4xl mb-3 max-w-xl">Four challenges, picked from your last session.</h1>
      <p className="text-ink/60 mb-10 max-w-lg">
        These target the filler-word spike in your opening lines and the longer pauses
        in impromptu answers — the two patterns your recent sessions have in common.
      </p>

      <div className="grid gap-5 sm:grid-cols-2">
        {CHALLENGES.map((c) => (
          <Card key={c.title} className="flex flex-col">
            <div className="flex items-center gap-2 mb-3">
              <span className="rounded-full bg-teal-50 px-2.5 py-0.5 text-xs text-teal-700">{c.scenario}</span>
              <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs text-ink/70">{c.difficulty}</span>
            </div>
            <h3 className="font-display text-lg mb-2">{c.title}</h3>
            <p className="text-sm text-ink/65 leading-relaxed mb-6 flex-1">{c.description}</p>
            <Link href="/record">
              <Button variant="ghost" size="sm">Try this challenge</Button>
            </Link>
          </Card>
        ))}
      </div>
    </main>
  );
}

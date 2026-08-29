import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { HeroWaveform, MiniWaveform } from "@/components/speaksense/waveform";

const FLOW = [
  { step: "Record", detail: "Speak into a prompt — an interview question, an intro, a talk." },
  { step: "Analyze", detail: "We measure pacing, pauses, filler words, and repetition." },
  { step: "Understand", detail: "See exactly where hesitation shows up, and why." },
  { step: "Practice", detail: "A daily challenge targets what tripped you up last time." },
  { step: "Improve", detail: "Watch the same metrics move, session over session." },
];

const FEATURES = [
  {
    title: "Video and audio assessment",
    body: "Every recording is scored on pacing, pause length, filler words, repetition, and vocabulary — not just a single confidence number.",
  },
  {
    title: "AI coaching",
    body: "Feedback names what you did well before it names what to change, and every tip is something you can practice tomorrow.",
  },
  {
    title: "Daily challenges",
    body: "Interview questions, thirty-second impromptu prompts, and introductions, sequenced to what your last session showed you need.",
  },
  {
    title: "Vocabulary enrichment",
    body: "We flag the words you lean on when you're unsure what to say, and suggest sharper, context-specific alternatives.",
  },
  {
    title: "Progress tracking",
    body: "Pacing, filler rate, and confidence score plotted across every session, so improvement is something you can see.",
  },
  {
    title: "Wearable context",
    body: "If you wear a NoiseFit or any Health Connect device, we read your heart rate against your own baseline — never anyone else's.",
  },
];

export default function LandingPage() {
  return (
    <main>
      {/* Hero */}
      <section className="container-page pt-16 pb-20 md:pt-24 md:pb-28">
        <p className="mb-5 font-mono text-xs uppercase tracking-[0.18em] text-teal-600">
          A communication coach that listens
        </p>
        <h1 className="max-w-3xl text-4xl leading-[1.08] md:text-6xl">
          Your voice, <em className="not-italic text-teal-600">a little steadier</em> every time you use it.
        </h1>
        <p className="mt-6 max-w-xl text-lg text-ink/70">
          SpeakSense listens to how you speak — not just what you say — and turns
          hesitation, pacing, and filler words into practice you can actually do
          before your next interview, presentation, or introduction.
        </p>
        <div className="mt-9 flex flex-wrap items-center gap-4">
          <Link href="/record"><Button size="lg">Record your first session</Button></Link>
          <Link href="/dashboard"><Button size="lg" variant="ghost">See a sample dashboard</Button></Link>
        </div>

        <div className="mt-16 rounded-3xl border border-line bg-white/50 p-8 md:p-12">
          <HeroWaveform />
          <div className="mt-4 flex justify-between font-mono text-xs text-ink/50">
            <span>0:00 — hesitant pacing, 6 filler words</span>
            <span>0:42 — steady pacing, 1 filler word</span>
          </div>
        </div>
      </section>

      {/* Core flow — a real sequence, so numbering earns its place */}
      <section className="border-y border-line bg-white/40">
        <div className="container-page py-16 md:py-20">
          <h2 className="text-2xl md:text-3xl mb-2">Five steps, in this order</h2>
          <p className="text-ink/60 mb-10 max-w-lg">
            Each step feeds the next. You can&apos;t practice what you haven&apos;t understood,
            and you can&apos;t understand a session without first recording one.
          </p>
          <ol className="grid gap-6 md:grid-cols-5">
            {FLOW.map((f, i) => (
              <li key={f.step} className="relative">
                <span className="font-mono text-xs text-teal-600">0{i + 1}</span>
                <h3 className="mt-2 text-lg font-medium font-display">{f.step}</h3>
                <p className="mt-1.5 text-sm text-ink/60">{f.detail}</p>
                {i < FLOW.length - 1 && (
                  <span className="hidden md:block absolute top-1.5 -right-3 text-teal-600/40">—</span>
                )}
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Feature grid */}
      <section className="container-page py-16 md:py-24">
        <h2 className="text-2xl md:text-3xl mb-10">What each session gives you</h2>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <Card key={f.title}>
              <h3 className="font-display text-lg mb-2">{f.title}</h3>
              <p className="text-sm text-ink/65 leading-relaxed">{f.body}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* Communication Context Engine */}
      <section className="border-y border-line bg-white/40">
        <div className="container-page py-16 md:py-24">
          <div className="grid gap-12 md:grid-cols-2 md:items-center">
            <div>
              <p className="mb-3 font-mono text-xs uppercase tracking-[0.18em] text-mist-600">
                Communication Context Engine
              </p>
              <h2 className="text-2xl md:text-3xl mb-4">
                Speech is the signal. Context makes it useful.
              </h2>
              <p className="text-ink/70 leading-relaxed mb-4">
                The same filler-word rate means something different in a mock interview
                than in a casual introduction. We combine your speech metrics with the
                scenario, your recent sessions, and — if you connect a watch — your heart
                rate relative to your own resting baseline.
              </p>
              <p className="text-sm text-ink/50 leading-relaxed">
                Wearable data adds context to coaching. It is never used to label or
                diagnose how you feel.
              </p>
            </div>
            <div className="rounded-2xl border border-line bg-paper p-6 font-mono text-xs leading-relaxed text-ink/70">
              <div className="flex items-center gap-2 mb-3 text-teal-600">
                <MiniWaveform tone="steady" />
                <span>context payload — mock interview, session #12</span>
              </div>
              <pre className="whitespace-pre-wrap">{`{
  "scenario": "interview",
  "words_per_minute": 128,
  "filler_word_rate": 3.1,
  "pause_count": 9,
  "wearable_context": {
    "relative_stress_index": 0.06,
    "note": "hr slightly above resting baseline"
  },
  "recent_trend": "filler rate down 22% over 4 sessions"
}`}</pre>
            </div>
          </div>
        </div>
      </section>

      {/* Sponsor integrations — understated, functional framing */}
      <section className="container-page py-14">
        <p className="text-center text-xs uppercase tracking-[0.18em] text-ink/40 mb-6">
          Built with
        </p>
        <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-4 text-ink/55 font-display text-lg">
          <span title="Workflow automation">n8n</span>
          <span title="Deployment">Render</span>
          <span title="Vocabulary enrichment">Wolfram</span>
          <span title="Communication visualization">Miro</span>
          <span title="Live demo interaction">Slido</span>
        </div>
      </section>

      {/* Closing CTA */}
      <section className="container-page pb-24">
        <div className="rounded-3xl bg-teal-600 px-8 py-14 text-center text-paper md:px-16">
          <h2 className="text-2xl md:text-3xl mb-3">Ready to hear how you actually sound?</h2>
          <p className="text-paper/80 mb-8 max-w-md mx-auto">
            One recording is enough to see your first set of metrics. No account required to try it.
          </p>
          <Link href="/record">
            <Button variant="secondary" size="lg">Start recording</Button>
          </Link>
        </div>
      </section>
    </main>
  );
}

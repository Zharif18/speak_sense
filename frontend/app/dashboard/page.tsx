"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Card } from "@/components/ui/card";
import { MiniWaveform } from "@/components/speaksense/waveform";
import { WearableStatusCard } from "@/components/speaksense/wearable-status";
import { API_BASE } from "@/lib/api";
import { DEMO_USER_ID } from "@/lib/constants";

type ProgressPoint = {
  session_id: string;
  created_at: string;
  words_per_minute: number | null;
  filler_word_rate: number | null;
  confidence_score: number | null;
};

type ProgressOut = {
  user_id: string;
  points: ProgressPoint[];
  trend_summary: string;
};

type VocabularySuggestion = {
  word: string;
  context: string;
  alternatives: string[];
};

type SpeechMetrics = {
  transcript: string | null;
  words_per_minute: number | null;
  pause_count: number | null;
  avg_pause_seconds: number | null;
  longest_pause_seconds: number | null;
  filler_word_count: number | null;
  filler_word_rate: number | null;
  repetition_count: number | null;
  unique_word_ratio: number | null;
  vocabulary_suggestions: VocabularySuggestion[] | null;
  nervousness_score: number | null;
  nervousness_label: string | null;
};

type CoachingFeedback = {
  summary: string | null;
  strengths: string[] | null;
  improvement_tips: string[] | null;
  stress_index: number | null;
  stress_index_raw: number | null;
  stress_confidence: number | null;
  stress_reasons: string[] | null;
  confidence_score: number | null;
};

type VideoMetrics = {
  eye_contact_percent: number | null;
  eye_contact_breaks: number | null;
  posture_openness_score: number | null;
  posture_variability: number | null;
  gesture_rate_per_min: number | null;
  gesture_variability: number | null;
  head_movement_index: number | null;
  smile_percent: number | null;
  face_detection_rate: number | null;
  body_language_label: string | null;
};

type SessionFull = {
  id: string;
  scenario_type: string;
  status: string;
  created_at: string;
  speech_metrics: SpeechMetrics | null;
  video_metrics: VideoMetrics | null;
  coaching_feedback: CoachingFeedback | null;
};

function formatChartDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function speakText(text: string, onEnd?: () => void) {
  if (!("speechSynthesis" in window)) return false;
  window.speechSynthesis.cancel(); // stop any prior utterance first
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.0;
  utterance.pitch = 1.0;
  if (onEnd) utterance.onend = onEnd;
  window.speechSynthesis.speak(utterance);
  return true;
}

function SpeakButton({ text }: { text: string }) {
  const [speaking, setSpeaking] = useState(false);
  const [supported, setSupported] = useState(true);

  useEffect(() => {
    setSupported("speechSynthesis" in window);
  }, []);

  if (!supported) return null;

  function handleClick() {
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    setSpeaking(true);
    const started = speakText(text, () => setSpeaking(false));
    if (!started) setSpeaking(false);
  }

  return (
    <button
      onClick={handleClick}
      className="inline-flex items-center gap-1.5 text-xs font-mono text-teal-700 hover:text-teal-800 mb-3"
    >
      {speaking ? "◼ Stop" : "🔊 Listen to your coaching notes"}
    </button>
  );
}

function DashboardContent() {
  const searchParams = useSearchParams();
  const requestedSessionId = searchParams.get("session");

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressOut | null>(null);
  const [session, setSession] = useState<SessionFull | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setLoadError(null);
      try {
        const progressRes = await fetch(`${API_BASE}/api/sessions/user/${DEMO_USER_ID}/progress`);
        if (!progressRes.ok) throw new Error(`Progress fetch failed (${progressRes.status})`);
        const progressData: ProgressOut = await progressRes.json();
        if (cancelled) return;
        setProgress(progressData);

        // Prefer the session just recorded (passed via ?session=); otherwise
        // fall back to the most recent analyzed session.
        const targetId =
          requestedSessionId || progressData.points[progressData.points.length - 1]?.session_id;

        if (targetId) {
          const sessionRes = await fetch(`${API_BASE}/api/sessions/${targetId}/full`);
          if (!sessionRes.ok) throw new Error(`Session fetch failed (${sessionRes.status})`);
          const sessionData: SessionFull = await sessionRes.json();
          if (cancelled) return;
          setSession(sessionData);
        }
      } catch (err) {
        console.error(err);
        if (!cancelled) setLoadError("Couldn't load your dashboard data. Is the backend running?");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [requestedSessionId]);

  const chartData =
    progress?.points
      .filter((p) => p.confidence_score !== null)
      .map((p) => ({ session: formatChartDate(p.created_at), confidence: p.confidence_score })) ?? [];

  const metrics = session?.speech_metrics;
  const video = session?.video_metrics;
  const feedback = session?.coaching_feedback;

  if (loading) {
    return (
      <main className="container-page py-14 md:py-20">
        <p className="text-sm text-ink/50">Loading your progress…</p>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="container-page py-14 md:py-20">
        <p className="text-sm text-red-600">{loadError}</p>
      </main>
    );
  }

  const hasAnySessions = (progress?.points.length ?? 0) > 0;

  if (!hasAnySessions) {
    return (
      <main className="container-page py-14 md:py-20">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-teal-600 mb-3">Your progress</p>
        <h1 className="text-3xl md:text-4xl mb-6 max-w-xl">No sessions yet.</h1>
        <p className="text-sm text-ink/60 mb-6">
          Record your first practice session and your real pacing, filler words, pauses, and
          tailored coaching notes will show up here.
        </p>
        <a href="/record" className="underline text-teal-700 text-sm">Go record one →</a>
      </main>
    );
  }

  const sessionStillProcessing = session && session.status !== "analyzed";

  return (
    <main className="container-page py-14 md:py-20">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-teal-600 mb-3">Your progress</p>
      <h1 className="text-3xl md:text-4xl mb-10">
        {progress!.points.length} session{progress!.points.length === 1 ? "" : "s"} in, and it shows.
      </h1>

      <div className="mb-6">
        <WearableStatusCard />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <Card className="p-6 md:p-8">
          <div className="flex items-center justify-between mb-6">
            <h2 className="font-display text-lg">Confidence score over time</h2>
            <MiniWaveform tone="steady" />
          </div>
          <div className="h-64">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ left: -10 }}>
                  <CartesianGrid stroke="#DDE3DF" vertical={false} />
                  <XAxis dataKey="session" tick={{ fontSize: 12, fill: "#1C2321aa" }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: "#1C2321aa" }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid #DDE3DF", fontSize: 13 }} />
                  <Line type="monotone" dataKey="confidence" stroke="#2F6F62" strokeWidth={2.5} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-ink/40 h-full flex items-center justify-center">
                Confidence scores will appear here once coaching feedback has been generated.
              </p>
            )}
          </div>
          <p className="mt-4 text-sm text-ink/60">{progress!.trend_summary}</p>
          <p className="mt-1 text-xs text-ink/40">
            Confidence score is a heuristic composite of pacing, filler rate, and pauses —
            not a measurement of how confident you felt.
          </p>
        </Card>

        <Card className="p-6 md:p-8">
          <h2 className="font-display text-lg mb-5">Latest session</h2>
          {sessionStillProcessing && (
            <p className="text-sm text-ink/50">
              This session is still being analyzed — refresh in a moment.
            </p>
          )}
          {metrics && (
            <dl className="space-y-4">
              <div className="flex items-baseline justify-between gap-4">
                <div>
                  <dt className="text-sm text-ink/60">Words per minute</dt>
                  <dd className="text-xs text-ink/40">
                    {metrics.words_per_minute && metrics.words_per_minute >= 120 && metrics.words_per_minute <= 150
                      ? "in the 120–150 conversational range"
                      : "conversational range is typically 120–150"}
                  </dd>
                </div>
                <dd className="font-mono text-sm font-medium shrink-0">
                  {metrics.words_per_minute ?? "—"}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <div>
                  <dt className="text-sm text-ink/60">Filler words</dt>
                  <dd className="text-xs text-ink/40">{metrics.filler_word_count ?? 0} total this session</dd>
                </div>
                <dd className="font-mono text-sm font-medium shrink-0">
                  {metrics.filler_word_rate ?? "—"} / 100 words
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <div>
                  <dt className="text-sm text-ink/60">Pauses over 0.6s</dt>
                  <dd className="text-xs text-ink/40">
                    longest was {metrics.longest_pause_seconds ?? 0}s
                  </dd>
                </div>
                <dd className="font-mono text-sm font-medium shrink-0">{metrics.pause_count ?? "—"}</dd>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <div>
                  <dt className="text-sm text-ink/60">Vocabulary variety</dt>
                  <dd className="text-xs text-ink/40">type-token ratio across the session</dd>
                </div>
                <dd className="font-mono text-sm font-medium shrink-0">{metrics.unique_word_ratio ?? "—"}</dd>
              </div>
              {metrics.nervousness_label && (
                <div className="flex items-baseline justify-between gap-4">
                  <div>
                    <dt className="text-sm text-ink/60">Vocal tension</dt>
                    <dd className="text-xs text-ink/40">from pitch/energy stability in your voice</dd>
                  </div>
                  <dd className="font-mono text-sm font-medium shrink-0 capitalize">{metrics.nervousness_label}</dd>
                </div>
              )}
            </dl>
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2 mt-6">
        {video && (
          <Card className="p-6 md:p-8">
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-display text-lg">Body language</h2>
              {video.body_language_label && (
                <span className="rounded-full bg-teal-50 px-3 py-1 text-xs font-mono text-teal-700 capitalize">
                  {video.body_language_label}
                </span>
              )}
            </div>
            <p className="text-xs text-ink/40 mb-5">
              From eye/pose tracking on your session video — a delivery signal, not a read on how you felt.
            </p>
            <dl className="space-y-4">
              <div className="flex items-baseline justify-between gap-4">
                <div>
                  <dt className="text-sm text-ink/60">Eye contact</dt>
                  <dd className="text-xs text-ink/40">
                    {video.eye_contact_breaks ?? 0} look-away{video.eye_contact_breaks === 1 ? "" : "s"} over 0.5s
                  </dd>
                </div>
                <dd className="font-mono text-sm font-medium shrink-0">
                  {video.eye_contact_percent ?? "—"}%
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <div>
                  <dt className="text-sm text-ink/60">Posture openness</dt>
                  <dd className="text-xs text-ink/40">shoulder/torso centeredness, 0–100</dd>
                </div>
                <dd className="font-mono text-sm font-medium shrink-0">
                  {video.posture_openness_score ?? "—"}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <div>
                  <dt className="text-sm text-ink/60">Hand gestures</dt>
                  <dd className="text-xs text-ink/40">movement events detected</dd>
                </div>
                <dd className="font-mono text-sm font-medium shrink-0">
                  {video.gesture_rate_per_min ?? "—"}/min
                </dd>
              </div>
              {video.smile_percent !== null && video.smile_percent !== undefined && (
                <div className="flex items-baseline justify-between gap-4">
                  <div>
                    <dt className="text-sm text-ink/60">Smiling</dt>
                    <dd className="text-xs text-ink/40">% of frames with a detected smile</dd>
                  </div>
                  <dd className="font-mono text-sm font-medium shrink-0">{video.smile_percent}%</dd>
                </div>
              )}
            </dl>
          </Card>
        )}

        <Card className="p-6 md:p-8">
          <h2 className="font-display text-lg mb-2">Coaching notes</h2>
          {feedback?.summary ? (
            <>
              <SpeakButton
                text={[feedback.summary, ...(feedback.improvement_tips ?? [])].join(". ")}
              />
              <p className="text-sm text-ink/70 leading-relaxed mb-4">{feedback.summary}</p>
              {feedback.improvement_tips && feedback.improvement_tips.length > 0 && (
                <ul className="text-sm text-ink/70 list-disc list-inside space-y-1 mb-4">
                  {feedback.improvement_tips.map((tip, i) => (
                    <li key={i}>{tip}</li>
                  ))}
                </ul>
              )}
              {feedback.stress_index !== null && feedback.stress_index !== undefined && (
                <div className="text-xs text-mist-600 border-t border-line pt-4 space-y-1">
                  <p>
                    Heart rate was {Math.abs(Math.round(feedback.stress_index * 100))}%{" "}
                    {feedback.stress_index >= 0 ? "above" : "below"} your resting baseline during this session.
                  </p>
                  {feedback.stress_confidence !== null && feedback.stress_confidence !== undefined && (
                    <p className="text-ink/40">
                      Confidence in this reading: {Math.round(feedback.stress_confidence * 100)}%
                      {feedback.stress_reasons && feedback.stress_reasons.length > 0
                        ? ` — ${feedback.stress_reasons.join("; ")}`
                        : ""}
                    </p>
                  )}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-ink/40">
              No coaching feedback yet for this session.
            </p>
          )}
        </Card>

        <Card className="p-6 md:p-8">
          <h2 className="font-display text-lg mb-4">Words worth swapping</h2>
          {metrics?.vocabulary_suggestions && metrics.vocabulary_suggestions.length > 0 ? (
            <ul className="space-y-4">
              {metrics.vocabulary_suggestions.map((v) => (
                <li key={v.word} className="text-sm">
                  <span className="font-mono text-ink/80">&quot;{v.word}&quot;</span>{" "}
                  <span className="text-ink/40">— {v.context}</span>
                  <div className="mt-1.5 flex flex-wrap gap-2">
                    {v.alternatives.map((alt) => (
                      <span key={alt} className="rounded-full bg-teal-50 px-3 py-1 text-xs text-teal-700">
                        {alt}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink/40">No repeated words flagged in this session.</p>
          )}
        </Card>
      </div>
    </main>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<main className="container-page py-14 md:py-20"><p className="text-sm text-ink/50">Loading…</p></main>}>
      <DashboardContent />
    </Suspense>
  );
}
"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { MiniWaveform } from "@/components/speaksense/waveform";
import { WearableStatusCard } from "@/components/speaksense/wearable-status";
import { API_BASE } from "@/lib/api";
import { DEMO_USER_ID } from "@/lib/constants";

const SCENARIOS = [
  { value: "interview", label: "Mock interview", prompt: "Tell me about a time you handled a setback." },
  { value: "presentation", label: "Presentation", prompt: "Give a 60-second pitch for a project you care about." },
  { value: "impromptu", label: "Impromptu", prompt: "Speak for 30 seconds on: is remote work good for students?" },
  { value: "introduction", label: "Introduction", prompt: "Introduce yourself as you would on the first day of a new job." },
];

type RecordingState = "idle" | "recording" | "recorded" | "uploading" | "done" | "error";

// Live-preview only. The backend's Whisper pipeline (word-level timestamps,
// vocabulary suggestions, etc.) remains the source of truth once submitted --
// this is just fast, in-browser feedback so recording doesn't feel like a
// black box. Chrome/Edge only; other browsers just won't show the live panel.
const LIVE_FILLER_REGEX = /\b(um+|uh+|like|you know|actually|basically|literally|i mean|kind of|sort of|right)\b/gi;
const LIVE_PAUSE_THRESHOLD_SECONDS = 1.2;

function countLiveFillers(text: string): number {
  const matches = text.toLowerCase().match(LIVE_FILLER_REGEX);
  return matches ? matches.length : 0;
}

export default function RecordPage() {
  const [scenario, setScenario] = useState(SCENARIOS[0]);
  const [state, setState] = useState<RecordingState>("idle");
  const [seconds, setSeconds] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [lastSessionId, setLastSessionId] = useState<string | null>(null);

  // Live-feedback state (updates while recording).
  const [speechSupported, setSpeechSupported] = useState(true);
  const [liveInterim, setLiveInterim] = useState("");
  const [liveWpm, setLiveWpm] = useState(0);
  const [liveFillerCount, setLiveFillerCount] = useState(0);
  const [livePauseCount, setLivePauseCount] = useState(0);
  const [isPausing, setIsPausing] = useState(false);

  // Video (body language) — camera is on for the whole session; MediaRecorder
  // captures audio+video together, then we split it server-side: the same
  // blob is sent to /api/speech for transcription AND /api/video for
  // eye-contact/posture analysis.
  const [cameraEnabled, setCameraEnabled] = useState(true);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const videoPreviewRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const hasVideoRef = useRef(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioUrlRef = useRef<string | null>(null);

  const recognitionRef = useRef<any>(null);
  const recordStartRef = useRef<number>(0);
  const lastSpeechTimeRef = useRef<number>(0);
  const wasPausingRef = useRef(false);
  const pauseCheckIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const liveFinalTranscriptRef = useRef("");
  const liveFillerCountRef = useRef(0);

  function startLiveRecognition() {
    const SpeechRecognitionCtor =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognitionCtor) {
      setSpeechSupported(false);
      return;
    }

    liveFinalTranscriptRef.current = "";
    liveFillerCountRef.current = 0;
    recordStartRef.current = performance.now();
    lastSpeechTimeRef.current = performance.now();
    wasPausingRef.current = false;

    const recognition = new SpeechRecognitionCtor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (event: any) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0].transcript;
        if (result.isFinal) {
          liveFinalTranscriptRef.current += text + " ";
          liveFillerCountRef.current += countLiveFillers(text);
          setLiveFillerCount(liveFillerCountRef.current);
        } else {
          interim += text;
        }
      }

      lastSpeechTimeRef.current = performance.now();
      setLiveInterim(interim);

      const elapsedMinutes = Math.max(
        (performance.now() - recordStartRef.current) / 60000,
        1 / 60
      );
      const wordCount = (liveFinalTranscriptRef.current + " " + interim)
        .trim()
        .split(/\s+/)
        .filter(Boolean).length;
      setLiveWpm(Math.round(wordCount / elapsedMinutes));
    };

    recognition.onerror = (e: any) => {
      // "no-speech" fires constantly during natural pauses -- not an error.
      if (e.error !== "no-speech") {
        console.warn("Speech recognition error:", e.error);
      }
    };

    recognition.onend = () => {
      // Chrome stops the recognizer after a stretch of silence; restart it
      // as long as we're still actually recording.
      if (mediaRecorderRef.current?.state === "recording") {
        try {
          recognition.start();
        } catch {
          /* already starting */
        }
      }
    };

    recognition.start();
    recognitionRef.current = recognition;

    pauseCheckIntervalRef.current = setInterval(() => {
      const silenceSeconds = (performance.now() - lastSpeechTimeRef.current) / 1000;
      const nowPausing = silenceSeconds >= LIVE_PAUSE_THRESHOLD_SECONDS;

      if (nowPausing && !wasPausingRef.current) {
        wasPausingRef.current = true;
        setIsPausing(true);
      } else if (!nowPausing && wasPausingRef.current) {
        wasPausingRef.current = false;
        setIsPausing(false);
        setLivePauseCount((c) => c + 1);
      }
    }, 200);
  }

  function stopLiveRecognition() {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    if (pauseCheckIntervalRef.current) clearInterval(pauseCheckIntervalRef.current);
    setIsPausing(false);
  }

  async function startRecording() {
    setErrorMsg(null);
    setCameraError(null);

    let stream: MediaStream;
    let recordingHasVideo = cameraEnabled;
    try {
      stream = await navigator.mediaDevices.getUserMedia(
        cameraEnabled
          ? { audio: true, video: { width: 640, height: 480, facingMode: "user" } }
          : { audio: true }
      );
    } catch (err) {
      if (cameraEnabled) {
        // Camera denied/unavailable — fall back to audio-only so the core
        // speech coaching flow still works; body-language analysis is skipped.
        setCameraError(
          "Couldn't access your camera, so body-language analysis will be skipped for this session. Audio recording will still work."
        );
        recordingHasVideo = false;
        try {
          stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch {
          setErrorMsg(
            "Couldn't access your microphone. Check your browser's permission settings and try again."
          );
          setState("error");
          return;
        }
      } else {
        setErrorMsg(
          "Couldn't access your microphone. Check your browser's permission settings and try again."
        );
        setState("error");
        return;
      }
    }

    streamRef.current = stream;
    if (recordingHasVideo && videoPreviewRef.current) {
      videoPreviewRef.current.srcObject = stream;
    }
    hasVideoRef.current = recordingHasVideo;

    const mimeType = recordingHasVideo
      ? MediaRecorder.isTypeSupported("video/webm;codecs=vp9,opus")
        ? "video/webm;codecs=vp9,opus"
        : "video/webm"
      : "audio/webm";
    const recorder = new MediaRecorder(stream, { mimeType });
    chunksRef.current = [];

    recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: mimeType });
      audioUrlRef.current = URL.createObjectURL(blob);
      setState("recorded");
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };

    recorder.start();
    mediaRecorderRef.current = recorder;
    setState("recording");
    setSeconds(0);
    setLiveInterim("");
    setLiveWpm(0);
    setLiveFillerCount(0);
    setLivePauseCount(0);
    timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);

    startLiveRecognition();
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    if (timerRef.current) clearInterval(timerRef.current);
    stopLiveRecognition();
  }

  async function submitRecording() {
    setState("uploading");
    try {
      // 1) Create the session record.
      const sessionRes = await fetch(`${API_BASE}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: DEMO_USER_ID, // replace with the authenticated user's id once auth exists
          scenario_type: scenario.value,
          prompt_text: scenario.prompt,
        }),
      });
      if (!sessionRes.ok) {
        throw new Error(`Couldn't create session (${sessionRes.status}): ${await sessionRes.text()}`);
      }
      const session = await sessionRes.json();

      // 2) Upload the audio for analysis.
      const chunks = chunksRef.current;
      const recordedMimeType = mediaRecorderRef.current?.mimeType || "audio/webm";
      const blob = new Blob(chunks, { type: recordedMimeType });
      const formData = new FormData();
      formData.append("audio", blob, "session.webm");

      const analyzeRes = await fetch(`${API_BASE}/api/speech/${session.id}/analyze`, {
        method: "POST",
        body: formData,
      });
      if (!analyzeRes.ok) {
        throw new Error(`Analysis failed (${analyzeRes.status}): ${await analyzeRes.text()}`);
      }

      // 2b) If the recording included video, send the same clip to the
      // body-language pipeline too (eye contact, posture, gesture). This
      // runs independently of speech analysis and never blocks it — a
      // failure here still lets the rest of the session complete.
      if (hasVideoRef.current) {
        try {
          const videoFormData = new FormData();
          videoFormData.append("video", blob, "session.webm");
          const videoRes = await fetch(`${API_BASE}/api/video/${session.id}/analyze`, {
            method: "POST",
            body: videoFormData,
          });
          if (!videoRes.ok) {
            console.warn(`Video analysis failed (${videoRes.status}): ${await videoRes.text()}`);
          }
        } catch (videoErr) {
          console.warn("Video analysis request failed:", videoErr);
        }
      }

      // 2c) Sweep up any watch readings (heart rate, etc.) that landed in this
      // session's recording window but weren't tagged with a session_id yet --
      // e.g. an Android Health Connect bridge syncing NoiseFit data in the
      // background. Never blocks the rest of the flow if it fails.
      try {
        const claimRes = await fetch(`${API_BASE}/api/wearables/session/${session.id}/claim`, {
          method: "POST",
        });
        if (!claimRes.ok) {
          console.warn(`Wearable claim failed (${claimRes.status}): ${await claimRes.text()}`);
        }
      } catch (claimErr) {
        console.warn("Wearable claim request failed:", claimErr);
      }

      // 3) Generate tailored coaching feedback from this session's real
      //    metrics (+ recent history + stress index/body-language if present).
      const coachingRes = await fetch(`${API_BASE}/api/coaching/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: session.id }),
      });
      if (!coachingRes.ok) {
        throw new Error(`Coaching generation failed (${coachingRes.status}): ${await coachingRes.text()}`);
      }

      setState("done");
      setLastSessionId(session.id);
    } catch (err) {
      console.error(err);
      setErrorMsg("Upload failed. Your recording is still in the browser — try submitting again.");
      setState("error");
    }
  }

  function resetSession() {
    stopLiveRecognition();
    setState("idle");
    setSeconds(0);
    setLiveInterim("");
    setLiveWpm(0);
    setLiveFillerCount(0);
    setLivePauseCount(0);
    audioUrlRef.current = null;
    setCameraError(null);
    hasVideoRef.current = false;
    if (videoPreviewRef.current) videoPreviewRef.current.srcObject = null;
  }

  return (
    <main className="container-page py-14 md:py-20">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-teal-600 mb-3">Step 1 — Record</p>
      <h1 className="text-3xl md:text-4xl mb-8 max-w-xl">Pick a scenario, then just talk.</h1>

      <div className="mb-8">
        <WearableStatusCard />
      </div>

      <div className="grid gap-8 md:grid-cols-[1fr_1.2fr]">
        <div>
          <p className="text-sm font-medium mb-3 text-ink/70">Scenario</p>
          <div className="flex flex-col gap-2">
            {SCENARIOS.map((s) => (
              <button
                key={s.value}
                onClick={() => state === "idle" && setScenario(s)}
                disabled={state !== "idle"}
                className={`text-left rounded-xl border px-4 py-3 text-sm transition-colors ${
                  scenario.value === s.value
                    ? "border-teal-600 bg-teal-50 text-teal-700"
                    : "border-line bg-white/50 text-ink/70 hover:border-teal-600/40"
                } disabled:opacity-60`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        <Card>
          <p className="text-xs uppercase tracking-wide text-ink/40 mb-2">Your prompt</p>
          <p className="text-lg font-display mb-6">{scenario.prompt}</p>

          {(state === "idle" || state === "recording") && (
            <div className="mb-6">
              <div className="relative overflow-hidden rounded-xl border border-line bg-ink/5 aspect-video">
                {cameraEnabled ? (
                  <video
                    ref={videoPreviewRef}
                    autoPlay
                    muted
                    playsInline
                    className="h-full w-full object-cover -scale-x-100"
                  />
                ) : (
                  <div className="flex h-full w-full items-center justify-center">
                    <p className="text-xs text-ink/40">
                      Camera off — body-language analysis (eye contact, posture) will be skipped.
                    </p>
                  </div>
                )}
                {state === "recording" && cameraEnabled && hasVideoRef.current && (
                  <span className="absolute top-3 left-3 flex items-center gap-1.5 rounded-full bg-black/50 px-2.5 py-1 text-xs text-white">
                    <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
                    REC
                  </span>
                )}
              </div>
              {state === "idle" && (
                <label className="mt-2 flex items-center gap-2 text-xs text-ink/50">
                  <input
                    type="checkbox"
                    checked={cameraEnabled}
                    onChange={(e) => setCameraEnabled(e.target.checked)}
                  />
                  Record video for body-language feedback (eye contact, posture, gestures)
                </label>
              )}
              {cameraError && (
                <p className="mt-2 text-xs text-amber-700">{cameraError}</p>
              )}
            </div>
          )}

          <div className="flex items-center gap-3 mb-6">
            <MiniWaveform tone={state === "recording" && isPausing ? "hesitant" : "steady"} />
            <span className="font-mono text-sm text-ink/60">
              {String(Math.floor(seconds / 60)).padStart(2, "0")}:
              {String(seconds % 60).padStart(2, "0")}
            </span>
          </div>

          {state === "recording" && speechSupported && (
            <div className="mb-6 rounded-xl border border-line bg-white/60 p-4">
              <div className="flex flex-wrap items-center gap-4 mb-3">
                <span className="rounded-full bg-teal-50 px-3 py-1 text-xs font-mono text-teal-700">
                  {liveWpm || "—"} wpm
                </span>
                <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-mono text-amber-700">
                  {liveFillerCount} filler{liveFillerCount === 1 ? "" : "s"}
                </span>
                <span className="rounded-full bg-slate-50 px-3 py-1 text-xs font-mono text-slate-600">
                  {livePauseCount} pause{livePauseCount === 1 ? "" : "s"}
                </span>
                {isPausing && (
                  <span className="text-xs font-mono text-teal-600 animate-pulse">
                    pausing…
                  </span>
                )}
              </div>
              <p className="text-sm text-ink/50 italic min-h-[1.5em]">
                {liveInterim || "Listening…"}
              </p>
              <p className="text-xs text-ink/30 mt-2">
                Live preview — final numbers are computed after you submit.
              </p>
            </div>
          )}

          {state === "recording" && !speechSupported && (
            <p className="text-xs text-ink/40 mb-6">
              Live preview isn't available in this browser (try Chrome or Edge). Your
              recording will still be fully analyzed after you submit.
            </p>
          )}

          {errorMsg && (
            <p className="text-sm text-red-600 mb-4" role="alert">{errorMsg}</p>
          )}

          <div className="flex flex-wrap gap-3">
            {state === "idle" && <Button onClick={startRecording}>Start recording</Button>}
            {state === "recording" && (
              <Button variant="secondary" onClick={stopRecording}>Stop</Button>
            )}
            {state === "recorded" && (
              <>
                <Button onClick={submitRecording}>Submit for analysis</Button>
                <Button variant="ghost" onClick={resetSession}>Record again</Button>
              </>
            )}
            {state === "uploading" && <Button disabled>Uploading…</Button>}
            {state === "done" && (
              <p className="text-sm text-teal-700">
                Sent for analysis. See your{" "}
                <a href={lastSessionId ? `/dashboard?session=${lastSessionId}` : "/dashboard"} className="underline">
                  results on your dashboard
                </a>.
              </p>
            )}
            {state === "error" && (
              <Button variant="ghost" onClick={() => setState("idle")}>Try again</Button>
            )}
          </div>
        </Card>
      </div>
    </main>
  );
}
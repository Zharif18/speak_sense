"""
The Communication Context Engine.

Fuses: speech metrics + scenario + optional physiological stress index +
a short history of past sessions, into one prompt, and asks Gemini for
structured coaching feedback. This is the "fusion" layer described in the
project brief -- it's context engineering over an LLM, not a trained model,
which keeps it explainable and fast to iterate on during the hackathon.
"""

import os
import json
from typing import Optional, List, Dict, Any

import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))

SYSTEM_PROMPT = """You are SpeakSense's communication coach. You coach students who
may have social anxiety, stuttering, or low speaking confidence. Your tone is warm,
specific, and never clinical -- you are not diagnosing anxiety, you are coaching
communication skills using the data provided.

Rules:
- Never claim to detect or diagnose anxiety, stress, or any medical condition.
- If physiological data is present, describe it as "context" (e.g. "your heart rate
  was higher than your baseline during this session"), never as a measurement of
  the user's internal state.
- The physiological context includes a "confidence" (0-1) on the heart-rate signal
  itself -- it's discounted when nothing in the session's speech backs it up, or
  when the heart-rate trace looked noisy (a common false-positive from wrist
  sensors). If confidence is below ~0.5, don't lead with the heart-rate reading or
  state it as a fact -- either skip it or mention it only as a minor, uncertain
  aside ("there was a brief heart-rate uptick, though it's hard to say if that
  reflects the moment or just the sensor").
- If vocal tension data is present, describe it the same way -- as a signal about
  vocal delivery (e.g. "your voice showed more pitch instability early on"), never
  as a diagnosis of how nervous the user actually felt.
- If body-language data is present, describe it as a delivery signal too (e.g. "you
  held eye contact with the camera most of the session" or "there were a few longer
  look-aways"), never as a read on the user's emotional or mental state.
- Always lead with something specific the user did well before suggesting fixes.
- Keep tips concrete and practiceable, not generic ("pause after your intro line"
  beats "speak more slowly").
- Return ONLY valid JSON matching the schema below. No markdown, no preamble.

Schema:
{
  "summary": "2-3 sentence overview of this session",
  "strengths": ["short specific strength", "..."],
  "improvement_tips": ["short specific actionable tip", "..."],
  "confidence_score": <int 0-100, a heuristic composite of pace/fillers/pauses,
                       explained in summary, NOT a claim about the user's felt confidence>
}
"""


def build_context_payload(
    scenario_type: str,
    prompt_text: Optional[str],
    speech_metrics: Dict[str, Any],
    weighted_stress: Optional[Any],
    past_sessions: List[Dict[str, Any]],
    video_metrics: Optional[Dict[str, Any]] = None,
) -> str:
    payload = {
        "scenario_type": scenario_type,
        "prompt_given_to_user": prompt_text,
        "speech_metrics": {
            "words_per_minute": speech_metrics.get("words_per_minute"),
            "pause_count": speech_metrics.get("pause_count"),
            "avg_pause_seconds": speech_metrics.get("avg_pause_seconds"),
            "filler_word_rate_per_100_words": speech_metrics.get("filler_word_rate"),
            "repetition_count": speech_metrics.get("repetition_count"),
            "vocabulary_richness_ttr": speech_metrics.get("unique_word_ratio"),
        },
        "physiological_context": {
            "relative_stress_index": weighted_stress.stress_index,
            "raw_relative_stress_index": weighted_stress.raw_stress_index,
            "confidence": weighted_stress.confidence,
            "why": weighted_stress.reasons,
            "note": (
                "positive = heart rate above this user's personal baseline during the "
                "session; already down-weighted for corroboration/sensor-noise, see confidence"
            ),
        } if weighted_stress is not None and weighted_stress.stress_index is not None else None,
        "vocal_tension_context": {
            "nervousness_score": speech_metrics.get("nervousness_score"),
            "label": speech_metrics.get("nervousness_label"),
            "note": (
                "from an acoustic model trained on pitch/energy instability patterns "
                "in the user's voice -- a signal about vocal delivery, not a diagnosis"
            ),
        } if speech_metrics.get("nervousness_score") is not None else None,
        "body_language_context": {
            "eye_contact_percent": video_metrics.get("eye_contact_percent"),
            "eye_contact_breaks": video_metrics.get("eye_contact_breaks"),
            "posture_openness_score": video_metrics.get("posture_openness_score"),
            "gesture_rate_per_min": video_metrics.get("gesture_rate_per_min"),
            "overall_label": video_metrics.get("body_language_label"),
            "note": (
                "from face/pose landmark tracking on the session video -- a signal "
                "about on-camera delivery, not a read on how the user felt"
            ),
        } if video_metrics else None,
        "recent_session_trend": past_sessions,  # e.g. last 5 sessions' key metrics
    }
    return json.dumps(payload, indent=2)


def generate_coaching_feedback(
    scenario_type: str,
    prompt_text: Optional[str],
    speech_metrics: Dict[str, Any],
    weighted_stress: Optional[Any] = None,
    past_sessions: Optional[List[Dict[str, Any]]] = None,
    video_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    context = build_context_payload(
        scenario_type, prompt_text, speech_metrics, weighted_stress, past_sessions or [],
        video_metrics=video_metrics,
    )

    model = genai.GenerativeModel(
        model_name="gemini-3.5-flash-lite",
        system_instruction=SYSTEM_PROMPT,
        generation_config={"response_mime_type": "application/json"},
    )
    response = model.generate_content(context)

    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, AttributeError):
        # Fail soft: never break the dashboard if the model wobbles on format.
        return {
            "summary": "We couldn't generate detailed feedback for this session. "
                       "Your raw metrics are still saved below.",
            "strengths": [],
            "improvement_tips": [],
            "confidence_score": None,
        }
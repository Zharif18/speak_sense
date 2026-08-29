"""
Body-language analysis from a session's recorded video.

Uses MediaPipe's Face Mesh (for gaze/eye-contact + smile proxies) and Pose
(for posture + gesture/hand-movement proxies) on sampled frames from the
uploaded video. Everything here is deterministic, explainable signal
processing on landmark geometry -- no black-box emotion classifier, no
claims about how the user actually felt. That framing carries through to
the coaching engine and the copy shown on the dashboard.

If mediapipe/opencv aren't installed, or a face can't be found in enough
frames, this degrades gracefully (returns partial/None fields) rather than
crashing the analyze endpoint -- same pattern as nervousness_detector.py.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import cv2
    import mediapipe as mp

    _CV_AVAILABLE = True
except ImportError:
    _CV_AVAILABLE = False

# Sample at a fixed rate rather than every frame -- plenty for second-scale
# body-language signal, and much cheaper than processing 30fps video.
SAMPLE_FPS = 5

# Roughly how far (in normalized iris-offset units) the eyes can drift from
# dead-center before we count the frame as "looking away" rather than "at
# the camera." Tuned loosely; this is a coaching heuristic, not lab-grade
# gaze tracking (webcam video can't give true gaze angle without calibration).
GAZE_OFFSET_THRESHOLD = 0.045

# A look-away has to last at least this long to count as a distinct "break"
# rather than a natural blink/micro-saccade.
LOOK_AWAY_MIN_SECONDS = 0.5

# MediaPipe Face Mesh landmark indices used below.
LEFT_IRIS = [468, 469, 470, 471]
RIGHT_IRIS = [473, 474, 475, 476]
LEFT_EYE_CORNERS = (33, 133)
RIGHT_EYE_CORNERS = (362, 263)
MOUTH_CORNERS = (61, 291)
MOUTH_TOP_BOTTOM = (13, 14)
NOSE_TIP = 1


def analyze_video(video_path: str) -> Optional[Dict[str, Any]]:
    """
    Runs the full body-language pipeline on a video file and returns a
    dict matching VideoMetrics' columns, or None if OpenCV/MediaPipe
    aren't available in this environment.
    """
    if not _CV_AVAILABLE:
        return None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    source_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_interval = max(int(round(source_fps / SAMPLE_FPS)), 1)

    face_mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=True,  # needed for iris landmarks (468-477)
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    pose = mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    frame_idx = 0
    sampled = 0
    faces_found = 0

    gaze_offsets: List[float] = []       # per sampled frame with a face
    smile_ratios: List[float] = []
    torso_leans: List[float] = []        # signed horizontal shoulder-midpoint offset
    head_x_positions: List[float] = []   # nose-tip x, for head-movement jitter
    wrist_positions: List[Optional[float]] = []  # avg wrist y, None if not visible
    timeline: List[Dict[str, Any]] = []

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_idx % frame_interval != 0:
                frame_idx += 1
                continue
            frame_idx += 1
            sampled += 1

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame.shape[:2]

            face_result = face_mesh.process(rgb)
            pose_result = pose.process(rgb)

            t = round(sampled / SAMPLE_FPS, 2)
            frame_record: Dict[str, Any] = {"t": t}

            if face_result.multi_face_landmarks:
                faces_found += 1
                lm = face_result.multi_face_landmarks[0].landmark

                gaze_offset = _estimate_gaze_offset(lm)
                gaze_offsets.append(gaze_offset)
                frame_record["gaze_offset"] = round(gaze_offset, 4)

                smile_ratio = _estimate_smile_ratio(lm)
                smile_ratios.append(smile_ratio)

                head_x_positions.append(lm[NOSE_TIP].x)

            if pose_result.pose_landmarks:
                plm = pose_result.pose_landmarks.landmark
                lean = _estimate_torso_lean(plm)
                if lean is not None:
                    torso_leans.append(lean)
                    frame_record["torso_lean"] = round(lean, 4)

                wrist_y = _estimate_wrist_activity(plm)
                wrist_positions.append(wrist_y)
            else:
                wrist_positions.append(None)

            timeline.append(frame_record)
    finally:
        cap.release()
        face_mesh.close()
        pose.close()

    if sampled == 0:
        return None

    duration_seconds = sampled / SAMPLE_FPS
    face_detection_rate = round(faces_found / sampled * 100, 1)

    eye_contact_percent, eye_contact_breaks = _summarize_gaze(gaze_offsets)
    posture_openness_score, posture_variability = _summarize_posture(torso_leans)
    gesture_rate_per_min, gesture_variability = _summarize_gestures(
        wrist_positions, duration_seconds
    )
    head_movement_index = _summarize_head_movement(head_x_positions)
    smile_percent = (
        round(sum(1 for r in smile_ratios if r > 0.35) / len(smile_ratios) * 100, 1)
        if smile_ratios
        else None
    )

    label = _label_body_language(
        eye_contact_percent, posture_openness_score, gesture_variability, head_movement_index
    )

    return {
        "frames_analyzed": sampled,
        "face_detection_rate": face_detection_rate,
        "eye_contact_percent": eye_contact_percent,
        "eye_contact_breaks": eye_contact_breaks,
        "posture_openness_score": posture_openness_score,
        "posture_variability": posture_variability,
        "gesture_rate_per_min": gesture_rate_per_min,
        "gesture_variability": gesture_variability,
        "head_movement_index": head_movement_index,
        "smile_percent": smile_percent,
        "body_language_label": label,
        "raw_metrics": {"sample_fps": SAMPLE_FPS, "timeline": timeline},
    }


# ---------- per-frame geometry helpers ----------

def _estimate_gaze_offset(lm) -> float:
    """
    Rough gaze-toward-camera proxy: how far the iris center sits from the
    midpoint of its own eye corners, normalized and averaged across both
    eyes. Near 0 = eyes centered in the socket (roughly looking at the
    lens, when combined with a forward-facing head); larger = looking to a
    side/up/down.
    """
    def eye_offset(iris_idxs, corner_idxs):
        iris_x = statistics.mean(lm[i].x for i in iris_idxs)
        iris_y = statistics.mean(lm[i].y for i in iris_idxs)
        c1, c2 = lm[corner_idxs[0]], lm[corner_idxs[1]]
        mid_x = (c1.x + c2.x) / 2
        mid_y = (c1.y + c2.y) / 2
        eye_width = abs(c2.x - c1.x) or 1e-6
        return ((iris_x - mid_x) ** 2 + (iris_y - mid_y) ** 2) ** 0.5 / eye_width

    left = eye_offset(LEFT_IRIS, LEFT_EYE_CORNERS)
    right = eye_offset(RIGHT_IRIS, RIGHT_EYE_CORNERS)
    return (left + right) / 2


def _estimate_smile_ratio(lm) -> float:
    """Mouth width / mouth-corner-to-face-width proxy; higher = wider smile."""
    l, r = lm[MOUTH_CORNERS[0]], lm[MOUTH_CORNERS[1]]
    top, bottom = lm[MOUTH_TOP_BOTTOM[0]], lm[MOUTH_TOP_BOTTOM[1]]
    width = abs(r.x - l.x)
    height = abs(bottom.y - top.y) or 1e-6
    return width / height / 10  # scaled into a roughly 0-1ish working range


def _estimate_torso_lean(plm) -> Optional[float]:
    """
    Signed horizontal offset of the shoulder midpoint from the hip
    midpoint, normalized by shoulder width. ~0 = upright/centered;
    larger magnitude = leaning/slouching to one side.
    """
    try:
        ls, rs = plm[11], plm[12]  # left/right shoulder
        lh, rh = plm[23], plm[24]  # left/right hip
    except IndexError:
        return None
    if min(ls.visibility, rs.visibility, lh.visibility, rh.visibility) < 0.4:
        return None
    shoulder_mid_x = (ls.x + rs.x) / 2
    hip_mid_x = (lh.x + rh.x) / 2
    shoulder_width = abs(rs.x - ls.x) or 1e-6
    return (shoulder_mid_x - hip_mid_x) / shoulder_width


def _estimate_wrist_activity(plm) -> Optional[float]:
    """Average visible-wrist y position, used frame-to-frame to detect movement."""
    try:
        lw, rw = plm[15], plm[16]
    except IndexError:
        return None
    ys = [w.y for w in (lw, rw) if w.visibility > 0.4]
    return statistics.mean(ys) if ys else None


# ---------- aggregation helpers ----------

def _summarize_gaze(offsets: List[float]) -> tuple[Optional[float], Optional[int]]:
    if not offsets:
        return None, None
    looking_at_camera = [o <= GAZE_OFFSET_THRESHOLD for o in offsets]
    percent = round(sum(looking_at_camera) / len(looking_at_camera) * 100, 1)

    min_run = max(int(round(LOOK_AWAY_MIN_SECONDS * SAMPLE_FPS)), 1)
    breaks = 0
    run = 0
    for looking in looking_at_camera:
        if looking:
            if run >= min_run:
                breaks += 1
            run = 0
        else:
            run += 1
    if run >= min_run:
        breaks += 1
    return percent, breaks


def _summarize_posture(leans: List[float]) -> tuple[Optional[float], Optional[float]]:
    if not leans:
        return None, None
    avg_abs_lean = statistics.mean(abs(x) for x in leans)
    # Convert to a friendlier 0-100 "openness/centeredness" score --
    # smaller average lean -> higher score. Calibrated loosely for webcam
    # framing, not a biomechanical measurement.
    score = max(0.0, min(100.0, 100 - avg_abs_lean * 400))
    variability = round(statistics.pstdev(leans), 4) if len(leans) > 1 else 0.0
    return round(score, 1), variability


def _summarize_gestures(
    wrist_positions: List[Optional[float]], duration_seconds: float
) -> tuple[Optional[float], Optional[float]]:
    deltas = []
    prev = None
    for y in wrist_positions:
        if y is not None and prev is not None:
            deltas.append(abs(y - prev))
        prev = y if y is not None else prev
    if not deltas:
        return None, None

    # A "gesture event" is a frame-to-frame wrist movement above a small
    # noise floor -- counts hand movement without needing full gesture
    # classification.
    NOISE_FLOOR = 0.01
    events = sum(1 for d in deltas if d > NOISE_FLOOR)
    rate_per_min = round(events / max(duration_seconds, 1e-6) * 60, 1)
    variability = round(min(statistics.pstdev(deltas) * 50, 1.0), 3) if len(deltas) > 1 else 0.0
    return rate_per_min, variability


def _summarize_head_movement(head_x: List[float]) -> Optional[float]:
    if len(head_x) < 2:
        return None
    jitter = statistics.pstdev(head_x)
    return round(min(jitter * 20, 1.0), 3)


def _label_body_language(
    eye_contact_percent: Optional[float],
    posture_score: Optional[float],
    gesture_variability: Optional[float],
    head_movement_index: Optional[float],
) -> Optional[str]:
    if eye_contact_percent is None or posture_score is None:
        return None
    if eye_contact_percent >= 65 and posture_score >= 65:
        return "open & engaged"
    if head_movement_index is not None and head_movement_index >= 0.6:
        return "restless"
    if eye_contact_percent < 40:
        return "guarded"
    if gesture_variability is not None and gesture_variability < 0.1 and posture_score < 50:
        return "tense & still"
    return "mixed signals"

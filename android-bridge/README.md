# SpeakSense Watch Bridge (Android)

NoiseFit (and most other Indian/consumer fitness bands) don't expose a public
cloud API, so there's no way for the SpeakSense **web** app to pull heart-rate
data from it directly. What NoiseFit's own app *does* do is sync into
**Google Health Connect** on your phone (check: NoiseFit app → Settings →
Health Connect / Sync). This bridge app reads from Health Connect and pushes
normalized readings into SpeakSense's existing `/api/wearables/ingest`
endpoint -- the same endpoint `backend/app/services/wearable_adapter.py`
was already built to expect (`HealthConnectAdapter`'s docstring literally
describes this exact flow).

```
NoiseFit watch → NoiseFit app → Health Connect (on your phone)
                                        │
                                        ▼
                         SpeakSense Watch Bridge (this app)
                                        │  POST /api/wearables/ingest
                                        ▼
                          SpeakSense backend (FastAPI)
```

Readings are posted **without** a `session_id` (just `user_id` + timestamp).
When you finish a recording in the web app, it calls
`POST /api/wearables/session/{id}/claim`, which sweeps up any untagged
readings that fall inside that session's time window and links them. That
means this bridge app never needs to know about web sessions at all -- it
just keeps Health Connect and the backend in sync in the background.

## What it reads

- **Heart rate** (`HeartRateRecord`) → posted as `metric_type: "heart_rate"`.
- **Steps** (`StepsRecord`), bucketed per-minute → posted as
  `metric_type: "motion_index"`. This is a rough proxy for wrist motion
  (Health Connect doesn't expose raw accelerometer data to apps), used by
  the backend's weighting engine to help tell a real stress spike apart
  from a motion artifact on the optical HR sensor.

## Setup

1. **Install Health Connect** on your phone if it isn't already there
   (Android 14+ has it built in; older versions get it from the Play Store).
2. **Open the NoiseFit app → Settings → and enable syncing to Health Connect**
   (exact wording varies by NoiseFit app version — look for "Health Connect"
   or "Sync with other apps"). Give it a few minutes after a watch sync for
   heart-rate data to actually appear in Health Connect.
3. **Open this project in Android Studio** (`File → Open` → select this
   `android-bridge` folder). Let Gradle sync.
4. In `app/src/main/java/com/speaksense/bridge/MainActivity.kt`, confirm
   `DEFAULT_API_BASE` and `DEMO_USER_ID` — `DEMO_USER_ID` must match the
   same value as `frontend/lib/constants.ts` (`00000000-0000-0000-0000-000000000001`
   for the seeded demo user, or your real user's id once auth exists).
5. Build & run on your phone (not an emulator — Health Connect needs a real
   device with the NoiseFit app installed and syncing).
6. On first launch, tap **Grant permissions** and allow read access to heart
   rate and steps.
7. Set the **API base URL** to your deployed backend
   (`https://speaksense-backend.onrender.com`) or `http://<your-computer's-LAN-IP>:8000`
   for local testing — `http://localhost:8000` won't resolve from a phone.
8. Tap **Sync now** before/after a practice session, or leave "Auto-sync every
   15 min" on (uses WorkManager) so readings are already flowing in by the
   time you record.

## Notes / limitations

- This is a **read-only, one-way bridge** — it never writes to Health Connect
  or to NoiseFit, only reads and forwards.
- Health Connect only shares what NoiseFit chooses to write to it, at
  whatever granularity NoiseFit chooses to write it at. If your NoiseFit app
  only syncs heart rate every few minutes (rather than continuously), that's
  a NoiseFit-side limitation, not something this bridge can improve.
- `motion_index` here is a coarse steps-per-minute proxy, not a real
  accelerometer signal — treat it (and the backend's use of it) as a
  heuristic, not a precise motion measurement.

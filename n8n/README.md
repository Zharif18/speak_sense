# n8n integration

SpeakSense's backend POSTs a small recap payload to an n8n Webhook after
coaching feedback is generated for a session (see
`backend/app/services/n8n_notify.py`, called from
`backend/app/routers/coaching.py`). n8n owns everything that happens after
that — a Slack message, an email, a logged row — the backend doesn't know or
care.

## 1. Get n8n running

Easiest for a hackathon is n8n's cloud trial (n8n.cloud) — no install needed.
To self-host instead:

```bash
docker run -it --rm -p 5678:5678 n8nio/n8n
```

Open `http://localhost:5678` and create an owner account.

## 2. Import the starter workflow

In the n8n editor: **Workflows → Import from File** → select
`n8n/speaksense-recap-workflow.json` from this repo.

It comes with:
- A **Webhook** node listening for `POST` requests
- A **Set** node that builds a human-readable `recap_message` from the
  payload
- A sticky note marking where to add a real Slack/Email/Sheets node

## 3. Activate it and copy the webhook URL

Click the **Webhook** node → copy the **Production URL** (looks like
`https://your-instance.app.n8n.cloud/webhook/speaksense`). Toggle the
workflow **Active** in the top right.

## 4. Point the backend at it

In `backend/.env`:

```
N8N_WEBHOOK_URL=https://your-instance.app.n8n.cloud/webhook/speaksense
```

Restart the backend. Every time `/api/coaching/generate` runs successfully,
n8n receives:

```json
{
  "session_id": "...",
  "user_id": "...",
  "scenario_type": "interview",
  "confidence_score": 74,
  "summary": "...",
  "filler_word_rate": 3.1,
  "words_per_minute": 128
}
```

## 5. Extend it

Delete the sticky note and wire in a real destination node, using
`{{$json.recap_message}}` or any raw field from the payload:
- **Slack** node → post to a `#speaksense-demo` channel for the judges
- **Send Email** node → recap to the student
- **Google Sheets** node → append a row, giving you a free coach-facing
  spreadsheet dashboard with zero extra code

If the webhook is unreachable, the backend logs a warning and continues —
an n8n outage never breaks session analysis or the API response.

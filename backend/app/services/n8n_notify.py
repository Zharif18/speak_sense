"""
n8n integration.

After coaching feedback is generated for a session, we POST a recap payload
to an n8n Webhook node. From there, n8n owns the workflow entirely -- e.g.
send a recap email, post to Slack, log to a sheet, sync wearable data on a
schedule. The backend does not know or care what n8n does with the payload;
that decoupling is the point of using a workflow tool here instead of
hardcoding notification logic into the API.

Import n8n/speaksense-recap-workflow.json into your n8n instance to get a
working starting workflow (Webhook -> Set -> Slack/Email placeholder).
"""

import os
import logging
import httpx

logger = logging.getLogger("speaksense.n8n")

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")


async def notify_session_analyzed(payload: dict) -> None:
    """
    Fire-and-forget style notification. Failures are logged, never raised --
    an n8n outage should never break session analysis or the API response.
    """
    if not N8N_WEBHOOK_URL:
        logger.info("N8N_WEBHOOK_URL not set; skipping n8n notification.")
        return

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(N8N_WEBHOOK_URL, json=payload)
            response.raise_for_status()
            logger.info("n8n notified for session %s", payload.get("session_id"))
    except httpx.HTTPError as exc:
        logger.warning("n8n notification failed: %s", exc)

import os

from dotenv import load_dotenv

# Must run before any other app module reads os.getenv(...) for config
# (database URL, GEMINI_API_KEY, WOLFRAM_APP_ID, etc.) -- otherwise every
# one of those calls silently falls back to its hardcoded default instead
# of what's actually in .env.
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import sessions, speech, video, wearables, coaching, vocabulary, search

# Comma-separated list, e.g. "http://localhost:3000,https://speaksense-frontend.onrender.com"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

# Creates tables on boot for local/dev use. In production, use Alembic
# migrations instead (see backend/alembic/).
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SpeakSense API",
    description="AI communication coach: speech analysis + wearable context + personalized coaching.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(speech.router, prefix="/api/speech", tags=["speech"])
app.include_router(video.router, prefix="/api/video", tags=["video"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(wearables.router, prefix="/api/wearables", tags=["wearables"])
app.include_router(coaching.router, prefix="/api/coaching", tags=["coaching"])
app.include_router(vocabulary.router, prefix="/api/vocabulary", tags=["vocabulary"])


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "speaksense-api"}
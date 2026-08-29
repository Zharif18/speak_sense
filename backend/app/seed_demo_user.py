"""
Creates one fixed demo user so the frontend can record sessions before real
auth exists. speaking_sessions.user_id has a FK to users.id -- without a row
here, every session insert fails with "invalid input syntax for type uuid"
(or a FK violation once the id is a valid UUID).

Run once after setting up the database:
    python -m app.seed_demo_user

Safe to run multiple times -- it no-ops if the demo user already exists.
"""

from app.database import SessionLocal, Base, engine
from app.models import User

# Fixed UUID so the frontend can hardcode it too -- must match
# DEMO_USER_ID in frontend/lib/constants.ts (or wherever you put it).
DEMO_USER_ID = "00000000-0000-0000-0000-000000000001"
DEMO_USER_EMAIL = "demo@speaksense.local"


def seed_demo_user():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.id == DEMO_USER_ID).first()
        if existing:
            print(f"Demo user already exists: {existing.id} ({existing.email})")
            return

        user = User(
            id=DEMO_USER_ID,
            email=DEMO_USER_EMAIL,
            name="Demo User",
            # Not a real login path yet -- placeholder until auth is built.
            hashed_password="not-a-real-hash",
        )
        db.add(user)
        db.commit()
        print(f"Created demo user: {DEMO_USER_ID}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_user()
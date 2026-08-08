from fastapi import APIRouter, Depends
from backend.app.core.auth import get_current_user
from backend.app.core.logging import logger
from backend.app.db.firestore import firestore_db

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user profile. Upserts profile in Firestore on login."""
    user_id = current_user["uid"]
    email = current_user.get("email", "")
    name = current_user.get("name", email.split("@")[0] if email else "User")
    picture = current_user.get("picture", "")
    profile = {"uid": user_id, "email": email, "name": name, "picture": picture}
    firestore_db.save_user_profile(user_id, profile)
    logger.info(f"[Auth] Authenticated: uid={user_id} email={email}")
    return profile

"""
Backend auth dependency using google.oauth2.id_token directly.

This approach bypasses firebase_admin entirely for token verification:
- firebase_admin requires credentials (ADC/service-account) for initialization
- google.oauth2.id_token.verify_firebase_token ONLY needs the project ID
- It fetches Google's JWKS from a public URL — zero credentials required
- Works on any hosting platform (Railway, Fly, Render, etc.)
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import firebase_admin
from firebase_admin import auth as firebase_auth

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from backend.app.core.config import settings
from backend.app.core.logging import logger

# HTTPBearer scheme -- expects: Authorization: Bearer <token>
_bearer_scheme = HTTPBearer(auto_error=False)

# One shared transport for the lifetime of the process
_google_request = google_requests.Request()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """
    FastAPI dependency that verifies a Firebase Google OAuth ID Token.

    Uses google.oauth2.id_token.verify_firebase_token which:
    - Fetches Firebase's public JWKS from a public Google endpoint (no credentials)
    - Verifies the JWT signature cryptographically
    - Validates aud == FIREBASE_PROJECT_ID and iss claims
    - Works on Railway/any cloud without ADC or service account keys

    Returns decoded token claims dict with uid, email, name, picture.
    Raises HTTP 401 for missing, expired, or tampered tokens.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Include Authorization: Bearer <firebase_id_token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = credentials.credentials

    try:
        # Directly verify via Google's public JWKS — no firebase_admin credentials needed
        decoded = google_id_token.verify_firebase_token(
            raw_token,
            _google_request,
            audience=settings.FIREBASE_PROJECT_ID,
        )
        # Normalize 'uid' field — raw Google JWT claims contain 'user_id' or 'sub',
        # whereas Firebase Admin SDK sets 'uid'. Downstream endpoints expect 'uid'.
        if "uid" not in decoded or not decoded["uid"]:
            decoded["uid"] = decoded.get("user_id") or decoded.get("sub") or "anonymous_user"
        return decoded

    except ValueError as e:
        # Invalid token format, expired, wrong audience, or signature mismatch
        logger.warning(f"[Auth] Invalid Firebase token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"[Auth] Unexpected token verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

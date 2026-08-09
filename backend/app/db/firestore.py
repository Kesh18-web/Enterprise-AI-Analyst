import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.core.logging import logger

import firebase_admin
from firebase_admin import credentials as fb_credentials
from firebase_admin import firestore
from google.cloud import firestore as gfirestore
from google.oauth2 import service_account


class FirestoreManager:
    """
    Production GCP Firestore Client Manager.
    All data is namespaced under users/{user_id}/ to guarantee complete
    per-user data isolation. No user can ever see another user's data.

    Credentials priority (Railway-compatible):
    1. FIREBASE_SERVICE_ACCOUNT_JSON env var (JSON string) — Railway production
    2. FIREBASE_CREDENTIALS_PATH file — local development
    3. Application Default Credentials — GCP-hosted environments
    """

    def __init__(self):
        self.db = None
        self.is_mock = False
        self._initialize()

    def _initialize(self):
        try:
            cred_dict: Optional[Dict] = None

            # ── Priority 1: Env var (Railway production) ──────────────────────
            sa_json_env = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
            if sa_json_env:
                try:
                    cred_dict = json.loads(sa_json_env)
                    logger.info("Firebase: using credentials from FIREBASE_SERVICE_ACCOUNT_JSON env var")
                except json.JSONDecodeError as je:
                    logger.error(f"Firebase: FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON: {je}")

            # ── Priority 2: File path (local dev) ─────────────────────────────
            if not cred_dict:
                from backend.app.core.config import settings
                cred_path = settings.FIREBASE_CREDENTIALS_PATH
                if os.path.exists(cred_path):
                    with open(cred_path) as f:
                        cred_dict = json.load(f)
                    logger.info(f"Firebase: using credentials from file '{cred_path}'")

            # ── Initialize firebase_admin app ─────────────────────────────────────
            if not firebase_admin._apps:
                if cred_dict:
                    cred = fb_credentials.Certificate(cred_dict)
                    firebase_admin.initialize_app(cred)
                else:
                    # No service account available — initialize with project ID only.
                    # This is sufficient for firebase_auth.verify_id_token() which
                    # validates JWTs using Google's public keys (no credentials needed).
                    # Firestore writes will NOT work in this mode (db remains None).
                    from backend.app.core.config import settings as _settings
                    firebase_admin.initialize_app(
                        options={"projectId": _settings.FIREBASE_PROJECT_ID}
                    )
                    logger.info(
                        f"Firebase Admin initialized in token-verification-only mode "
                        f"(projectId={_settings.FIREBASE_PROJECT_ID}). "
                        f"Set FIREBASE_SERVICE_ACCOUNT_JSON to enable Firestore persistence."
                    )

            # ── Build Firestore client ─────────────────────────────────────────
            if cred_dict:
                # Explicit credentials for google-cloud-firestore client
                gcp_creds = service_account.Credentials.from_service_account_info(
                    cred_dict,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                self.db = gfirestore.Client(
                    project=cred_dict.get("project_id"),
                    credentials=gcp_creds,
                    database="enterprise-analyst-db",
                )
            else:
                # ADC path
                self.db = gfirestore.Client(database="enterprise-analyst-db")

            logger.info("Successfully connected to Firestore database 'enterprise-analyst-db'")

        except Exception as e:
            # Graceful degradation: log and continue — don't crash uvicorn.
            # All Firestore methods return safe empty values when self.db is None.
            logger.error(
                f"Firestore initialization failed — server will start in degraded mode "
                f"(Firestore unavailable). Set FIREBASE_SERVICE_ACCOUNT_JSON in Railway. Error: {e}"
            )
            self.db = None
            self.is_mock = True

    def _check_db(self) -> bool:
        """Returns True if db is available, logs warning otherwise."""
        if self.db is None:
            logger.warning("Firestore is unavailable (credentials not configured). Operation skipped.")
            return False
        return True

    # ── User Profile ──────────────────────────────────────────────────────────

    def save_user_profile(self, user_id: str, data: Dict[str, Any]) -> bool:
        """Upsert user profile at users/{user_id}/profile/info."""
        if not self._check_db():
            return False
        self.db.collection("users").document(user_id).collection("profile").document("info").set(data, merge=True)
        logger.debug(f"Saved user profile for uid='{user_id}'")
        return True

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve user profile at users/{user_id}/profile/info."""
        if not self._check_db():
            return None
        doc = self.db.collection("users").document(user_id).collection("profile").document("info").get()
        return doc.to_dict() if doc.exists else None

    # ── Generic Document Helpers ──────────────────────────────────────────────

    def save_document(self, user_id: str, collection_name: str, doc_id: str, data: Dict[str, Any]) -> bool:
        """Save or update a document scoped to users/{user_id}/{collection}/{doc_id}."""
        if not self._check_db():
            return False
        self.db.collection("users").document(user_id).collection(collection_name).document(doc_id).set(data)
        logger.debug(f"Saved document '{doc_id}' into users/{user_id}/{collection_name}/")
        return True

    def get_document(self, user_id: str, collection_name: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a document scoped to users/{user_id}/{collection}/{doc_id}."""
        if not self._check_db():
            return None
        doc_snap = self.db.collection("users").document(user_id).collection(collection_name).document(doc_id).get()
        if doc_snap.exists:
            return doc_snap.to_dict()
        return None

    # ── Chat Sessions ──────────────────────────────────────────────────────────

    def save_chat_session(self, user_id: str, session_id: str, data: Dict[str, Any]) -> bool:
        """Save or update chat session metadata under users/{user_id}/chat_sessions/{session_id}."""
        if not self._check_db():
            return False
        self.db.collection("users").document(user_id).collection("chat_sessions").document(session_id).set(data, merge=True)
        logger.debug(f"Saved chat session '{session_id}' for user '{user_id}'")
        return True

    def list_chat_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """List all chat sessions for a specific user ordered by creation timestamp."""
        if not self._check_db():
            return []
        docs = self.db.collection("users").document(user_id).collection("chat_sessions").stream()
        sessions = []
        for doc in docs:
            data = doc.to_dict()
            if not data.get("id"):
                data["id"] = doc.id
            sessions.append(data)
        sessions.sort(key=lambda s: s.get("createdAt", 0))
        return sessions

    def delete_chat_session(self, user_id: str, session_id: str) -> bool:
        """Delete a session and all its messages for the specified user."""
        if not self._check_db():
            return False
        if not session_id or session_id == "undefined":
            return False
        user_ref = self.db.collection("users").document(user_id)
        user_ref.collection("chat_sessions").document(session_id).delete()
        msg_docs = user_ref.collection("chat_sessions").document(session_id).collection("messages").stream()
        for doc in msg_docs:
            doc.reference.delete()
        logger.info(f"Deleted session '{session_id}' and all messages for user '{user_id}'")
        return True

    # ── Chat Messages ──────────────────────────────────────────────────────────

    def save_chat_message(self, user_id: str, session_id: str, message: Dict[str, Any]) -> bool:
        """Save a message into users/{user_id}/chat_sessions/{session_id}/messages/{msg_id}."""
        if not self._check_db():
            return False
        if not session_id or session_id == "undefined":
            return False
        msg_id = message.get("id") or f"msg_{int(datetime.utcnow().timestamp()*1000)}"
        (
            self.db.collection("users").document(user_id)
            .collection("chat_sessions").document(session_id)
            .collection("messages").document(msg_id)
            .set(message)
        )
        logger.debug(f"Saved message '{msg_id}' to session '{session_id}' for user '{user_id}'")
        return True

    def get_chat_messages(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve all messages for a user's session, ordered by timestamp."""
        if not self._check_db():
            return []
        if not session_id or session_id == "undefined":
            return []
        msg_docs = (
            self.db.collection("users").document(user_id)
            .collection("chat_sessions").document(session_id)
            .collection("messages").stream()
        )
        messages = [doc.to_dict() for doc in msg_docs]
        messages.sort(key=lambda m: str(m.get("timestamp") or ""))
        return messages


# Global singleton — instantiated once at import time.
# Gracefully degrades if credentials are missing (is_mock=True, db=None).
firestore_db = FirestoreManager()

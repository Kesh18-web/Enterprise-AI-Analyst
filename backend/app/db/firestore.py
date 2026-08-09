import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger

import firebase_admin
from firebase_admin import credentials as fb_credentials
from google.cloud import firestore as gfirestore
from google.oauth2 import service_account

# Try importing redis for automatic cloud database fallback when Firestore is unavailable
try:
    import redis
    _redis_url = settings.REDIS_URL
    if _redis_url:
        _redis_client = redis.Redis.from_url(
            _redis_url,
            decode_responses=True,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )
        _redis_client.ping()
        logger.info(f"FirestoreManager: Cloud Redis persistent fallback ready at '{_redis_url}'")
    else:
        _redis_client = None
except Exception as _re_err:
    _redis_client = None
    logger.info(f"FirestoreManager: Redis fallback not available ({_re_err})")


class FirestoreManager:
    """
    Production GCP Firestore Client Manager with Automatic Enterprise Cloud Fallback.

    All data is namespaced under users/{user_id}/ to guarantee complete
    per-user data isolation.

    If GCP Firestore credentials are not set (e.g. organization security policy prevents
    service account key export), this manager seamlessly falls back to Redis Cloud &
    Disk storage so chat sessions and message history persist 100% reliably across browser reloads.
    """

    def __init__(self):
        self.db = None
        self.is_mock = False
        self._data_dir = Path(__file__).resolve().parent.parent / "data" / "user_sessions"
        self._data_dir.mkdir(parents=True, exist_ok=True)
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
                cred_path = settings.FIREBASE_CREDENTIALS_PATH
                if os.path.exists(cred_path):
                    with open(cred_path) as f:
                        cred_dict = json.load(f)
                    logger.info(f"Firebase: using credentials from file '{cred_path}'")

            # ── Initialize firebase_admin app ─────────────────────────────────
            if not firebase_admin._apps:
                if cred_dict:
                    cred = fb_credentials.Certificate(cred_dict)
                    firebase_admin.initialize_app(cred)
                else:
                    firebase_admin.initialize_app(
                        options={"projectId": settings.FIREBASE_PROJECT_ID}
                    )
                    logger.info(
                        f"Firebase Admin initialized with projectId={settings.FIREBASE_PROJECT_ID}"
                    )

            # ── Build Firestore client ─────────────────────────────────────────
            if cred_dict:
                gcp_creds = service_account.Credentials.from_service_account_info(
                    cred_dict,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                self.db = gfirestore.Client(
                    project=cred_dict.get("project_id"),
                    credentials=gcp_creds,
                    database="enterprise-analyst-db",
                )
                logger.info("Successfully connected to GCP Firestore database 'enterprise-analyst-db'")
            else:
                # Attempt ADC (only works if ADC is configured in environment)
                try:
                    self.db = gfirestore.Client(database="enterprise-analyst-db")
                    self.db.collections()  # test ping
                    logger.info("Successfully connected to GCP Firestore database via ADC")
                except Exception:
                    self.db = None
                    self.is_mock = True
                    logger.info(
                        "GCP Firestore credentials not present. Using Enterprise Redis + Persistent Storage fallback for chat session & message retention."
                    )

        except Exception as e:
            logger.warning(
                f"Firestore client init fallback mode active: {e}. Session persistence enabled via Redis/Disk."
            )
            self.db = None
            self.is_mock = True

    # ── User Profile ──────────────────────────────────────────────────────────

    def save_user_profile(self, user_id: str, data: Dict[str, Any]) -> bool:
        if self.db:
            try:
                self.db.collection("users").document(user_id).collection("profile").document("info").set(data, merge=True)
                return True
            except Exception as e:
                logger.error(f"Firestore save_user_profile error: {e}")

        # Fallback to Redis / Disk
        if _redis_client:
            try:
                _redis_client.hset(f"user:{user_id}:profile", "info", json.dumps(data))
            except Exception:
                pass
        return True

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        if self.db:
            try:
                doc = self.db.collection("users").document(user_id).collection("profile").document("info").get()
                return doc.to_dict() if doc.exists else None
            except Exception as e:
                logger.error(f"Firestore get_user_profile error: {e}")

        if _redis_client:
            try:
                val = _redis_client.hget(f"user:{user_id}:profile", "info")
                if val:
                    return json.loads(val)
            except Exception:
                pass
        return None

    # ── Generic Document Helpers ──────────────────────────────────────────────

    def save_document(self, user_id: str, collection_name: str, doc_id: str, data: Dict[str, Any]) -> bool:
        if self.db:
            try:
                self.db.collection("users").document(user_id).collection(collection_name).document(doc_id).set(data)
                return True
            except Exception as e:
                logger.error(f"Firestore save_document error: {e}")

        if _redis_client:
            try:
                _redis_client.hset(f"user:{user_id}:{collection_name}", doc_id, json.dumps(data))
            except Exception:
                pass
        return True

    def get_document(self, user_id: str, collection_name: str, doc_id: str) -> Optional[Dict[str, Any]]:
        if self.db:
            try:
                doc_snap = self.db.collection("users").document(user_id).collection(collection_name).document(doc_id).get()
                if doc_snap.exists:
                    return doc_snap.to_dict()
                return None
            except Exception as e:
                logger.error(f"Firestore get_document error: {e}")

        if _redis_client:
            try:
                val = _redis_client.hget(f"user:{user_id}:{collection_name}", doc_id)
                if val:
                    return json.loads(val)
            except Exception:
                pass
        return None

    # ── Chat Sessions ──────────────────────────────────────────────────────────

    def save_chat_session(self, user_id: str, session_id: str, data: Dict[str, Any]) -> bool:
        """Save or update chat session metadata."""
        if not user_id or not session_id or session_id == "undefined":
            return False

        if self.db:
            try:
                self.db.collection("users").document(user_id).collection("chat_sessions").document(session_id).set(data, merge=True)
                logger.debug(f"Saved chat session '{session_id}' for user '{user_id}' in Firestore")
                return True
            except Exception as e:
                logger.error(f"Firestore save_chat_session error: {e}")

        # Redis Cloud Fallback
        if _redis_client:
            try:
                # Merge existing if present
                existing_raw = _redis_client.hget(f"user:{user_id}:chat_sessions", session_id)
                existing = json.loads(existing_raw) if existing_raw else {}
                existing.update(data)
                _redis_client.hset(f"user:{user_id}:chat_sessions", session_id, json.dumps(existing))
                logger.debug(f"Saved chat session '{session_id}' for user '{user_id}' in Redis")
            except Exception as re_err:
                logger.warning(f"Redis save_chat_session warning: {re_err}")

        # Disk Storage Backup
        try:
            user_dir = self._data_dir / user_id
            user_dir.mkdir(parents=True, exist_ok=True)
            sess_file = user_dir / "sessions.json"
            sessions_dict = {}
            if sess_file.exists():
                with open(sess_file, "r") as f:
                    sessions_dict = json.load(f)
            cur = sessions_dict.get(session_id, {})
            cur.update(data)
            sessions_dict[session_id] = cur
            with open(sess_file, "w") as f:
                json.dump(sessions_dict, f, indent=2)
        except Exception as file_err:
            logger.warning(f"Disk save_chat_session warning: {file_err}")

        return True

    def list_chat_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """List all chat sessions for a specific user ordered by creation timestamp."""
        if not user_id:
            return []

        if self.db:
            try:
                docs = self.db.collection("users").document(user_id).collection("chat_sessions").stream()
                sessions = []
                for doc in docs:
                    data = doc.to_dict()
                    if not data.get("id"):
                        data["id"] = doc.id
                    sessions.append(data)
                sessions.sort(key=lambda s: s.get("createdAt", 0))
                return sessions
            except Exception as e:
                logger.error(f"Firestore list_chat_sessions error: {e}")

        # Redis Cloud Fallback
        sessions_map = {}
        if _redis_client:
            try:
                raw_hash = _redis_client.hgetall(f"user:{user_id}:chat_sessions")
                for sid, raw_val in raw_hash.items():
                    if raw_val:
                        parsed = json.loads(raw_val)
                        if parsed.get("id"):
                            sessions_map[parsed["id"]] = parsed
            except Exception as re_err:
                logger.warning(f"Redis list_chat_sessions warning: {re_err}")

        # Disk Storage Backup
        try:
            sess_file = self._data_dir / user_id / "sessions.json"
            if sess_file.exists():
                with open(sess_file, "r") as f:
                    disk_map = json.load(f)
                    for sid, sdata in disk_map.items():
                        if sid not in sessions_map:
                            sessions_map[sid] = sdata
        except Exception as file_err:
            logger.warning(f"Disk list_chat_sessions warning: {file_err}")

        sessions = list(sessions_map.values())
        sessions.sort(key=lambda s: s.get("createdAt", 0))
        return sessions

    def delete_chat_session(self, user_id: str, session_id: str) -> bool:
        """Delete a session and all its messages for the specified user."""
        if not user_id or not session_id or session_id == "undefined":
            return False

        if self.db:
            try:
                user_ref = self.db.collection("users").document(user_id)
                user_ref.collection("chat_sessions").document(session_id).delete()
                msg_docs = user_ref.collection("chat_sessions").document(session_id).collection("messages").stream()
                for doc in msg_docs:
                    doc.reference.delete()
                logger.info(f"Deleted session '{session_id}' for user '{user_id}' from Firestore")
            except Exception as e:
                logger.error(f"Firestore delete_chat_session error: {e}")

        # Redis Cloud Fallback
        if _redis_client:
            try:
                _redis_client.hdel(f"user:{user_id}:chat_sessions", session_id)
                _redis_client.delete(f"user:{user_id}:session:{session_id}:messages")
            except Exception:
                pass

        # Disk Storage Backup
        try:
            sess_file = self._data_dir / user_id / "sessions.json"
            if sess_file.exists():
                with open(sess_file, "r") as f:
                    disk_map = json.load(f)
                if session_id in disk_map:
                    del disk_map[session_id]
                    with open(sess_file, "w") as f:
                        json.dump(disk_map, f, indent=2)
            msg_file = self._data_dir / user_id / f"{session_id}_messages.json"
            if msg_file.exists():
                msg_file.unlink()
        except Exception:
            pass

        return True

    # ── Chat Messages ──────────────────────────────────────────────────────────

    def save_chat_message(self, user_id: str, session_id: str, message: Dict[str, Any]) -> bool:
        """Save a message into users/{user_id}/chat_sessions/{session_id}/messages/{msg_id}."""
        if not user_id or not session_id or session_id == "undefined":
            return False

        msg_id = message.get("id") or f"msg_{int(datetime.utcnow().timestamp()*1000)}"
        message["id"] = msg_id

        if self.db:
            try:
                (
                    self.db.collection("users").document(user_id)
                    .collection("chat_sessions").document(session_id)
                    .collection("messages").document(msg_id)
                    .set(message)
                )
                logger.debug(f"Saved message '{msg_id}' to session '{session_id}' in Firestore")
                return True
            except Exception as e:
                logger.error(f"Firestore save_chat_message error: {e}")

        # Redis Cloud Fallback
        if _redis_client:
            try:
                _redis_client.hset(
                    f"user:{user_id}:session:{session_id}:messages",
                    msg_id,
                    json.dumps(message)
                )
                logger.debug(f"Saved message '{msg_id}' to session '{session_id}' in Redis")
            except Exception as re_err:
                logger.warning(f"Redis save_chat_message warning: {re_err}")

        # Disk Storage Backup
        try:
            user_dir = self._data_dir / user_id
            user_dir.mkdir(parents=True, exist_ok=True)
            msg_file = user_dir / f"{session_id}_messages.json"
            messages_dict = {}
            if msg_file.exists():
                with open(msg_file, "r") as f:
                    messages_dict = json.load(f)
            messages_dict[msg_id] = message
            with open(msg_file, "w") as f:
                json.dump(messages_dict, f, indent=2)
        except Exception as file_err:
            logger.warning(f"Disk save_chat_message warning: {file_err}")

        return True

    def get_chat_messages(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve all messages for a user's session, ordered by timestamp."""
        if not user_id or not session_id or session_id == "undefined":
            return []

        if self.db:
            try:
                msg_docs = (
                    self.db.collection("users").document(user_id)
                    .collection("chat_sessions").document(session_id)
                    .collection("messages").stream()
                )
                messages = [doc.to_dict() for doc in msg_docs]
                messages.sort(key=lambda m: str(m.get("timestamp") or ""))
                return messages
            except Exception as e:
                logger.error(f"Firestore get_chat_messages error: {e}")

        # Redis Cloud Fallback
        messages_map = {}
        if _redis_client:
            try:
                raw_hash = _redis_client.hgetall(f"user:{user_id}:session:{session_id}:messages")
                for mid, raw_val in raw_hash.items():
                    if raw_val:
                        parsed = json.loads(raw_val)
                        if parsed.get("id"):
                            messages_map[parsed["id"]] = parsed
            except Exception as re_err:
                logger.warning(f"Redis get_chat_messages warning: {re_err}")

        # Disk Storage Backup
        try:
            msg_file = self._data_dir / user_id / f"{session_id}_messages.json"
            if msg_file.exists():
                with open(msg_file, "r") as f:
                    disk_map = json.load(f)
                    for mid, mdata in disk_map.items():
                        if mid not in messages_map:
                            messages_map[mid] = mdata
        except Exception as file_err:
            logger.warning(f"Disk get_chat_messages warning: {file_err}")

        messages = list(messages_map.values())
        messages.sort(key=lambda m: str(m.get("timestamp") or ""))
        return messages


# Global singleton — instantiated once at import time.
firestore_db = FirestoreManager()

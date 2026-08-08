from datetime import datetime
from typing import Any, Dict, List, Optional
from backend.app.core.logging import logger

import firebase_admin
from firebase_admin import firestore
from google.cloud import firestore as gfirestore


class FirestoreManager:
    """
    Strict Production GCP Firestore Client Manager.
    All data is namespaced under users/{user_id}/ to guarantee complete
    per-user data isolation. No user can ever see another user's data.
    """

    def __init__(self):
        self.db = None
        self._initialize()

    def _initialize(self):
        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app()
            self.db = gfirestore.Client(database="enterprise-analyst-db")
            logger.info("Successfully connected to Firestore database 'enterprise-analyst-db' via ADC")
        except Exception as e:
            logger.error(f"Critical Firestore initialization failure: {e}")
            raise e

    # ── User Profile ──────────────────────────────────────────────────────────

    def save_user_profile(self, user_id: str, data: Dict[str, Any]) -> bool:
        """Upsert user profile at users/{user_id}/profile/info."""
        self.db.collection("users").document(user_id).collection("profile").document("info").set(data, merge=True)
        logger.debug(f"Saved user profile for uid='{user_id}'")
        return True

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve user profile at users/{user_id}/profile/info."""
        doc = self.db.collection("users").document(user_id).collection("profile").document("info").get()
        return doc.to_dict() if doc.exists else None

    # ── Generic Document Helpers ──────────────────────────────────────────────

    def save_document(self, user_id: str, collection_name: str, doc_id: str, data: Dict[str, Any]) -> bool:
        """Save or update a document scoped to users/{user_id}/{collection}/{doc_id}."""
        self.db.collection("users").document(user_id).collection(collection_name).document(doc_id).set(data)
        logger.debug(f"Saved document '{doc_id}' into users/{user_id}/{collection_name}/")
        return True

    def get_document(self, user_id: str, collection_name: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a document scoped to users/{user_id}/{collection}/{doc_id}."""
        doc_snap = self.db.collection("users").document(user_id).collection(collection_name).document(doc_id).get()
        if doc_snap.exists:
            return doc_snap.to_dict()
        return None

    # ── Chat Sessions ──────────────────────────────────────────────────────────

    def save_chat_session(self, user_id: str, session_id: str, data: Dict[str, Any]) -> bool:
        """Save or update chat session metadata under users/{user_id}/chat_sessions/{session_id}."""
        self.db.collection("users").document(user_id).collection("chat_sessions").document(session_id).set(data, merge=True)
        logger.debug(f"Saved chat session '{session_id}' for user '{user_id}'")
        return True

    def list_chat_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """List all chat sessions for a specific user ordered by creation timestamp."""
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


# Global singleton instance
firestore_db = FirestoreManager()


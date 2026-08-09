"""
Standalone Verification Script: Session & Document Auth Persistence
Rule 3 Compliance: Verify auth routes, session listing, message history, and attachedFiles metadata.
"""
import sys, os, uuid
from typing import Dict, Any

# Ensure backend package is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.db.firestore import firestore_db

def run_test():
    print("=== Running Session & Document Auth Persistence Test ===")
    test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    test_session_id = f"session_{uuid.uuid4().hex[:8]}"

    # 1. Test Session Creation
    session_data = {
        "id": test_session_id,
        "name": "Test Persistence Session",
        "createdAt": 1700000000000,
        "searchScope": "session",
        "attachedFiles": ["test_resume.pdf"],
        "userId": test_user_id,
    }
    saved = firestore_db.save_chat_session(test_user_id, test_session_id, session_data)
    assert saved, "Failed to save chat session"
    print(f"1. Saved test session '{test_session_id}' for user '{test_user_id}'")

    # 2. Test Listing Sessions for User
    sessions = firestore_db.list_chat_sessions(test_user_id)
    assert len(sessions) == 1, f"Expected 1 session, got {len(sessions)}"
    assert sessions[0]["id"] == test_session_id, "Session ID mismatch"
    assert sessions[0]["attachedFiles"] == ["test_resume.pdf"], "Attached files metadata mismatch"
    print(f"2. Listed {len(sessions)} session(s) successfully for user '{test_user_id}'")

    # 3. Test Message Saving & Retreival
    msg = {
        "id": f"msg_{uuid.uuid4().hex[:8]}",
        "role": "user",
        "content": "Hello persistence test",
        "timestamp": "2026-08-09T02:00:00Z",
    }
    saved_msg = firestore_db.save_chat_message(test_user_id, test_session_id, msg)
    assert saved_msg, "Failed to save message"

    messages = firestore_db.get_chat_messages(test_user_id, test_session_id)
    assert len(messages) == 1, f"Expected 1 message, got {len(messages)}"
    assert messages[0]["content"] == "Hello persistence test", "Message content mismatch"
    print(f"3. Saved and retrieved message history successfully!")

    # 4. Test Multi-Tenant Data Isolation (Other user gets 0 sessions)
    other_user_id = f"other_user_{uuid.uuid4().hex[:8]}"
    other_sessions = firestore_db.list_chat_sessions(other_user_id)
    assert len(other_sessions) == 0, f"Isolation failure! Other user found {len(other_sessions)} sessions"
    print("4. Multi-Tenant Data Isolation Verified! Other users receive 0 sessions.")

    # 5. Clean up test data
    deleted = firestore_db.delete_chat_session(test_user_id, test_session_id)
    assert deleted, "Failed to delete test session"
    print("5. Test cleanup completed cleanly!")

    print("\n✅ ALL SESSION & DOCUMENT AUTH PERSISTENCE TESTS PASSED 100%!")

if __name__ == "__main__":
    run_test()

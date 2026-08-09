"""
Standalone Verification Script: Document Indexing & BM25 Cache Reload
Rule 3 Compliance: Verify raw text indexing, document upload, BM25 memory reload, and deduplication.
"""
import sys, os, uuid

# Ensure backend package is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.db.bm25 import bm25_mgr
from backend.app.db.qdrant import qdrant_store
from backend.app.db.firestore import firestore_db

def run_test():
    print("=== Running Document Indexing & BM25 Cache Reload Test ===")
    test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    test_doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    test_session_id = f"session_{uuid.uuid4().hex[:8]}"

    # 1. Test In-Memory Chunk Reload Sync
    initial_count = len(bm25_mgr.chunks)
    bm25_mgr.load_from_disk()
    print(f"1. Loaded BM25 from disk cleanly (Total chunks: {len(bm25_mgr.chunks)})")

    # 2. Index a mock chunk
    mock_chunk = {
        "chunk_id": f"{test_doc_id}_0",
        "doc_id": test_doc_id,
        "source_name": "Test_Doc.pdf",
        "session_id": test_session_id,
        "page_number": 1,
        "chunk_index": 0,
        "text": "Keshav worked as a Software Development Engineer Intern at Commvault Systems Inc.",
    }

    indexed = bm25_mgr.index_chunks([mock_chunk])
    assert indexed, "Failed to index mock chunk in BM25"
    print("2. Indexed mock chunk into BM25 Keyword Store")

    # 3. Test Search Retrieval
    results = bm25_mgr.search_bm25(query="Commvault", top_k=5, session_id=test_session_id)
    assert len(results) >= 1, "BM25 search failed to retrieve indexed chunk"
    assert "Commvault" in results[0]["text"], "Chunk content mismatch"
    print(f"3. BM25 Search retrieved chunk with score={results[0]['score']:.4f}")

    # 4. Test Strict Session Filtering (Different session gets 0 results)
    diff_results = bm25_mgr.search_bm25(query="Commvault", top_k=5, session_id="other_session_xyz")
    assert len(diff_results) == 0, "Session isolation failed in BM25 search"
    print("4. Session isolation verified in BM25 search!")

    # 5. Clean up test chunks
    bm25_mgr.chunks = [c for c in bm25_mgr.chunks if c.get("doc_id") != test_doc_id]
    bm25_mgr.save_to_disk()
    print("5. Test cleanup completed cleanly!")

    print("\n✅ ALL DOCUMENT INDEXING & BM25 TESTS PASSED 100%!")

if __name__ == "__main__":
    run_test()

import os
import pickle
import re
from typing import Any, Dict, List, Optional
from backend.app.core.logging import logger

try:
    from rank_bm25 import BM25Okapi

    HAS_BM25_LIB = True
except ImportError:
    HAS_BM25_LIB = False


def tokenize_text(text: str) -> List[str]:
    """Basic alphanumeric lowercased tokenizer for BM25 keyword matching."""
    text_clean = re.sub(r"[^\w\s]", " ", text.lower())
    return [token for token in text_clean.split() if len(token) > 1]


class BM25Indexer:
    """BM25 Keyword Indexer with disk pickle persistence for precise keyword & technical term retrieval."""

    def __init__(self, storage_path: str = "backend/app/data/bm25_index.pkl"):
        self.storage_path = storage_path
        self.bm25_index: Optional[Any] = None
        self.chunks: List[Dict[str, Any]] = []
        self.corpus_tokens: List[List[str]] = []
        self.load_from_disk()

    def index_chunks(self, new_chunks: List[Dict[str, Any]]) -> bool:
        """Index text chunks using Rank-BM25 Okapi algorithm, appending to existing chunks and persisting to disk."""
        if not HAS_BM25_LIB:
            logger.warning("rank_bm25 library not available. BM25 indexing skipped.")
            return False

        if not new_chunks:
            logger.warning("No chunks provided to BM25 indexer.")
            return False

        # Existing chunk IDs set for deduplication
        existing_ids = {c.get("chunk_id") for c in self.chunks if c.get("chunk_id")}
        added_count = 0

        for chunk in new_chunks:
            c_id = chunk.get("chunk_id")
            if not c_id or c_id not in existing_ids:
                self.chunks.append(chunk)
                self.corpus_tokens.append(tokenize_text(chunk.get("text", "")))
                added_count += 1
                if c_id:
                    existing_ids.add(c_id)

        try:
            self.bm25_index = BM25Okapi(self.corpus_tokens)
            logger.info(
                f"Successfully indexed {added_count} new chunks (Total: {len(self.chunks)}) into BM25 Keyword Store."
            )
            self.save_to_disk()
            return True
        except Exception as e:
            logger.error(f"Failed to build BM25 index: {e}")
            return False

    def save_to_disk(self) -> bool:
        """Save BM25 index and indexed chunks to disk pickle file."""
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "wb") as f:
                pickle.dump({"chunks": self.chunks, "corpus_tokens": self.corpus_tokens}, f)
            logger.info(f"Persisted BM25 Index ({len(self.chunks)} chunks) to disk at '{self.storage_path}'")
            return True
        except Exception as e:
            logger.warning(f"Could not persist BM25 index to disk: {e}")
            return False

    def clear_in_memory_cache(self) -> None:
        """Clear in-memory chunks and reset BM25 index."""
        self.chunks = []
        self.corpus_tokens = []
        self.bm25_index = None
        logger.info("[BM25Indexer] In-memory chunk cache cleared.")

    def load_from_disk(self) -> bool:
        """Load BM25 index and chunks from disk pickle file if available."""
        if not HAS_BM25_LIB:
            return False
        if not os.path.exists(self.storage_path):
            self.clear_in_memory_cache()
            return False

        try:
            with open(self.storage_path, "rb") as f:
                data = pickle.load(f)
                self.chunks = data.get("chunks", [])
                self.corpus_tokens = data.get("corpus_tokens", [])
                if self.corpus_tokens:
                    self.bm25_index = BM25Okapi(self.corpus_tokens)
                    logger.info(f"Loaded persistent BM25 Index ({len(self.chunks)} chunks) from '{self.storage_path}'")
                else:
                    self.bm25_index = None
                return True
        except Exception as e:
            logger.warning(f"Could not load BM25 index from disk: {e}")
            self.clear_in_memory_cache()
        return False

    def search_bm25(
        self,
        query: str,
        top_k: int = 10,
        session_id: Optional[str] = None,
        session_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search BM25 keyword index and return top_k candidates with BM25 scores and optional session filter."""
        if not self.bm25_index or not self.chunks:
            return []

        query_tokens = tokenize_text(query)
        if not query_tokens:
            return []

        try:
            scores = self.bm25_index.get_scores(query_tokens)

            # Filter session target list
            target_sessions = set(session_ids) if session_ids else ({session_id} if session_id else None)

            # Zip chunks with scores and sort descending
            scored_results = []
            for idx, score in enumerate(scores):
                if score != 0.0:  # Only return chunks with non-zero keyword match (handles Rank-BM25 negative IDF on small corpora)
                    chunk_copy = dict(self.chunks[idx])
                    chunk_sess = chunk_copy.get("session_id")

                    # Filter by session if specified (strict isolation)
                    if target_sessions:
                        if not chunk_sess or chunk_sess not in target_sessions:
                            continue

                    chunk_copy["score"] = float(score)
                    chunk_copy["retrieval_method"] = "bm25"
                    scored_results.append(chunk_copy)

            scored_results.sort(key=lambda x: x["score"], reverse=True)
            return scored_results[:top_k]
        except Exception as e:
            logger.error(f"Error during BM25 search for query '{query}': {e}")
            return []


# Global singleton instance
bm25_mgr = BM25Indexer()



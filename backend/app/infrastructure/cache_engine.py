import json
import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple
from backend.app.core.config import settings
from backend.app.core.logging import logger, logger_timer
from backend.app.infrastructure.embedding_engine import embedding_engine

# Optional Redis Client initialization
redis_client = None
HAS_REDIS = False

try:
    import redis
    if settings.REDIS_URL:
        redis_client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=0.2,
            socket_connect_timeout=0.2,
            health_check_interval=30,
            retry_on_timeout=False,
        )
        # Test ping connection
        redis_client.ping()
        HAS_REDIS = True
        logger.info(f"[Cache Engine] Successfully connected to Redis Store at '{settings.REDIS_URL}'")
except Exception as _e:
    redis_client = None
    HAS_REDIS = False
    logger.info("[Cache Engine] Redis unavailable or offline. Operating in ultra-fast Python RAM In-Memory mode.")


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute Cosine Similarity between two high-dimensional float vector embeddings."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


def _make_json_serializable(obj: Any) -> Any:
    """Recursively convert Pydantic models and complex objects into JSON primitives."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_serializable(item) for item in obj]
    return obj


def _clean_payload_for_storage(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Strip cache-classification fields from payload before writing to store.
    This prevents stale cache_type from contaminating future reads — the
    cache_type is always set at READ time, not stored at WRITE time.
    """
    clean = _make_json_serializable(payload)
    clean.pop("cache_type", None)
    clean.pop("semantic_cache_hit", None)
    clean.pop("semantic_similarity_score", None)
    return clean


class EnterpriseCacheManager:
    """
    Unified Production Enterprise Cache Manager.

    Architecture:
    - Tier 1 (Exact SHA-256 Hash): O(1) lookup keyed by query+session_id+search_scope.
    - Tier 2 (Semantic Cosine Vector >= 0.85): Scoped per session_id+search_scope to
      prevent cross-session cache contamination.

    Key design invariant:
    - cache_type is NEVER stored inside the payload blob. It is set only at READ time.
    - Semantic entries carry session_id and search_scope for isolation.
    """

    def __init__(self, similarity_threshold: float = 0.75, ttl_seconds: int = 7200):
        self.similarity_threshold = similarity_threshold
        self.ttl_seconds = ttl_seconds
        self._memory_exact_store: Dict[str, Dict[str, Any]] = {}
        self._memory_semantic_entries: List[Dict[str, Any]] = []

    def _hash_key(self, query: str, session_id: str, search_scope: str = "") -> str:
        raw_str = f"{query.strip().lower()}:{session_id}"
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def _load_semantic_entries_from_redis(self) -> List[Dict[str, Any]]:
        """Load semantic entries from Redis and sync to in-memory list."""
        if not HAS_REDIS or not redis_client:
            return self._memory_semantic_entries
        try:
            redis_data = redis_client.get("cache:semantic:entries")
            if redis_data:
                entries = json.loads(redis_data)
                self._memory_semantic_entries = entries
                return entries
        except Exception as e:
            logger.warning(f"[CacheManager] Redis semantic read fallback (1.0s timeout): {e}")
        return self._memory_semantic_entries

    def _save_semantic_entries_to_redis(self) -> None:
        """Persist in-memory semantic entries to Redis (capped at recent 50 lightweight entries to prevent network socket stalls)."""
        if not HAS_REDIS or not redis_client:
            return
        try:
            # Cap at recent 50 entries to keep network payload under 100KB
            recent = self._memory_semantic_entries[-50:]
            self._memory_semantic_entries = recent
            redis_client.set("cache:semantic:entries", json.dumps(recent), ex=self.ttl_seconds)
        except Exception as e:
            logger.warning(f"[CacheManager] Redis semantic write fallback (1.0s timeout): {e}")

    def check_cache(
        self, query: str, session_id: str, search_scope: str, trace_id: str = "N/A"
    ) -> Tuple[Optional[Dict[str, Any]], List[float]]:
        """
        Single Entry-Point Cache Evaluation.
        Returns (cached_payload, query_vector).

        Tier-1: Exact SHA-256 hash match (scoped by session_id).
        Tier-2: Semantic cosine similarity scan (scoped by session_id).

        cache_type is set HERE at read time — never read from stored payload.
        """
        if not query or not query.strip():
            return None, []

        with logger_timer("CacheManager: Unified Check", trace_id=trace_id) as log:
            # ── 1. TIER 1: Exact Hash Lookup (O(1) - ~0.1ms) ────────────────
            exact_key = self._hash_key(query, session_id, search_scope)
            if HAS_REDIS and redis_client:
                try:
                    redis_val = redis_client.get(f"cache:exact:{exact_key}")
                    if redis_val:
                        log.info(f"[CacheManager] REDIS TIER-1 EXACT HIT for query: '{query}'")
                        payload = json.loads(redis_val)
                        # Set cache classification at READ TIME — never trust stored value
                        payload["semantic_cache_hit"] = True
                        payload["cache_type"] = "exact_hash"
                        return payload, []
                except Exception as e:
                    logger.warning(f"[CacheManager] Redis exact read error: {e}")

            # Check In-Memory fallback for Exact Hash
            mem_exact = self._memory_exact_store.get(exact_key)
            if mem_exact and (time.time() - mem_exact["timestamp"] <= self.ttl_seconds):
                log.info(f"[CacheManager] RAM TIER-1 EXACT HIT for query: '{query}'")
                payload = dict(mem_exact["payload"])
                payload["semantic_cache_hit"] = True
                payload["cache_type"] = "exact_hash"
                return payload, []

            # ── 2. TIER 2: Semantic Vector Scan (Cosine Similarity >= 0.85) ───
            # Scoped to same session_id only — NO cross-session leakage!
            try:
                query_vector = embedding_engine.embed(query)
            except Exception as e:
                log.warning(f"[CacheManager] Embedding failed for query '{query}': {e}. Skipping semantic cache.")
                return None, []

            if not query_vector:
                return None, []

            now = time.time()
            best_score = 0.0
            best_entry = None

            # Load entries from Redis (always refresh from Redis for latest state)
            entries_to_scan = self._load_semantic_entries_from_redis()

            for entry in entries_to_scan:
                # Skip expired entries
                if now - entry.get("timestamp", 0) > self.ttl_seconds:
                    continue
                # ── CRITICAL: Session scope check — match any query within the SAME chat session ──
                if entry.get("session_id") != session_id:
                    continue

                score = cosine_similarity(query_vector, entry.get("vector", []))
                if score > best_score:
                    best_score = score
                    best_entry = entry

            if best_entry and best_score >= self.similarity_threshold:
                log.info(
                    f"[CacheManager] REDIS TIER-2 SEMANTIC HIT! Similarity Score={best_score:.4f} >= {self.similarity_threshold} "
                    f"| session={session_id} | scope={search_scope}"
                )
                payload = dict(best_entry["payload"])
                # Set cache classification at READ TIME
                payload["semantic_cache_hit"] = True
                payload["semantic_similarity_score"] = round(best_score, 4)
                payload["cache_type"] = "semantic_vector"

                # Promote this exact query to Tier-1 Exact Hash for future 1ms lookups
                self.store_exact_hash(query, session_id, search_scope, payload)
                return payload, query_vector

            log.info(
                f"[CacheManager] MISS. Best similarity score was {best_score:.4f} "
                f"(Threshold: {self.similarity_threshold}) | session={session_id} | scope={search_scope}"
            )
            return None, query_vector

    def store_exact_hash(self, query: str, session_id: str, search_scope: str, payload: Dict[str, Any]) -> None:
        """
        Store exact query SHA-256 hash into Tier-1 cache.
        Payload is stripped of cache classification fields before writing —
        cache_type is always set at read time, never persisted.
        """
        if not query or not payload:
            return
        clean_payload = _clean_payload_for_storage(payload)
        now = time.time()
        exact_key = self._hash_key(query, session_id, search_scope)
        self._memory_exact_store[exact_key] = {"timestamp": now, "payload": clean_payload}
        if HAS_REDIS and redis_client:
            try:
                redis_client.setex(f"cache:exact:{exact_key}", self.ttl_seconds, json.dumps(clean_payload))
                logger.info(f"[CacheManager] STORED/PROMOTED exact query hash '{exact_key[:12]}' to Tier-1 | session={session_id} | scope={search_scope}")
            except Exception as e:
                logger.warning(f"[CacheManager] Redis exact write error: {e}")

    def store_cache(
        self, query: str, query_vector: List[float], session_id: str, search_scope: str, payload: Dict[str, Any]
    ) -> None:
        """
        Store synthesized report payload into both Tier-1 (Exact Hash) and Tier-2 (Semantic Vector).
        Both stores are scoped to session_id + search_scope.
        payload is cleaned of cache classification fields before writing.
        """
        if not query or not payload:
            return

        clean_payload = _clean_payload_for_storage(payload)
        now = time.time()
        exact_key = self._hash_key(query, session_id, search_scope)

        # Ensure query_vector is present for semantic indexing
        if not query_vector:
            query_vector = embedding_engine.embed(query)

        # 1. Store Tier-1 Exact Hash (scoped)
        self._memory_exact_store[exact_key] = {"timestamp": now, "payload": clean_payload}
        if HAS_REDIS and redis_client:
            try:
                redis_client.setex(
                    f"cache:exact:{exact_key}", self.ttl_seconds, json.dumps(clean_payload)
                )
                logger.info(f"[CacheManager] STORED exact query hash '{exact_key[:12]}' | session={session_id} | scope={search_scope}")
            except Exception as e:
                logger.warning(f"[CacheManager] Redis exact write error: {e}")

        # 2. Store Tier-2 Semantic Vector Entry (scoped with session_id + search_scope)
        if query_vector:
            entry = {
                "timestamp": now,
                "vector": query_vector,
                "payload": clean_payload,
                "session_id": session_id,       # ── SCOPE FIELD ──
                "search_scope": search_scope,   # ── SCOPE FIELD ──
            }

            # Sync in-memory from Redis before appending
            self._load_semantic_entries_from_redis()
            self._memory_semantic_entries.append(entry)
            self._save_semantic_entries_to_redis()
            logger.info(f"[CacheManager] STORED semantic vector for query '{query}' | session={session_id} | scope={search_scope} | total_entries={len(self._memory_semantic_entries)}")
        else:
            logger.warning(f"[CacheManager] Skipped Tier-2 semantic store — no query_vector for '{query}'")


# Singleton Cache Manager Instance
cache_manager = EnterpriseCacheManager(similarity_threshold=0.75, ttl_seconds=7200)

# Backward-compatibility aliases for legacy references if any
retrieval_cache = cache_manager
semantic_cache = cache_manager

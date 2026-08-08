import io
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.app.core.auth import get_current_user
from backend.app.core.logging import logger
from backend.app.db.bm25 import bm25_mgr
from backend.app.db.firestore import firestore_db
from backend.app.db.qdrant import qdrant_store
from backend.app.infrastructure.embedding_engine import embedding_engine

router = APIRouter(prefix="/documents", tags=["Documents"])


class DocumentUploadRequest(BaseModel):
    title: str
    content: str
    source_name: str = "Uploaded Document"
    session_id: str = "default_session"


@router.post("/index")
async def index_document(req: DocumentUploadRequest, current_user: dict = Depends(get_current_user)):
    """Index document text content into BM25 Keyword store, Qdrant Dense Vector store, and Firestore metadata."""
    try:
        import hashlib
        user_id = current_user["uid"]
        content_hash = hashlib.sha256(req.content.encode("utf-8")).hexdigest()[:12]
        doc_id = f"doc_{content_hash}"

        # ── DEDUPLICATION CHECK ──
        existing_doc = firestore_db.get_document(user_id, "uploaded_documents", doc_id)
        if existing_doc and existing_doc.get("session_id") == req.session_id:
            logger.info(
                f"[DocumentDeduplication] Document '{req.title}' (hash={content_hash}) already indexed for session '{req.session_id}'. Skipping indexing."
            )
            return {
                "status": "skipped",
                "doc_id": doc_id,
                "title": req.title,
                "chunks_indexed": existing_doc.get("chunks_indexed", 0),
                "message": "Document already indexed for this session.",
            }

        # Basic paragraph chunking heuristic
        raw_paragraphs = [p.strip() for p in req.content.split("\n\n") if p.strip()]

        chunks: List[Dict[str, Any]] = []

        for idx, para in enumerate(raw_paragraphs):
            chunk = {
                "chunk_id": f"{doc_id}_{idx}",
                "doc_id": doc_id,
                "source_name": req.source_name,
                "session_id": req.session_id,
                "page_number": 1,
                "chunk_index": idx,
                "text": para,
            }
            chunks.append(chunk)

        if not chunks:
            raise HTTPException(status_code=400, detail="No readable text extracted from document.")

        # Generate real 384-dim semantic embeddings for all chunks
        chunk_texts = [c["text"] for c in chunks]
        embeddings = embedding_engine.embed_batch(chunk_texts)

        # 1. Index into BM25 Keyword Store
        bm25_mgr.index_chunks(chunks)

        # 2. Index into Qdrant Vector Store
        qdrant_store.upsert_chunks(
            collection_name="enterprise_documents",
            chunks=chunks,
            embeddings=embeddings,
        )

        # 3. Persist Document Metadata into GCP Firestore
        firestore_db.save_document(
            user_id=user_id,
            collection_name="uploaded_documents",
            doc_id=doc_id,
            data={
                "doc_id": doc_id,
                "title": req.title,
                "source_name": req.source_name,
                "session_id": req.session_id,
                "content_hash": content_hash,
                "chunks_indexed": len(chunks),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        logger.info(
            f"Successfully indexed document '{req.title}' ({len(chunks)} chunks) into BM25, Qdrant & Firestore"
        )
        return {
            "status": "success",
            "doc_id": doc_id,
            "title": req.title,
            "chunks_indexed": len(chunks),
        }
    except Exception as e:
        logger.error(f"Error indexing document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    session_id: str = Form("default_session"),
    current_user: dict = Depends(get_current_user),
):
    """Upload raw PDF or text document file, extract content, and index into hybrid search stores."""
    try:
        import hashlib
        user_id = current_user["uid"]
        content_bytes = await file.read()
        doc_title = title or file.filename or "Uploaded Document"
        filename_lower = (file.filename or "").lower()

        # Compute deterministic content SHA-256 hash
        content_hash = hashlib.sha256(content_bytes).hexdigest()[:12]
        doc_id = f"doc_{content_hash}"

        # ── DEDUPLICATION CHECK: Skip pipeline if file content is identical ──
        existing_doc = firestore_db.get_document(user_id, "uploaded_documents", doc_id)
        if existing_doc and (existing_doc.get("session_id") == session_id or session_id in ["global", "global_workspace"]):
            is_global = session_id in ["global", "global_workspace"]
            msg = "Document already uploaded in Global Workspace." if is_global else "Document already uploaded in this session."
            logger.info(
                f"[DocumentDeduplication] File '{file.filename}' (hash={content_hash}) already indexed for session '{session_id}'. Skipping chunking & embedding."
            )
            return {
                "status": "skipped",
                "doc_id": doc_id,
                "title": doc_title,
                "filename": file.filename,
                "chunks_indexed": existing_doc.get("chunks_indexed", 0),
                "session_id": session_id,
                "message": msg,
            }

        chunks: List[Dict[str, Any]] = []

        if filename_lower.endswith(".pdf"):
            try:
                import pypdf
                pdf_reader = pypdf.PdfReader(io.BytesIO(content_bytes))
                chunk_counter = 0

                for page_idx, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text() or ""
                    paragraphs = [p.strip() for p in page_text.split("\n\n") if p.strip()]
                    if not paragraphs and page_text.strip():
                        paragraphs = [page_text.strip()]

                    for para in paragraphs:
                        chunk = {
                            "chunk_id": f"{doc_id}_{chunk_counter}",
                            "doc_id": doc_id,
                            "source_name": file.filename or "Uploaded File",
                            "session_id": session_id,
                            "page_number": page_idx + 1,
                            "chunk_index": chunk_counter,
                            "text": para,
                        }
                        chunks.append(chunk)
                        chunk_counter += 1
            except Exception as pdf_err:
                logger.error(f"pypdf extraction failed for {file.filename}: {pdf_err}")
                raise HTTPException(status_code=400, detail=f"Failed to parse PDF file: {pdf_err}")
        else:
            # Plain text / markdown fallback
            text_content = content_bytes.decode("utf-8", errors="ignore")
            raw_paragraphs = [p.strip() for p in text_content.split("\n\n") if p.strip()]
            for idx, para in enumerate(raw_paragraphs):
                chunk = {
                    "chunk_id": f"{doc_id}_{idx}",
                    "doc_id": doc_id,
                    "source_name": file.filename or "Uploaded File",
                    "session_id": session_id,
                    "page_number": 1,
                    "chunk_index": idx,
                    "text": para,
                }
                chunks.append(chunk)

        if not chunks:
            raise HTTPException(status_code=400, detail="No readable text content extracted from file.")

        # Generate real 384-dim semantic embeddings for all chunks
        chunk_texts = [c["text"] for c in chunks]
        embeddings = embedding_engine.embed_batch(chunk_texts)

        # 1. Index into BM25 Keyword Store
        bm25_mgr.index_chunks(chunks)

        # 2. Index into Qdrant Vector Store
        qdrant_store.upsert_chunks(
            collection_name="enterprise_documents",
            chunks=chunks,
            embeddings=embeddings,
        )

        # 3. Persist Document Metadata into GCP Firestore
        firestore_db.save_document(
            user_id=user_id,
            collection_name="uploaded_documents",
            doc_id=doc_id,
            data={
                "doc_id": doc_id,
                "title": doc_title,
                "source_name": file.filename or "Uploaded File",
                "session_id": session_id,
                "content_hash": content_hash,
                "chunks_indexed": len(chunks),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        logger.info(
            f"Successfully uploaded & indexed '{doc_title}' ({len(chunks)} chunks, session={session_id}) into BM25, Qdrant & Firestore"
        )
        return {
            "status": "success",
            "doc_id": doc_id,
            "title": doc_title,
            "filename": file.filename,
            "chunks_indexed": len(chunks),
            "session_id": session_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling file upload '{file.filename}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")


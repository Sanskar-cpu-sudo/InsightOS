"""
routers/upload.py

Lets a user upload a PDF (like a company policy or report). We read
the text out of it, split it into smaller chunks, and store those
chunks in Qdrant so the Knowledge Agent can find them later.

This only needs to happen ONCE per document. After it's uploaded, it
stays searchable forever - no need to re-upload it again.
"""

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from pypdf import PdfReader
import io

from app.database import get_db
from app.vector_store import add_texts
from app.models import Document

router = APIRouter()

DEFAULT_COMPANY_ID = 1
CHUNK_SIZE = 800  # roughly how many characters go in each chunk


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Reads all the text out of a PDF file."""
    reader = PdfReader(io.BytesIO(file_bytes))
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"
    return full_text


def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE) -> list:
    """
    Splits a long piece of text into smaller pieces.
    We keep it simple: just cut every `chunk_size` characters.
    """
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size].strip()
        if chunk:  # skip empty pieces
            chunks.append(chunk)
    return chunks


@router.post("")
def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    from datetime import datetime, UTC

    file_bytes = file.file.read()

    text = extract_text_from_pdf(file_bytes)
    chunks = split_into_chunks(text)

    if not chunks:
        return {"success": False, "reason": "no_text_found_in_pdf"}

    # V2: create the Document row FIRST (before adding to Qdrant) so we
    # have a real id to use as source_id - this lets us trace any piece
    # of retrieved evidence back to exactly which uploaded file it came
    # from, and when it was uploaded (for recency scoring later).
    new_document = Document(
        company_id=DEFAULT_COMPANY_ID,
        filename=file.filename,
        qdrant_point_ids=[],  # filled in below, after we have point_ids
    )
    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    upload_time = datetime.now(UTC).isoformat()
    extra_payload = [{"filename": file.filename, "chunk_index": i} for i in range(len(chunks))]

    point_ids = add_texts(
        texts=chunks,
        source_type="document",
        company_id=DEFAULT_COMPANY_ID,
        created_at=[upload_time] * len(chunks),
        source_id=[new_document.id] * len(chunks),
        category=["policy_document"] * len(chunks),
        extra_payload=extra_payload,
    )

    # now update the Document row with the actual Qdrant point ids
    new_document.qdrant_point_ids = point_ids
    db.commit()

    return {
        "success": True,
        "filename": file.filename,
        "chunks_stored": len(chunks),
        "document_id": new_document.id,
    }
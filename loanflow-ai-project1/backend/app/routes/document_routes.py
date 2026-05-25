import os

from fastapi import APIRouter, UploadFile, File

from app.core.mcp.client import call_tool
from app.services.document_parser import extract_text_from_pdf
from app.services.text_chunker import chunk_text
from app.services.vector_store import store_document_chunks

router = APIRouter()

UPLOAD_DIR = "app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    file_path = f"{UPLOAD_DIR}/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())

    extracted_text = extract_text_from_pdf(file_path)
    chunks = chunk_text(extracted_text)
    stored_count = store_document_chunks(
        document_id=file.filename.replace(".pdf", ""),
        filename=file.filename,
        chunks=chunks,
    )
    return {
        "documentId": file.filename.replace(".pdf", ""),
        "filename": file.filename,
        "characters": len(extracted_text),
        "chunkCount": len(chunks),
        "vectorsStored": stored_count,
    }


@router.get("/documents/search")
async def search_documents(question: str):
    chunks = await call_tool("search_policy_tool", {"query": question, "top_k": 5})
    return {"question": question, "matches": chunks}

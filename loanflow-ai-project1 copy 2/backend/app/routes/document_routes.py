import os
import json

from fastapi import APIRouter, UploadFile, File
from app.services.text_chunker import chunk_text
from app.services.document_parser import extract_text_from_pdf
from app.services.vector_store import store_document_chunks
from app.services.retrieval_service import search_similar_chunks


router = APIRouter()

UPLOAD_DIR = "app/uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    file_path = f"{UPLOAD_DIR}/{file.filename}"
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    extracted_text = extract_text_from_pdf(file_path)
    chunks = chunk_text(extracted_text)
    document_id = file.filename.replace(".pdf", "")
    stored_count = store_document_chunks(
        document_id=document_id,
        filename=file.filename,
        chunks=chunks,
    )
    return {
        "documentId": document_id,
        "filename": file.filename,
        "characters": len(extracted_text),
        "chunkCount": len(chunks),
        "vectorsStored": stored_count,
    }

@router.get("/documents/search")
def search_documents(question: str):
    results = search_similar_chunks(question)

    return {
        "question": question,
        "matches": results,
    }
import os
import uuid

from app.services.embedding_service import create_embedding
from pinecone import Pinecone

_pc = None
_index = None


def get_index():
    global _pc, _index
    if _index is None:
        _pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        _index = _pc.Index(os.getenv("PINECONE_INDEX_NAME"))
    return _index

def store_document_chunks(document_id: str, filename: str, chunks: list[str]):
    vectors = []

    for idx, chunk in enumerate(chunks):
        embedding = create_embedding(chunk)

        vectors.append(
            {
                "id": str(uuid.uuid4()),
                "values": embedding,
                "metadata": {
                    "document_id": document_id,
                    "filename": filename,
                    "chunk_index": idx,
                    "text": chunk,
                },
            }
        )

    get_index().upsert(vectors=vectors)

    return len(vectors)
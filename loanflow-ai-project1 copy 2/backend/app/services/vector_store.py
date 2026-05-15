import os
import uuid

from app.services.embedding_service import create_embedding
from pinecone import Pinecone

pc= Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))

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

    index.upsert(vectors=vectors)

    return len(vectors)
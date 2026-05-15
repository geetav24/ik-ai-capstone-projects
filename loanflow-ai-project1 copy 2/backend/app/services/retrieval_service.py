import os
from pinecone import Pinecone

from app.services.embedding_service import create_embedding

pc= Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))

def search_similar_chunks(question: str, top_k: int = 3) -> list[dict]:
    question_embedding = create_embedding(question)

    results = index.query(
        vector=question_embedding,
        top_k=top_k,
        include_metadata=True,
    )

    matches = []

    for match in results.matches:
        matches.append(
            {
                "score": match.score,
                "document_id": match.metadata.get("document_id"),
                "filename": match.metadata.get("filename"),
                "chunk_index": match.metadata.get("chunk_index"),
                "text": match.metadata.get("text"),
            }
        )

    return matches
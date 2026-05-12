from app.services.retrieval_service import search_similar_chunks


def loan_policy_tool(question: str):
    return search_similar_chunks(question)
def get_loan_policy():
    return {
        "min_credit_score": 700,
        "required_documents": [
            "bank_statements",
            "income_proof",
            "id_verification"
        ],
        "restricted_decisions": [
            "approve",
            "reject",
            "final approval",
            "final rejection"
        ],
        "human_review_required_rule": (
            "AI must not approve or reject loans. "
            "AI can only recommend human review and explain risk signals."
        )
    }
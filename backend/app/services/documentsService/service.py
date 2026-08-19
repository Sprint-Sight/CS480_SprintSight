from app.schemas.assessment import IngestionRequest


# Placeholder for document ingestion pipeline.
def collect_document_signals(payload: IngestionRequest) -> dict[str, float]:
    return {
        "documentation_quality": 82.0,
        "demo_completeness": 78.0,
    }

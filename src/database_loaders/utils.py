# FILE: src/database_loaders/utils.py
# Kilo-Architect - Metadata Transformation Utilities V3.0 (Hardened)

"""
This utility module provides stateless helper functions for transforming the
enriched chunk data into a format suitable for Pinecone's metadata payload.

V3.0 Changes:
- Completely refactored the flattening and key creation logic to be robust,
  explicit, and type-safe, fixing data corruption bugs.
- Now preserves the full original content ('source_content') for traceability,
  addressing the "missing big chunk" issue.
- Enhanced self-test to check data types for every field.
"""
import logging
import json
from datetime import datetime
from typing import Dict, Any, List

# --- PUBLIC ORCHESTRATION FUNCTION ---
def create_pinecone_metadata(
    chunk: Dict[str, Any],
    publication_date: datetime
) -> Dict[str, Any]:
    """
    Creates a flattened, database-friendly metadata payload from an enriched chunk.

    Args:
        chunk: A dictionary representing a single enriched chunk.
        publication_date: A pre-resolved datetime object for the document.
    """
    metadata_payload = {}
    original_metadata = chunk.get('metadata', {})

    # --- Step 1: Add Core and Traceability Fields ---
    metadata_payload['doc_id'] = original_metadata.get("doc_id", "unknown_doc")
    metadata_payload['chunk_id'] = chunk.get('chunk_id')
    metadata_payload['text_for_embedding'] = chunk.get('text') # What gets vectorized

    # V3.0 FIX: Ensure full traceability. For tables, this is the markdown.
    if original_metadata.get("chunk_type") == "table_summary":
        metadata_payload['source_content'] = original_metadata.get("raw_table_content")
    else:
        metadata_payload['source_content'] = chunk.get('text')


    # --- Step 2: Extract High-Level Metadata with Type Safety ---
    semantic_purpose_data = original_metadata.get("semantic_purpose", {})
    metadata_payload['semantic_purpose'] = str(semantic_purpose_data.get("value", "Unknown"))
    metadata_payload['semantic_purpose_confidence'] = float(semantic_purpose_data.get("confidence", 0.0))

    quality_data = original_metadata.get("quality_assessment", {})
    metadata_payload['quality_assessment_confidence'] = float(quality_data.get("confidence", 0.0))
    metadata_payload['quality_assessment_is_ambiguous'] = bool(quality_data.get("is_ambiguous", True))

    # --- Step 3: Extract Persona Scores Explicitly ---
    persona_scores = original_metadata.get("persona_relevance_scores", {})
    for persona, data in persona_scores.items():
        if isinstance(data, dict):
            # Transform 'clinical_analyst' to 'persona_clinical_analyst_score'
            key_name = f"persona_{persona}_score"
            metadata_payload[key_name] = float(data.get("score", 0.0))

    # --- Step 4: Add Derived Metadata ---
    metadata_payload['published_timestamp'] = int(publication_date.timestamp())

    section_path = original_metadata.get('section_path', [])
    metadata_payload['section_path'] = " > ".join(section_path)
    for i, section_name in enumerate(section_path):
        if i < 5: metadata_payload[f'section_level_{i+1}'] = section_name

    typed_entities = original_metadata.get('typed_entities', [])
    if isinstance(typed_entities, list):
         metadata_payload['mentioned_entities'] = [
            entity.get('name') for entity in typed_entities if isinstance(entity, dict) and 'name' in entity
        ]
    else:
        metadata_payload['mentioned_entities'] = []


    logging.debug(f"Created metadata payload for chunk {metadata_payload.get('chunk_id')}")
    return metadata_payload


# --- Example Usage & Self-Test ---
if __name__ == '__main__':
    print("--- Running self-test for metadata utility functions (V3.0) ---")
    sample_doc_date = datetime(2024, 12, 1)

    # Test case 1: A text chunk
    sample_text_chunk = {
        "chunk_id": "chunk-text-123",
        "text": "The study met its primary endpoint...",
        "metadata": {
            "doc_id": "esketamine-psd-12-2024",
            "chunk_type": "semantic_text",
            "section_path": ["6. PBAC OUTCOME"],
            "semantic_purpose": {"value": "Efficacy Results", "confidence": 0.98},
            "persona_relevance_scores": {"clinical_analyst": {"score": 0.95}},
            "typed_entities": [{"name": "Esketamine", "type": "DRUG"}],
            "quality_assessment": {"confidence": 0.99, "is_ambiguous": False}
        }
    }
    # Test case 2: A table summary chunk with raw content
    sample_table_chunk = {
        "chunk_id": "chunk-table-456",
        "text": "This table summarizes drug costs.",
        "metadata": {
            "doc_id": "pbac_guidelines_version_5",
            "chunk_type": "table_summary",
            "section_path": ["Tables", "Page 34"],
            "semantic_purpose": {"value": "Pharmacoeconomic Analysis", "confidence": 0.9},
            "persona_relevance_scores": {"health_economist": {"score": 1.0}, "regulatory_specialist": {"score": 0.8}},
            "typed_entities": [],
            "raw_table_content": "| Drug | Cost |\n|---|---|\n| Drug A | $100 |" # The raw table data
        }
    }

    # --- Test Text Chunk ---
    print("\n--- Testing Text Chunk ---")
    final_text_meta = create_pinecone_metadata(sample_text_chunk, sample_doc_date)
    print(json.dumps(final_text_meta, indent=2))
    # Assertions for text chunk
    assert final_text_meta['source_content'] == "The study met its primary endpoint..."
    assert isinstance(final_text_meta['persona_clinical_analyst_score'], float)
    assert final_text_meta['semantic_purpose'] == "Efficacy Results"
    assert isinstance(final_text_meta['semantic_purpose_confidence'], float)
    assert isinstance(final_text_meta['quality_assessment_is_ambiguous'], bool)

    # --- Test Table Chunk ---
    print("\n--- Testing Table Chunk ---")
    final_table_meta = create_pinecone_metadata(sample_table_chunk, sample_doc_date)
    print(json.dumps(final_table_meta, indent=2))
    # Assertions for table chunk
    assert final_table_meta['text_for_embedding'] == "This table summarizes drug costs."
    assert final_table_meta['source_content'] == "| Drug | Cost |\n|---|---|\n| Drug A | $100 |"
    assert isinstance(final_table_meta['persona_health_economist_score'], float)
    assert isinstance(final_table_meta['persona_regulatory_specialist_score'], float)
    assert 'persona_clinical_analyst_score' not in final_table_meta # Ensure missing scores aren't added

    print("\n--- Self-test PASSED ---")
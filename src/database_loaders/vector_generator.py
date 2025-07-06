# FILE: src/database_loaders/vector_generator.py
# Kilo-Architect - Multi-Vector Generation Specialist V1.1 (Corrected)

"""
This specialist module is responsible for generating multiple, aspect-specific
vector embeddings for a single document chunk.

V1.1 Change: Corrected import paths to use relative imports, making the
module compatible with being run as part of a package.
"""

import logging
import os
import json
from typing import Dict, Any, List

import pydantic
# V1.1 FIX: Changed from absolute to relative imports.
# The '..' means 'go up one directory level from here'.
from ..document_processing.llm_client import call_gemini, LLMAPIError
from ..embedding.client import EmbeddingClient

# --- CONFIGURATION & MODEL DEFINITIONS ---
SUMMARIZATION_MODEL_NAME = os.environ.get("SUMMARIZATION_MODEL_NAME", "gemini-1.5-flash-latest")
EMBEDDING_MODEL_NAME = "text-embedding-004"


# --- SCHEMAS FOR ROBUST PARSING ---
class AspectualSummaries(pydantic.BaseModel):
    """Ensures the LLM output for summaries is valid and structured."""
    clinical_summary: str = pydantic.Field(
        ..., description="A summary focusing ONLY on clinical aspects: efficacy, safety, trial design."
    )
    economic_summary: str = pydantic.Field(
        ..., description="A summary focusing ONLY on economic aspects: cost, pricing, market access, QALY."
    )


# --- INITIALIZE CLIENTS ONCE (Module-level singleton pattern) ---
try:
    embedding_client = EmbeddingClient(model_name=EMBEDDING_MODEL_NAME)
    logging.info(f"EmbeddingClient initialized successfully for model: {EMBEDDING_MODEL_NAME}")
except Exception as e:
    logging.critical(f"Failed to initialize EmbeddingClient: {e}", exc_info=True)
    raise


# --- INTERNAL HELPER FUNCTIONS ---

def _generate_aspect_summaries(chunk_text: str) -> AspectualSummaries:
    """
    Uses a fast LLM to generate clinical and economic summaries from chunk text.
    Returns default empty summaries on failure to ensure pipeline resilience.
    """
    prompt = f"""
    You are an efficient text analysis tool. Your task is to extract specific aspects from the following text.
    Analyze the text and generate a single, minified JSON object with two keys: "clinical_summary" and "economic_summary".

    - The clinical_summary must ONLY contain information about clinical efficacy, safety, side effects, trial design, or patient outcomes.
    - The economic_summary must ONLY contain information about cost-effectiveness, pricing, QALY, budget impact, or market access.

    If an aspect is not present in the text, return an empty string for that key.

    TEXT TO ANALYZE:
    ---
    {chunk_text}
    ---
    """
    try:
        logging.debug("Requesting aspectual summaries from LLM...")
        raw_response = call_gemini(prompt, model_name=SUMMARIZATION_MODEL_NAME)
        summaries = AspectualSummaries.model_validate_json(raw_response)
        logging.debug("Successfully generated and validated aspectual summaries.")
        return summaries
    except (LLMAPIError, json.JSONDecodeError, pydantic.ValidationError) as e:
        logging.warning(
            f"Could not generate or validate aspectual summaries. Defaulting to empty. Error: {e}"
        )
        return AspectualSummaries(clinical_summary="", economic_summary="")


# --- PUBLIC ORCHESTRATION FUNCTION ---

def create_multi_vector_payload(chunk: Dict[str, Any]) -> Dict[str, List[float]]:
    """
    Creates a dictionary of vector embeddings for a given chunk.
    """
    vector_payload: Dict[str, List[float]] = {}
    chunk_id = chunk.get("chunk_id", "unknown_chunk")

    try:
        metadata = chunk.get("metadata", {})
        doc_id = metadata.get("doc_id", "")
        section_path = " > ".join(metadata.get("section_path", []))
        purpose = metadata.get("semantic_purpose", {}).get("value", "")
        text_to_embed = f"DOCUMENT: {doc_id}\nSECTION: {section_path}\nTYPE: {purpose}\nCONTENT: {chunk.get('text', '')}"

        logging.info(f"[{chunk_id}] Generating 'base' vector.")
        vector_payload['base'] = embedding_client.embed(text_to_embed, task_type="RETRIEVAL_DOCUMENT")
    except Exception as e:
        logging.error(f"[{chunk_id}] FAILED to generate 'base' vector. Error: {e}", exc_info=True)
        return {}

    summaries = _generate_aspect_summaries(chunk.get("text", ""))

    if summaries.clinical_summary.strip():
        logging.info(f"[{chunk_id}] Generating 'clinical' vector from summary.")
        try:
            vector_payload['clinical'] = embedding_client.embed(
                summaries.clinical_summary, task_type="RETRIEVAL_DOCUMENT"
            )
        except Exception as e:
            logging.error(f"[{chunk_id}] FAILED to generate 'clinical' vector. Error: {e}")
    else:
        logging.debug(f"[{chunk_id}] Skipping 'clinical' vector: no clinical summary generated.")

    if summaries.economic_summary.strip():
        logging.info(f"[{chunk_id}] Generating 'economic' vector from summary.")
        try:
            vector_payload['economic'] = embedding_client.embed(
                summaries.economic_summary, task_type="RETRIEVAL_DOCUMENT"
            )
        except Exception as e:
            logging.error(f"[{chunk_id}] FAILED to generate 'economic' vector. Error: {e}")
    else:
        logging.debug(f"[{chunk_id}] Skipping 'economic' vector: no economic summary generated.")

    logging.info(f"[{chunk_id}] Successfully created payload with {len(vector_payload)} vectors.")
    return vector_payload
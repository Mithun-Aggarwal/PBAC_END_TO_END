# FILE: run_enrichment.py
# Kilo-Architect - Pass 3 Semantic Enrichment Orchestrator V5.1 (Final Efficiency Polish)

"""
...
V5.1 Change (Final Efficiency Polish):
- Implemented a "Pre-Enrichment Junk Filter" to improve cost and performance.
- A new `_is_low_value_chunk` function uses heuristics to identify worthless chunks
  (e.g., very short text, mostly numbers).
- These low-value chunks bypass the expensive LLM call and are assigned a default
  "Miscellaneous" payload, saving significant cost and processing time.
- Updated to use the refined `chunk_enrichment_v9` prompt for all valuable chunks.
"""

from dotenv import load_dotenv
load_dotenv()
import argparse
import json
import logging
import pydantic
import re
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from src.document_processing.llm_client import call_gemini, LLMAPIError
from src.document_processing.prompt_loader import load_prompt
# Using the stable V5 schemas
from src.document_processing.schemas import (
    Chunk, EnrichedChunkV5, EnrichedChunkMetadataV5, JustifiedStringValue,
    PersonaRelevanceV5, TypedEntityV5, QualityAssessmentV5, SemanticPurposeEnum, EntityTypeEnum
)

class EnrichmentPayloadV5(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    semantic_purpose: JustifiedStringValue
    persona_relevance_scores: PersonaRelevanceV5
    typed_entities: List[TypedEntityV5]
    quality_assessment: QualityAssessmentV5

def _is_low_value_chunk(text: str) -> bool:
    """
    Heuristic-based filter to identify "junk" chunks not worth sending to an LLM.
    
    Returns True if:
    - Text is shorter than 20 characters.
    - More than 70% of characters are digits or symbols.
    """
    text = text.strip()
    if len(text) < 20:
        return True
    
    alphanumeric_chars = sum(1 for char in text if char.isalnum())
    if len(text) > 0 and (alphanumeric_chars / len(text)) < 0.5:
        return True
        
    return False

def _run_enrichment_specialist(
    chunk: Chunk, doc_title: str
) -> Tuple[str, Optional[EnrichedChunkV5]]:
    """
    The main unit of work for a single thread. Takes one chunk and enriches it.
    """
    try:
        # V5.1 - Use the latest, most refined prompt
        prompt_template = load_prompt('chunk_enrichment_v9')
        target_model = "gemini-2.5-flash"
        
        formatted_prompt = prompt_template.format(
            doc_title=doc_title,
            section_path=" -> ".join(chunk.metadata.section_path),
            chunk_text=chunk.text
        )
        
        llm_response_str = call_gemini(formatted_prompt, model_name=target_model, force_json=True)
        payload = EnrichmentPayloadV5.model_validate_json(llm_response_str)
        
        base_metadata = chunk.metadata.model_dump()
        if base_metadata['chunk_type'] == 'semantic_text':
            base_metadata['chunk_type'] = _format_chunk_type(payload.semantic_purpose.value.value)
        
        enriched_metadata = EnrichedChunkMetadataV5(**base_metadata, **payload.model_dump())
        final_chunk = EnrichedChunkV5(chunk_id=chunk.chunk_id, text=chunk.text, metadata=enriched_metadata)
        
        return chunk.chunk_id, final_chunk
        
    except Exception as e:
        logging.error(f"Failed to process chunk {chunk.chunk_id}. Error: {e}", exc_info=False)
        return chunk.chunk_id, None

def _format_chunk_type(semantic_purpose: str) -> str:
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', semantic_purpose)
    s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
    return s2.lower().replace('/', '_').replace(' ', '_').replace('__', '_')


def main():
    parser = argparse.ArgumentParser(description="Pass 3 (V5.1): Parallelized, Efficient Knowledge Extraction.")
    parser.add_argument("--output-dir", type=str, required=True, help="Root directory for artifacts.")
    parser.add_argument("--force-reprocess", action="store_true", help="Force reprocessing.")
    parser.add_argument("--log-file", type=str, default=None, help="Optional log file path.")
    parser.add_argument("--num-workers", type=int, default=10, help="Number of parallel threads for enrichment.")
    args = parser.parse_args()

    # Logger setup...
    log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(funcName)s] - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file, mode='w', encoding='utf-8')
        file_handler.setFormatter(log_formatter)
        root_logger.addHandler(file_handler)
    logging.info(f"--- Enrichment Pipeline Started. Logging to: {args.log_file or 'Console'} ---")

    output_dir = Path(args.output_dir).resolve()
    artifact_dirs = [d for d in output_dir.iterdir() if d.is_dir() and d.name.endswith("_artifacts")]
    
    if not artifact_dirs:
        logging.critical("FATAL: No directories ending with '_artifacts' found.")
        sys.exit(1)

    logging.info(f"SUCCESS: Found {len(artifact_dirs)} document artifact folders to process using {args.num_workers} workers.")

    for artifact_dir in artifact_dirs:
        doc_id = artifact_dir.name.replace("_artifacts", "")
        chunks_path = artifact_dir / "chunks.json"
        enriched_chunks_path = artifact_dir / "enriched_chunks_v5.json"
        failed_chunks_path = artifact_dir / "failed_chunks_for_review.json"

        if not chunks_path.exists():
            logging.warning(f"Skipping '{doc_id}': Base 'chunks.json' not found.")
            continue
            
        if not args.force_reprocess and enriched_chunks_path.exists() and enriched_chunks_path.stat().st_size > 2:
            logging.info(f"Skipping '{doc_id}': Non-empty V5 enriched artifact already exists.")
            continue
        
        logging.info(f"--- Starting Parallel Enrichment for document: {doc_id} with V9 prompt ---")
        with open(chunks_path, 'r', encoding='utf-8') as f:
            base_chunks = [Chunk.model_validate(c) for c in json.load(f)]
            
        doc_title = "Unknown Document"
        master_record_path = artifact_dir / "master_record.json"
        if master_record_path.exists():
            with open(master_record_path, 'r', encoding='utf-8') as f:
                title_value = json.load(f).get("global_metadata", {}).get("doc_title", {}).get("value")
                if title_value: doc_title = title_value

        final_enriched_chunks: List[EnrichedChunkV5] = []
        failed_chunks_for_review: List[Dict] = []
        
        with ThreadPoolExecutor(max_workers=args.num_workers) as executor:
            future_to_chunk = {}
            for chunk in base_chunks:
                # --- V5.1 JUNK FILTER ---
                if _is_low_value_chunk(chunk.text):
                    logging.info(f"Chunk {chunk.chunk_id} flagged as low-value. Skipping LLM call.")
                    # Create a default payload without an API call
                    default_payload = EnrichmentPayloadV5(
                        semantic_purpose=JustifiedStringValue(value=SemanticPurposeEnum.MISCELLANEOUS, confidence=1.0, justification="Programmatically flagged as low-value content."),
                        persona_relevance_scores={ "clinical_analyst": {"score": 0.0, "justification": "Low-value content."}, "health_economist": {"score": 0.0, "justification": "Low-value content."}, "regulatory_specialist": {"score": 0.0, "justification": "Low-value content."} },
                        typed_entities=[],
                        quality_assessment=QualityAssessmentV5(confidence=0.0, is_ambiguous=True, justification="Skipped LLM enrichment due to low textual content.")
                    )
                    # Construct the final chunk and add it directly to the results list
                    base_metadata = chunk.metadata.model_dump()
                    base_metadata['chunk_type'] = 'miscellaneous'
                    enriched_metadata = EnrichedChunkMetadataV5(**base_metadata, **default_payload.model_dump())
                    final_chunk = EnrichedChunkV5(chunk_id=chunk.chunk_id, text=chunk.text, metadata=enriched_metadata)
                    final_enriched_chunks.append(final_chunk)
                else:
                    # If chunk is valuable, submit it to the thread pool
                    future = executor.submit(_run_enrichment_specialist, chunk, doc_title)
                    future_to_chunk[future] = chunk

            progress_bar = tqdm(as_completed(future_to_chunk), total=len(future_to_chunk), desc=f"Enriching {doc_id}")
            for future in progress_bar:
                original_chunk = future_to_chunk[future]
                try:
                    _chunk_id, result_chunk = future.result()
                    if result_chunk:
                        final_enriched_chunks.append(result_chunk)
                    else:
                        failed_chunks_for_review.append({"chunk_id": original_chunk.chunk_id, "error_message": "Enrichment returned None.", "original_chunk": original_chunk.model_dump()})
                except Exception as exc:
                    failed_chunks_for_review.append({"chunk_id": original_chunk.chunk_id, "error_message": str(exc), "original_chunk": original_chunk.model_dump()})

        # Finalize and save outputs
        if final_enriched_chunks:
            final_enriched_chunks.sort(key=lambda c: (c.metadata.page_numbers[0], c.chunk_id))
            serialized_chunks = [c.model_dump() for c in final_enriched_chunks]
            with open(enriched_chunks_path, 'w', encoding='utf-8') as f:
                json.dump(serialized_chunks, f, indent=4)
        
        if failed_chunks_for_review:
            with open(failed_chunks_path, 'w', encoding='utf-8') as f:
                json.dump(failed_chunks_for_review, f, indent=4)

        logging.info(
            f"Enrichment for '{doc_id}' complete. "
            f"SUCCESS: {len(final_enriched_chunks)}. "
            f"FAILED: {len(failed_chunks_for_review)}. "
            f"Quarantined failures saved to: {failed_chunks_path if failed_chunks_for_review else 'N/A'}"
        )

    logging.info("--- Enrichment Pipeline COMPLETED ---")


if __name__ == "__main__":
    main()
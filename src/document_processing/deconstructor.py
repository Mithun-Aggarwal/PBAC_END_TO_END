# FILE: src/document_processing/deconstructor.py
# Kilo-Architect - Deconstruction Orchestrator V8.0 (Re-modularized)

import fitz
import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Tuple

from .schemas import (
    Pass1Layout, MasterRecord, GlobalMetadata, LLMResponseValue
)
# --- V8.0 ARCHITECTURAL REFACTOR ---
# Complex logic is now delegated to specialized, single-responsibility modules.
from ._pass_1_structure import run_pass_1_layout_analysis
from ._pass_2_semantic import extract_global_metadata, summarize_tables, LLMResponseValidationError, LLMAPIError

def create_master_record(
    pdf_path: str,
    output_dir: str,
    config: Dict[str, Any]
) -> Tuple[MasterRecord, Pass1Layout]:
    """
    Orchestrates the full deconstruction (Pass 1 and 2) of a PDF document
    to a structured master record. This function is now a high-level
    coordinator that calls specialized modules for structural and semantic analysis.

    Args:
        pdf_path: The full path to the source PDF file.
        output_dir: The root directory where artifacts will be saved.
        config: A dictionary containing system configurations.

    Returns:
        A tuple containing the generated MasterRecord and Pass1Layout objects.
    """
    doc_id = os.path.splitext(os.path.basename(pdf_path))[0]
    artifact_dir = os.path.join(output_dir, f"{doc_id}_artifacts")
    os.makedirs(artifact_dir, exist_ok=True)

    # --- Pass 1: Structural Analysis ---
    # The config is passed to Pass 1 to allow for tunable heuristics.
    pass_1_layout = run_pass_1_layout_analysis(pdf_path, config)

    # --- Pass 2: Semantic Analysis ---
    logging.info(f"[{doc_id}] Starting Pass 2: Semantic Analysis...")
    global_metadata = None # Ensure variable is initialized

    try:
        global_metadata = extract_global_metadata(pass_1_layout)
    except (LLMResponseValidationError, LLMAPIError) as e:
        # CRITICAL STABILITY FIX: Gracefully handle metadata extraction failure.
        logging.error(f"FATAL (non-blocking): Could not extract global metadata for {doc_id}. Error: {e}", exc_info=True)
        # Create a valid placeholder object to ensure pipeline stability.
        global_metadata = GlobalMetadata(
            doc_title=LLMResponseValue(value="Extraction Failed", confidence=0.0, justification=str(e)),
            drug_name=LLMResponseValue(value="Extraction Failed", confidence=0.0, justification=str(e)),
            indication=LLMResponseValue(value="Extraction Failed", confidence=0.0, justification=str(e)),
            sponsor=LLMResponseValue(value="Extraction Failed", confidence=0.0, justification=str(e))
        )

    processed_tables = summarize_tables(pass_1_layout)

    # --- Assembly ---
    master_record = MasterRecord(
        doc_id=pass_1_layout.doc_id,
        global_metadata=global_metadata,
        pass_1_metadata=pass_1_layout.processing_metadata,
        tables=processed_tables,
        sections=[] # Specialist section extraction is out of scope.
    )

    # --- Final Artifact Saving ---
    # Save the Pass 1 and Master Record artifacts at the end of the process.
    pass1_path = os.path.join(artifact_dir, "pass_1_layout.json")
    with open(pass1_path, "w", encoding='utf-8') as f:
        f.write(pass_1_layout.model_dump_json(indent=4))
    logging.info(f"Pass 1 layout artifact saved to {pass1_path}")

    master_record_path = os.path.join(artifact_dir, "master_record.json")
    with open(master_record_path, "w", encoding='utf-8') as f:
        f.write(master_record.model_dump_json(indent=4))
    logging.info(f"Master record created and saved to {master_record_path}")

    return master_record, pass_1_layout
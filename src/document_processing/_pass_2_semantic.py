# FILE: src/document_processing/_pass_2_semantic.py
# Kilo-Architect - Semantic Analysis Module V8.3 (Debugging Markdown Traceability)

"""
This module is the dedicated home for all Pass 2 LLM-driven semantic inquiry.

V8.3 Change: Added extensive debug logging to `summarize_tables` to meticulously
trace the `markdown_representation` from `Pass1Layout` blocks into `ProcessedTable`
objects, aiming to pinpoint where table content is lost for validation.
"""
import logging
import json
import pydantic
from typing import List

from .schemas import (
    Pass1Layout, GlobalMetadata, TableSummary, ProcessedTable
)
from .llm_client import call_gemini, LLMAPIError
from .prompt_loader import load_prompt

# Custom exceptions for clear error handling
class LLMResponseValidationError(Exception):
    """Custom exception for when an LLM response fails Pydantic validation even after successful parsing."""
    pass

# ==============================================================================
# INTERNAL SPECIALIST FUNCTION (RELIANT ON CENTRALIZED REPAIR)
# ==============================================================================

def _run_extraction_specialist(
    prompt_name: str,
    context_text: str,
    validation_model: pydantic.BaseModel,
    model_name: str = "gemini-1.5-flash-latest"
) -> pydantic.BaseModel:
    """
    A generic, robust function to run an extraction specialist prompt.

    It now fully delegates JSON parsing and repair to the centralized `call_gemini`
    function, which has a built-in multi-stage repair pipeline. This function's
    sole responsibility is to call the LLM and validate the final, cleaned
    response against a specific Pydantic schema.

    Returns:
        A validated Pydantic model instance with the extracted data.

    Raises:
        LLMResponseValidationError: If the LLM response is successfully parsed into JSON but
                                    still fails Pydantic schema validation.
        LLMAPIError: If the underlying API call and all of its internal repair stages fail.
    """
    logging.info(f"Running LLM specialist '{prompt_name}' using model '{model_name}'...")
    prompt_template = load_prompt(prompt_name)
    formatted_prompt = prompt_template.format(context_text=context_text.strip())
    
    try:
        llm_response_str = call_gemini(formatted_prompt, model_name=model_name, force_json=True)
        return validation_model.model_validate_json(llm_response_str)

    except LLMAPIError as e:
        logging.error(f"LLM specialist '{prompt_name}' failed because the API call or repair process failed: {e}")
        raise e
        
    except (pydantic.ValidationError, json.JSONDecodeError) as e:
        logging.error(f"Final validation failed for '{prompt_name}'. The JSON response was syntactically valid but did not match the '{validation_model.__name__}' schema.")
        raise LLMResponseValidationError(
            f"LLM response for '{prompt_name}' was valid JSON but failed schema validation for {validation_model.__name__}."
        ) from e


# ==============================================================================
# PUBLIC SEMANTIC ANALYSIS FUNCTIONS
# ==============================================================================

def extract_global_metadata(pass_1_layout: Pass1Layout) -> GlobalMetadata:
    """Extracts global metadata from the first few pages of a document."""
    logging.info(f"[{pass_1_layout.doc_id}] Extracting global metadata...")
    context_text = "".join(
        span.text + " "
        for page in pass_1_layout.pages[:3]
        for block in page.blocks if block.block_type == 'text'
        for span in block.spans
    )
    
    return _run_extraction_specialist(
        prompt_name='global_metadata_v1',
        context_text=context_text,
        validation_model=GlobalMetadata
    )

def summarize_tables(pass_1_layout: Pass1Layout) -> List[ProcessedTable]:
    """Iterates through tables found in Pass 1 and generates a summary for each."""
    num_tables_in_layout = len([b for p in pass_1_layout.pages for b in p.blocks if b.block_type == 'table'])
    logging.info(f"[{pass_1_layout.doc_id}] Summarizing {num_tables_in_layout} tables from Pass 1 Layout...")
    processed_tables: List[ProcessedTable] = []
    
    for page in pass_1_layout.pages:
        for block in page.blocks:
            if block.block_type == "table":
                # V8.3 Debug: Trace block.table_markdown as it enters _pass_2_semantic.py
                block_markdown_len = len(block.table_markdown) if block.table_markdown else 0
                logging.debug(f"[{pass_1_layout.doc_id}] Processing table block {block.block_id} (Page {page.page_number}): "
                              f"block.table_markdown is_None={block.table_markdown is None}, length={block_markdown_len}")

                if not block.table_markdown:
                    logging.warning(f"[{pass_1_layout.doc_id}] Table block {block.block_id} has empty or None markdown_representation. Skipping LLM summary.")
                    summary_text = "N/A (No markdown content for summary)"
                else:
                    summary_text = f"Error: Could not generate summary for table {block.block_id}."
                    try:
                        summary_result = _run_extraction_specialist(
                            prompt_name="table_summary_v1",
                            context_text=block.table_markdown,
                            validation_model=TableSummary
                        )
                        summary_text = summary_result.summary
                        logging.info(f"[{pass_1_layout.doc_id}] Successfully generated summary for table {block.block_id}")
                    except (LLMResponseValidationError, LLMAPIError) as e:
                        logging.error(f"[{pass_1_layout.doc_id}] Failed to generate summary for table {block.block_id}. Error: {e}", exc_info=True)
                        summary_text = f"Error generating summary: {e}"

                # Create ProcessedTable instance
                pt = ProcessedTable(
                    table_id=block.block_id,
                    page_number=page.page_number,
                    bounding_box=block.bounding_box,
                    llm_summary=summary_text,
                    markdown_representation=block.table_markdown, # This should pass the original markdown
                )
                processed_tables.append(pt)
                
                # V8.3 Debug: Trace markdown_representation AFTER ProcessedTable creation
                pt_markdown_len = len(pt.markdown_representation) if pt.markdown_representation is not None else 0
                logging.debug(f"[{pass_1_layout.doc_id}] Created ProcessedTable {pt.table_id}: "
                              f"pt.markdown_representation is_None={pt.markdown_representation is None}, length={pt_markdown_len}")

    logging.info(f"[{pass_1_layout.doc_id}] Finished processing {len(processed_tables)} tables for MasterRecord.")
    return processed_tables
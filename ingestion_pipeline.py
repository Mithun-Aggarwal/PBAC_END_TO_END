# FILE: ingestion_pipeline.py
# Kilo-Architect - Master Ingestion Orchestrator V3.4 (Lossless Validation - Robust Table Chars)

from dotenv import load_dotenv
load_dotenv()
import argparse
import json
import logging
import os
import sys
from pathlib import Path
import yaml
import concurrent.futures
from tqdm import tqdm
from typing import List

from src.document_processing.deconstructor import create_master_record
from src.document_processing.chunker import create_chunks_from_record
# --- V3.2 IMPORTS ---
from src.document_processing.schemas import Pass1Layout, Chunk

# --- V3.2 NEW - Custom Exception for Validation ---
class ContentLossError(Exception):
    """Raised when the content completeness check fails."""
    pass

# --- V3.2 NEW - The Lossless Validation Function ---
# V3.4 FIX: Robustly calculates table_content_chars by always getting length, even if raw_table_content is None.
def validate_content_completeness(pass_1_layout: Pass1Layout, chunks: List[Chunk], config: dict):
    """
    Compares the total text character count from the source layout against the
    final chunked content to ensure no significant data was lost.
    """
    logging.debug("Running lossless validation check...")
    
    # 1. Calculate Total Source Characters from Pass 1 Layout
    source_chars = 0
    for page in pass_1_layout.pages:
        for block in page.blocks:
            if block.block_type == 'text':
                source_chars += sum(len(span.text) for span in block.spans)
            elif block.block_type == 'table' and block.table_markdown:
                source_chars += len(block.table_markdown)

    # 2. Calculate Total Chunked Characters
    semantic_text_chars = sum(len(c.text) for c in chunks if c.metadata.chunk_type == 'semantic_text')
    
    # V3.4 FIX: Always get length, treating None as empty string. Remove the filter.
    table_content_chars = 0
    for chunk in chunks:
        if chunk.metadata.chunk_type == 'table_summary':
            raw_content = getattr(chunk.metadata, 'raw_table_content', None)
            if raw_content is None:
                logging.warning(f"Table chunk {chunk.chunk_id}: raw_table_content is None. Treating as 0 length for validation.")
            table_content_chars += len(raw_content if raw_content is not None else "")
    
    logging.debug(f"Calculated table_content_chars from chunks: {table_content_chars}")
    chunked_chars = semantic_text_chars + table_content_chars


    # 3. Compare and Assert
    completeness_threshold = config.get("validation_rules", {}).get("completeness_threshold", 0.95)
    
    if source_chars == 0 and chunked_chars > 0:
        logging.warning("Source character count was zero, but chunks were produced. Skipping validation.")
        return # Cannot divide by zero, but content exists.

    if source_chars == 0 and chunked_chars == 0:
        logging.info("Source and chunked content are both empty. Validation passed.")
        return

    completeness_ratio = chunked_chars / source_chars
    
    logging.info(f"Validation Check: Source Chars={source_chars}, Chunked Chars={chunked_chars}, Ratio={completeness_ratio:.2%}")
    
    if completeness_ratio < completeness_threshold:
        raise ContentLossError(
            f"Content loss validation failed! Completeness ratio is {completeness_ratio:.2%}, "
            f"which is below the required threshold of {completeness_threshold:.2%}."
        )
    
    logging.info(f"Content completeness check PASSED. ({completeness_ratio:.2%} >= {completeness_threshold:.2%})")


def process_single_document(pdf_path: Path, output_dir: Path, config: dict, force_reprocess: bool) -> tuple[str, str, str]:
    """
    The main unit of work for a single PROCESS.
    V3.2: Now includes the lossless validation check at the end.
    """
    doc_id = pdf_path.stem
    process_name = concurrent.futures.process.mp.current_process().name
    log_prefix = f"[{doc_id}]"
    
    try:
        artifact_dir = output_dir / f"{doc_id}_artifacts"
        artifact_dir.mkdir(exist_ok=True)
        final_chunk_artifact_path = artifact_dir / "chunks.json"

        if not force_reprocess and final_chunk_artifact_path.exists() and final_chunk_artifact_path.stat().st_size > 2:
            logging.info(f"{log_prefix} Skipping: Non-empty chunk artifact already exists.")
            return (doc_id, "skipped", "Artifact already exists")

        logging.info(f"{log_prefix} Starting processing on {process_name}...")
        
        master_record, pass_1_layout = create_master_record(
            pdf_path=str(pdf_path), output_dir=str(output_dir), config=config
        )
        chunks = create_chunks_from_record(master_record, pass_1_layout, config=config)

        # --- V3.2 FINAL VALIDATION STEP ---
        # Before saving, run the completeness check.
        # This will raise ContentLossError on failure, which is caught below.
        validate_content_completeness(pass_1_layout, chunks, config)
        # --- END OF VALIDATION ---

        serialized_chunks = [chunk.model_dump() for chunk in chunks]
        with open(final_chunk_artifact_path, 'w', encoding='utf-8') as f:
            json.dump(serialized_chunks, f, indent=4)
        
        return (doc_id, "success", f"Processed {len(chunks)} chunks.")

    except Exception as e:
        # This will now catch ContentLossError as well.
        logging.error(f"{log_prefix} --- FAILED processing for document ---", exc_info=True)
        return (doc_id, "failed", str(e))


def main():
    parser = argparse.ArgumentParser(description="High-throughput parallel document intelligence ingestion pipeline.")
    parser.add_argument("--input-dir", type=str, required=True, help="Directory containing source PDFs.")
    parser.add_argument("--output-dir", type=str, required=True, help="Root directory for artifacts.")
    default_workers = os.cpu_count() or 4
    parser.add_argument("--num-workers", type=int, default=default_workers, help="Number of parallel PROCESSES for processing.")
    parser.add_argument("--force-reprocess", action="store_true", help="Force reprocessing.")
    parser.add_argument("--log-file", type=str, default=None, help="Optional log file path.")
    args = parser.parse_args()

    # Logging Setup
    log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(processName)s] - %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) # <--- Changed from INFO to DEBUG
    root_logger.handlers.clear()
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file, mode='w', encoding='utf-8')
        file_handler.setFormatter(log_formatter)
        root_logger.addHandler(file_handler)
    
    # Pipeline Initialization
    logging.info("--- Phase 0: Process-Safe Parallel Ingestion Pipeline Started ---")
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with open("config.yml", 'r') as f: config = yaml.safe_load(f)
    pdf_files = list(input_dir.glob("*.pdf"))
    logging.info(f"Found {len(pdf_files)} PDFs. Using up to {args.num_workers} parallel processes.")

    # Parallel Execution with Processes
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.num_workers) as executor:
        future_to_pdf = {
            executor.submit(process_single_document, pdf, output_dir, config, args.force_reprocess): pdf
            for pdf in pdf_files
        }
        
        for future in tqdm(concurrent.futures.as_completed(future_to_pdf), total=len(pdf_files), desc="Processing Documents"):
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                pdf_path = future_to_pdf[future]
                logging.error(f"A top-level exception occurred for {pdf_path.name}: {exc}", exc_info=True)
                results.append((pdf_path.stem, "failed", str(exc)))

    # Final Summary
    success_count = sum(1 for _, status, _ in results if status == "success")
    skipped_count = sum(1 for _, status, _ in results if status == "skipped")
    failed_count = sum(1 for _, status, _ in results if status == "failed")
    logging.info("--- Phase 0: Ingestion Pipeline COMPLETED ---")
    logging.info(f"Total: {len(pdf_files)}, Succeeded: {success_count}, Skipped: {skipped_count}, Failed: {failed_count}")
    if failed_count > 0:
        logging.warning("Failed documents:")
        for doc_id, status, msg in results:
            if status == "failed":
                # Ensure the message is clean for logging
                clean_msg = str(msg).splitlines()[0]
                logging.warning(f"  - {doc_id}: {clean_msg}")

if __name__ == "__main__":
    main()
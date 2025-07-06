# FILE: src/database_loaders/pinecone_loader.py
# Kilo-Architect - Strategic Pinecone Ingestion Orchestrator V3.1

"""
This script orchestrates the ingestion of enriched document chunks into a Pinecone
vector database.

V3.1 Changes:
- Added logic to create a lookup for raw table markdown representation.
- Injects the 'raw_table_content' into table summary chunks to enable
  full traceability, passing the necessary data to the utils module.
"""
# --- BOOTSTRAP: Load environment variables BEFORE any other imports ---
from dotenv import load_dotenv
load_dotenv()
# --- END BOOTSTRAP ---

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Set

from pinecone import Pinecone

# --- MODULE IMPORTS (Adhering to our modular architecture) ---
try:
    from .vector_generator import create_multi_vector_payload
    from .utils import create_pinecone_metadata
except ImportError as e:
    print(f"FATAL: A module import failed. This usually means a sub-module has an incorrect import path. Error: {e}")
    print("Ensure this script is run as a module from the project root (e.g., python -m src.database_loaders.pinecone_loader)")
    sys.exit(1)


# --- CONFIGURATION & CONSTANTS ---
BATCH_SIZE = 100

def _setup_logger(log_file: Path) -> None:
    # (No changes to this function)
    log_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)
    logging.info(f"Logging to console and file: {log_file}")

def _load_state(state_file_path: Path) -> Dict[str, Set[str]]:
    # (No changes to this function)
    if state_file_path.exists():
        with open(state_file_path, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
        processed_state = {filename: set(ids) for filename, ids in state_data.items()}
        total_processed = sum(len(ids) for ids in processed_state.values())
        logging.info(f"Loaded state from {state_file_path}. Found {total_processed} previously processed chunk IDs across {len(processed_state)} files.")
        return processed_state
    return {}

def _save_state(state_file_path: Path, processed_state: Dict[str, Set[str]]):
    # (No changes to this function)
    state_to_save = {filename: list(ids) for filename, ids in processed_state.items()}
    with open(state_file_path, 'w', encoding='utf-8') as f:
        json.dump(state_to_save, f, indent=4)


def main():
    """Main function to execute the Pinecone ingestion pipeline."""
    # (Argument parsing is unchanged)
    parser = argparse.ArgumentParser(description="Pinecone Ingestion Orchestrator for Hybrid RAG.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Path to the directory containing enriched chunk JSON files.")
    parser.add_argument("--pinecone-index-name", type=str, required=True, help="Name of the target Pinecone index.")
    parser.add_argument("--log-file", type=Path, default=Path("pinecone_loader.log"), help="Path to the log file.")
    parser.add_argument("--state-file", type=Path, default=Path("upload_status.json"), help="Path to the state file for idempotency.")
    parser.add_argument("--force-reupload", action="store_true", help="Force re-upload of all chunks, ignoring the state file.")
    args = parser.parse_args()

    _setup_logger(args.log_file)
    # (Pinecone connection logic is unchanged)
    PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
    PINECONE_HOST = os.environ.get("PINECONE_HOST")

    if not PINECONE_API_KEY or not PINECONE_HOST:
        logging.critical("PINECONE_API_KEY and PINECONE_HOST must be set in your .env file.")
        return

    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        pinecone_index = pc.Index(host=PINECONE_HOST)
        pinecone_index.describe_index_stats()
        logging.info("Successfully connected to Pinecone index.")
    except Exception as e:
        logging.critical(f"Failed to connect to Pinecone. Please check your API Key and Host URL. Error: {e}")
        return

    processed_state = {} if args.force_reupload else _load_state(args.state_file)
    if args.force_reupload: logging.warning("`--force-reupload` is active.")

    json_files = sorted(list(args.input_dir.glob("*.json")))
    logging.info(f"Found {len(json_files)} JSON files to process in {args.input_dir}.")

    for json_file in json_files:
        filename = json_file.name
        logging.info(f"--- Processing file: {filename} ---")
        
        with open(json_file, 'r', encoding='utf-8') as f:
            document_data = json.load(f)

        if "document_level_metadata" not in document_data or "chunks" not in document_data:
            logging.error(f"Skipping malformed file {filename}: Missing 'document_level_metadata' or 'chunks' keys.")
            continue

        doc_meta = document_data["document_level_metadata"]
        enriched_chunks = document_data["chunks"]

        try:
            resolved_date = datetime.fromisoformat(doc_meta.get("publication_date", ""))
            date_source = doc_meta.get("date_source", "unknown")
            logging.info(f"Using document date {resolved_date.date()} from source '{date_source}' for '{doc_meta.get('doc_id')}'")
        except (ValueError, TypeError):
            logging.warning(f"Could not parse date from document metadata. Using default for '{doc_meta.get('doc_id')}'.")
            resolved_date = datetime(1970, 1, 1)

        # V3.1 ADDITION: Create a lookup for raw table markdown for traceability.
        # Note: This assumes table data is in 'document_level_metadata', which may
        # need to be adjusted based on the upstream enrichment process.
        table_markdown_lookup = {
            table['table_id']: table['markdown_representation']
            for table in doc_meta.get('tables', [])
            if 'table_id' in table and 'markdown_representation' in table
        }
        if table_markdown_lookup:
            logging.info(f"Created a lookup for {len(table_markdown_lookup)} raw table representations.")

        processed_chunk_ids_for_file = processed_state.get(filename, set())

        total_chunks_in_file = len(enriched_chunks)
        chunks_to_process = [c for c in enriched_chunks if c.get('chunk_id') not in processed_chunk_ids_for_file]
        
        if not chunks_to_process:
            logging.info(f"All {total_chunks_in_file} chunks in {filename} have already been processed. Skipping.")
            continue

        logging.info(f"Found {len(chunks_to_process)} new chunks to process in {filename}.")
        batch_to_upsert: List[Dict] = []
        chunk_ids_in_current_batch: Set[str] = set()

        try:
            for i, chunk in enumerate(chunks_to_process):
                chunk_id = chunk.get("chunk_id")
                logging.info(f"[{i+1}/{len(chunks_to_process)}] Processing chunk {chunk_id}...")

                # V3.1 FIX: Add the raw table content to the chunk's metadata before processing.
                chunk_meta = chunk.get("metadata", {})
                if chunk_meta.get("chunk_type") == "table_summary":
                    table_id = chunk_meta.get("table_id")
                    if table_id and table_id in table_markdown_lookup:
                        chunk["metadata"]["raw_table_content"] = table_markdown_lookup[table_id]
                        logging.debug(f"Injected raw markdown for table {table_id} into chunk {chunk_id}.")
                    else:
                        logging.warning(f"Could not find raw markdown for table_id {table_id}. Traceability may be incomplete.")
                
                multi_vector_payload = create_multi_vector_payload(chunk)
                if not multi_vector_payload:
                    logging.warning(f"Skipping chunk {chunk_id} as no vectors could be generated.")
                    continue
                
                metadata = create_pinecone_metadata(chunk, resolved_date)

                for vector_type, vector_values in multi_vector_payload.items():
                    structured_id = f"{chunk_id}::{vector_type}"
                    batch_to_upsert.append({"id": structured_id, "values": vector_values, "metadata": metadata})
                
                chunk_ids_in_current_batch.add(chunk_id)
                
                if len(chunk_ids_in_current_batch) >= BATCH_SIZE:
                    logging.info(f"Batch full. Upserting {len(batch_to_upsert)} vectors...")
                    doc_id_namespace = metadata.get("doc_id", "default_namespace")
                    pinecone_index.upsert(vectors=batch_to_upsert, namespace=doc_id_namespace)
                    processed_chunk_ids_for_file.update(chunk_ids_in_current_batch)
                    processed_state[filename] = processed_chunk_ids_for_file
                    _save_state(args.state_file, processed_state)
                    logging.info(f"Upsert successful.")
                    batch_to_upsert.clear()
                    chunk_ids_in_current_batch.clear()
                    time.sleep(1)
        finally:
            if batch_to_upsert:
                logging.info(f"Upserting final batch of {len(batch_to_upsert)} vectors for {filename}...")
                last_metadata = batch_to_upsert[-1]['metadata']
                doc_id_namespace = last_metadata.get("doc_id", "default_namespace")
                pinecone_index.upsert(vectors=batch_to_upsert, namespace=doc_id_namespace)
                processed_chunk_ids_for_file.update(chunk_ids_in_current_batch)
                processed_state[filename] = processed_chunk_ids_for_file
                logging.info(f"Final batch upsert for {filename} successful.")
            _save_state(args.state_file, processed_state)
            logging.info(f"--- Finished processing file: {filename}. ---")
    logging.info("--- All files processed. Pinecone ingestion finished. ---")

if __name__ == "__main__":
    main()
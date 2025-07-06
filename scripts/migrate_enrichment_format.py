# FILE: scripts/migrate_enrichment_format.py
# Kilo-Architect - Data Reconciliation & Migration Utility V2.0

"""
This is an advanced migration script that solves the data traceability problem
by acting as a data reconciler.

It reads BOTH the original master_record.json (to get the raw table data and
other ground-truth metadata) and an existing enriched_chunks file (to get the
LLM analysis). It then merges them into a single, complete, and
architecturally-correct V3.x format file, ready for the final pinecone_loader.
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
import re

# --- Standalone Date Parsing Logic (self-contained for portability) ---
def _extract_date_from_doc_id(doc_id: str) -> datetime:
    """Parses a date from a document ID string. Supports multiple common formats."""
    # Case 1: Month and Year (e.g., 11-2022, 03-2023)
    match = re.search(r'(\d{1,2})-(\d{4})', doc_id)
    if match:
        try: return datetime.strptime(f"{match.group(1)}-{match.group(2)}", "%m-%Y")
        except ValueError: pass

    # Case 2: Month name and Year (e.g., nov-2024, March-2025)
    match = re.search(r'([a-zA-Z]{3,})-(\d{4})', doc_id, re.IGNORECASE)
    if match:
        try: return datetime.strptime(f"{match.group(1)}-{match.group(2)}", "%b-%Y")
        except ValueError:
            try: return datetime.strptime(f"{match.group(1)}-{match.group(2)}", "%B-%Y")
            except ValueError: pass
    
    # Case 3 - Look for a standalone 4-digit year.
    match = re.search(r'\b(20\d{2})\b', doc_id)
    if match:
        try: return datetime.strptime(match.group(1), "%Y")
        except ValueError: pass
            
    logging.warning(f"Could not parse a date from doc_id '{doc_id}'. Using default date.")
    return datetime(1970, 1, 1)

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] - %(message)s")

    parser = argparse.ArgumentParser(description="Reconciles master record and enriched chunks into the new Global Metadata format.")
    # V2.0 Change: Uses a directory-based approach for robustness
    parser.add_argument("--artifacts-dir", type=Path, required=True, help="Path to a single document's _artifacts directory (e.g., .../pbac_guidelines_version_5_artifacts/).")
    parser.add_argument("--enriched-chunks-filename", type=str, default="enriched_chunks_v5.json", help="The name of the enriched chunks file to read.")
    parser.add_argument("--output-filename", type=str, default="enriched_chunks_v7_reconciled.json", help="The name for the new, corrected output file.")
    args = parser.parse_args()

    # --- File Validation ---
    master_record_path = args.artifacts_dir / "master_record.json"
    enriched_chunks_path = args.artifacts_dir / args.enriched_chunks_filename

    if not master_record_path.exists() or not enriched_chunks_path.exists():
        logging.error(f"FATAL: Missing required files. Check for '{master_record_path}' and '{enriched_chunks_path}'.")
        sys.exit(1)

    # --- Load All Required Data Sources ---
    logging.info(f"Loading master record from: {master_record_path}")
    with open(master_record_path, 'r', encoding='utf-8') as f:
        master_record = json.load(f)
        
    logging.info(f"Loading enriched chunks from: {enriched_chunks_path}")
    with open(enriched_chunks_path, 'r', encoding='utf-8') as f:
        enriched_chunks = json.load(f)

    # --- Core Reconciliation & Migration Logic ---
    doc_id = master_record.get("doc_id", "unknown_doc")
    publication_date = _extract_date_from_doc_id(doc_id)
    
    # Create a lookup for raw table data from the master record. This is key.
    table_markdown_lookup = {
        table.get('table_id'): table.get('markdown_representation')
        for table in master_record.get('tables', [])
        if 'table_id' in table and 'markdown_representation' in table
    }
    logging.info(f"Found {len(table_markdown_lookup)} raw table representations in master record.")
    
    # Iterate through the chunks and inject the missing raw content where needed
    for chunk in enriched_chunks:
        chunk_meta = chunk.get("metadata", {})
        if chunk_meta.get("chunk_type") == "table_summary":
            table_id = chunk_meta.get("table_id")
            if table_id in table_markdown_lookup:
                # This is the reconciliation step: adding the lost data back in.
                chunk["metadata"]["raw_table_content"] = table_markdown_lookup[table_id]
            else:
                logging.warning(f"Could not find a matching table in master_record for table_id: {table_id}")

    # Build the new, complete V7 data structure
    new_format_data = {
        "document_level_metadata": {
            "doc_id": doc_id,
            "publication_date": publication_date.isoformat(),
            "date_source": "derived_from_filename" if publication_date.year != 1970 else "default_fallback",
            "source_files": {
                "master_record": "master_record.json",
                "enriched_chunks": args.enriched_chunks_filename
            },
            # This is critical: we carry the full table data forward at the doc level.
            "tables": master_record.get("tables", [])
        },
        "chunks": enriched_chunks
    }
    
    logging.info(f"Successfully reconciled and created new data structure for doc_id: {doc_id}")
    
    # Write the new, reconciled file
    output_path = args.artifacts_dir / args.output_filename
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(new_format_data, f, indent=4)
        
    logging.info(f"Successfully saved corrected data to: {output_path}")

if __name__ == "__main__":
    main()
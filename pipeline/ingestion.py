# pipeline/ingestion.py

"""
Document ingestion module with de-duplication logic.
-----------------------------------------------------
This script walks through the input folder, filters by supported file types,
and returns a clean list of unique document paths for processing.

De-duplication Strategy:
- It identifies files with the same base name but different extensions (e.g.,
  'report.pdf' and 'report.docx').
- It prioritizes the PDF version, as it is considered the most reliable
  source of truth for document structure and content.
- This ensures each document is processed only once, saving API quota and
  preventing duplicate entries in the final search index.
"""

import os
from collections import defaultdict
from typing import List, Dict

def ingest_documents(input_folder: str, supported_formats: List[str], logger=None) -> List[str]:
    """
    Walks the input folder, collects supported files, and de-duplicates them,
    prioritizing PDF files over other formats.
    
    Args:
        input_folder (str): Root directory to search for documents.
        supported_formats (List[str]): List of supported extensions (e.g., ['pdf', 'docx']).
        logger (optional): Logger instance for logging events.

    Returns:
        A de-duplicated list of valid document file paths.
    """
    if not os.path.isdir(input_folder):
        if logger:
            logger.error(f"Input folder not found: {input_folder}")
        raise ValueError(f"Input folder not found: {input_folder}")

    # Use a dictionary to group files by their base name (without extension)
    found_files: Dict[str, Dict[str, str]] = defaultdict(dict)
    
    for root, _, files in os.walk(input_folder):
        for fname in files:
            base_name, ext = os.path.splitext(fname)
            ext_lower = ext.lower().replace('.', '')
            
            if ext_lower in supported_formats:
                full_path = os.path.join(root, fname)
                # Store the file path keyed by its extension
                found_files[base_name][ext_lower] = full_path

    # Now, de-duplicate the list based on our prioritization rule
    final_documents_to_process: List[str] = []
    for base_name, file_group in found_files.items():
        if 'pdf' in file_group:
            # If a PDF exists, it's the source of truth. Add it and ignore others.
            selected_file = file_group['pdf']
            if logger and len(file_group) > 1:
                logger.info(f"De-duplication: Found multiple versions for '{base_name}'. Prioritizing PDF: {os.path.basename(selected_file)}")
            final_documents_to_process.append(selected_file)
        else:
            # If no PDF, just add the first available supported format found.
            # This handles cases where only a .docx or .txt exists.
            # We take the first item from the dictionary's values.
            selected_file = next(iter(file_group.values()))
            final_documents_to_process.append(selected_file)

    if logger:
        logger.info(f"Ingestion complete. Found {len(final_documents_to_process)} unique documents to process.")

    return final_documents_to_process

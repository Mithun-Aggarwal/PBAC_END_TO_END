# pipeline/utils.py

"""
Utility functions for the document processing pipeline.
Includes helpers for chunking, logging, text manipulation, and PDF splitting.
"""

import os
import logging
import fitz  # PyMuPDF
from typing import List, Dict

# --- Logging Setup ---

def setup_logger(name, log_file, level=logging.INFO):
    """
    Sets up a logger that writes to both a file and the console.
    """
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))

    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
        
    return logger

# --- PDF Handling ---

def get_pdf_page_count(pdf_path: str, logger: logging.Logger) -> int:
    """
    Safely returns the number of pages in a PDF document.
    Returns 0 if the file is corrupt or unreadable, allowing it to be skipped.
    """
    try:
        with fitz.open(pdf_path) as doc:
            return doc.page_count
    except Exception as e:
        logger.error(f"Could not read PDF '{os.path.basename(pdf_path)}': {e}. Skipping file.")
        return 0

def split_pdf(pdf_path: str, max_pages: int, output_dir: str, logger: logging.Logger) -> List[str]:
    """
    Splits a large PDF into smaller sub-documents.
    """
    split_pdf_paths = []
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    
    try:
        with fitz.open(pdf_path) as doc:
            total_pages = doc.page_count
            logger.info(f"Splitting large PDF '{base_name}.pdf' ({total_pages} pages) into chunks of max {max_pages} pages.")
            
            for i in range(0, total_pages, max_pages):
                start_page = i
                end_page = min(i + max_pages - 1, total_pages - 1)
                
                part_num = (i // max_pages) + 1
                new_pdf_name = f"{base_name}_part_{part_num}.pdf"
                new_pdf_path = os.path.join(output_dir, new_pdf_name)

                with fitz.open() as new_doc:
                    new_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)
                    new_doc.save(new_pdf_path)
                    
                split_pdf_paths.append(new_pdf_path)
                logger.info(f"  -> Created part {part_num}: '{new_pdf_name}' with pages {start_page+1}-{end_page+1}")

    except Exception as e:
        logger.error(f"Failed to split PDF {pdf_path}: {e}", exc_info=True)
        return []

    return split_pdf_paths


# --- Text Processing & Embedding Helpers ---
def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    if not text:
        return []
    tokens = text.split()
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + chunk_size
        chunk = ' '.join(tokens[start:end])
        chunks.append(chunk)
        start += chunk_size - chunk_overlap
        if start >= len(tokens):
            break
    return chunks

def extract_title_from_text(text: str) -> str:
    lines = text.strip().split('\n')
    for line in lines:
        cleaned = line.strip()
        if cleaned and (len(cleaned.split()) <= 15):
            return cleaned
    return "Untitled Document"

def log_embedding_stats(doc_path: str, results: List[Dict], logger=None):
    if not logger or not results:
        return
    total_chunks = len(results)
    failed_chunks = sum(1 for r in results if not r.get("embedding"))
    if total_chunks > 0 and total_chunks > failed_chunks:
        avg_dims = sum(len(r["embedding"]) for r in results if r.get("embedding")) / (total_chunks - failed_chunks)
    else:
        avg_dims = 0
    logger.info(f"Embedding Stats for: {os.path.basename(doc_path)}")
    logger.info(f"  - Total Chunks Processed: {total_chunks}")
    logger.info(f"  - Failed Chunks: {failed_chunks}")
    logger.info(f"  - Average Vector Dimensions: {avg_dims:.0f}")
    if failed_chunks > 0:
        logger.warning(f"  ⚠️ {failed_chunks} chunks failed to embed and will be excluded from the final output.")

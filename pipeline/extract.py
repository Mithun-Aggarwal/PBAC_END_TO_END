# pipeline/extract.py

"""
Document extraction module: extracts raw text and structured content from PDFs.
Includes dynamic, content-aware chunking and OCR fallback.
"""

import os
import fitz  # PyMuPDF
import docx
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
from typing import Tuple, Dict, List, Any
from datetime import datetime

def extract_text_and_chunks(file_path: str, config: Dict) -> Tuple[List[Dict[str, Any]], Dict]:
    """
    Extracts structured content from a document and performs dynamic chunking.

    Args:
        file_path (str): Full path to the document.
        config (Dict): Parsed configuration settings.

    Returns:
        Tuple[List[Dict[str, Any]], Dict]: A list of page content and basic metadata.
    """
    ext = os.path.splitext(file_path)[1].lower().replace('.', '')
    pages_content = []
    meta = {
        "source_file": os.path.basename(file_path),
        "extension": ext,
        "extracted_at": datetime.now().isoformat(),
        "pages": 0,
    }

    if ext == 'pdf':
        pages_content, pages = extract_pdf_structured(file_path, config)
        meta["pages"] = pages
    elif ext == 'docx':
        # For now, we'll just get the raw text for docx
        text = extract_docx(file_path)
        pages_content.append({"page_number": 1, "chunks": [{"chunk_id": "doc_1_chunk_0", "text": text, "chunk_type": "paragraph"}]})
        meta["pages"] = 1
    elif ext == 'txt':
        text = extract_txt(file_path)
        pages_content.append({"page_number": 1, "chunks": [{"chunk_id": "doc_1_chunk_0", "text": text, "chunk_type": "paragraph"}]})
        meta["pages"] = 1
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    return pages_content, meta


def extract_pdf_structured(file_path: str, config: Dict) -> Tuple[List[Dict[str, Any]], int]:
    """
    Extracts structured content from a PDF using PyMuPDF for text extraction
    and OCR fallback.
    """
    doc = fitz.open(file_path)
    document_pages = []
    ocr_enabled = config.get("enable_ocr", False)
    lang = "+".join(config.get("ocr_languages", ["eng"]))
    doc_id = os.path.splitext(os.path.basename(file_path))[0]

    for page_num, page in enumerate(doc):
        page_content = {"page_number": page_num + 1, "chunks": []}
        chunk_id_counter = 0
        
        page_text = page.get_text()
        if not page_text.strip() and ocr_enabled:
            images = convert_from_path(file_path, first_page=page_num + 1, last_page=page_num + 1)
            ocr_text = ""
            for image in images:
                ocr_text += pytesseract.image_to_string(image, lang=lang)
            
            if ocr_text.strip():
                page_content["chunks"].append({
                    "chunk_id": f"{doc_id}_page_{page_num + 1}_chunk_{chunk_id_counter}",
                    "text": ocr_text,
                    "chunk_type": "ocr_text"
                })
                chunk_id_counter += 1
        elif page_text.strip():
            # Simple chunking: one chunk per page
            page_content["chunks"].append({
                "chunk_id": f"{doc_id}_page_{page_num + 1}_chunk_{chunk_id_counter}",
                "text": page_text.strip(),
                "chunk_type": "paragraph"
            })
            chunk_id_counter += 1

        if page_content["chunks"]:
            document_pages.append(page_content)

    return document_pages, len(doc)


def extract_docx(file_path: str) -> str:
    """Extract text from DOCX using python-docx."""
    doc = docx.Document(file_path)
    text = "\n".join([para.text for para in doc.paragraphs])
    return text


def extract_txt(file_path: str) -> str:
    """Read plain text file."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

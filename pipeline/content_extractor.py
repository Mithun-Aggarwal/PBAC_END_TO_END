# pipeline/content_extractor.py

import os
import json
import fitz  # PyMuPDF
import docx # python-docx
import pandas as pd
import logging
from pipeline.date_extractor import DateExtractor
from pipeline.extract_pbac_metadata import enrich_with_metadata

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_text_from_pdf(file_path):
    # Existing PDF extraction logic
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text

def extract_text_from_docx(file_path):
    doc = docx.Document(file_path)
    text = "\n".join([para.text for para in doc.paragraphs])
    return text

def extract_text_from_txt(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def extract_text_from_excel(file_path):
    xls = pd.ExcelFile(file_path)
    text = ""
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        text += df.to_string()
    return text

def get_content_extractor(file_extension):
    """Returns the appropriate content extraction function."""
    if file_extension == ".pdf":
        return extract_text_from_pdf
    elif file_extension == ".docx":
        return extract_text_from_docx
    elif file_extension in [".txt", ".md"]:
        return extract_text_from_txt
    elif file_extension in [".xls", ".xlsx"]:
        return extract_text_from_excel
    else:
        return None

def process_page(page_path, output_path):
    """
    Processes a single page: extracts content, enriches it with metadata, and saves it as JSON.
    """
    try:
        page_text = extract_text_from_pdf(page_path)
        
        # Extract date
        date_extractor = DateExtractor(page_path, page_text)
        date_info = date_extractor.extract_date()

        # Enrich with other metadata
        metadata = enrich_with_metadata(page_text, page_path)

        output_data = {
            "source_page": page_path,
            "raw_text": page_text,
            **date_info,
            **metadata
        }

        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=4)
        logging.info(f"Successfully saved JSON output to {output_path}")

    except Exception as e:
        logging.error(f"Failed to process page {page_path}: {e}")


def process_file(source_path, output_path):
    """
    Processes a single non-PDF file: extracts content and saves it as JSON.
    """
    file_extension = os.path.splitext(source_path)[1]
    extractor = get_content_extractor(file_extension)

    if not extractor:
        logging.warning(f"No extractor found for {file_extension}. Skipping {source_path}.")
        return

    try:
        raw_text = extractor(source_path)
        
        date_extractor = DateExtractor(source_path, raw_text)
        date_info = date_extractor.extract_date()

        output_data = {
            "source_file": source_path,
            "raw_text": raw_text,
            **date_info
        }

        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=4)
        logging.info(f"Successfully saved JSON output to {output_path}")

    except Exception as e:
        logging.error(f"Failed to process {source_path}: {e}")
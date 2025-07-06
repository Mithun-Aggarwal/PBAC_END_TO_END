# pipeline/local_extractor.py

"""
Local LLM Extractor Module using Ollama
---------------------------------------
This script uses a locally-run model via Ollama (e.g., Llama 3) to perform
structured data extraction from documents.

Workflow:
1.  Reads a PDF document page by page to handle large files and keep
    context windows small and fast.
2.  For each page, sends the text content to the local Ollama API.
3.  Instructs the local model to extract specific metadata fields and respond
    in a structured JSON format.
4.  Aggregates the extracted information from all pages into a single,
    consolidated JSON object for the entire document.
5.  This approach is cost-effective, avoids API rate limits, and is highly
    resilient to failures on individual pages.
"""

import os
import json
import requests
import fitz  # PyMuPDF
import logging
from datetime import datetime
from typing import Dict, Any, List

# This prompt is designed for per-page analysis. It asks the model to only
# extract information it can see on the current page.
SYSTEM_PROMPT_PER_PAGE = """
You are a specialist analyst for the Australian Pharmaceutical Benefits Advisory Committee (PBAC).
Your task is to extract key metadata from the single page of text provided.
Respond ONLY with a single, valid JSON object. Do not include any other text or explanations.

From the text on THIS PAGE ONLY, extract the following fields. If a field is not mentioned on this page, use a null value.
- "title": The main title of the document, if present on this page.
- "doc_type": If identifiable, one of: [PSD, Guideline, Meeting Outcome, Cost Manual, Consultation Input, Newsletter, Misc].
- "pbac_meeting_date": The date of a PBAC meeting, if mentioned.
- "drug_name": The primary drug or therapeutic product discussed.
- "sponsor": The company or entity that sponsored the submission.
- "indication": The medical condition or reason for using the drug.
- "outcome": The final decision or outcome (e.g., "Recommended", "Rejected").
- "page_sections": A list of any distinct sections on this page. Each item in the list should be an object with a "heading" and "text" key.
"""

def _merge_results(page_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merges metadata extracted from individual pages into a single, consolidated document object.
    
    It prioritizes the first non-null value found for single-value fields (like 'title')
    and concatenates list-based fields (like 'sections').
    """
    if not page_results:
        return {}

    final_result = {
        "title": None,
        "doc_type": None,
        "pbac_meeting_date": None,
        "drug_name": None,
        "sponsor": None,
        "indication": None,
        "outcome": None,
        "sections": []
    }
    
    # Single-value fields: take the first valid value found
    for key in ["title", "doc_type", "pbac_meeting_date", "drug_name", "sponsor", "indication", "outcome"]:
        for res in page_results:
            if res.get(key):
                final_result[key] = res[key]
                break
    
    # List-based fields: combine all entries
    page_offset = 0
    for res in page_results:
        page_sections = res.get("page_sections", [])
        if isinstance(page_sections, list):
            for section in page_sections:
                if isinstance(section, dict) and "heading" in section and "text" in section:
                    section['page_start'] = page_offset + 1 # Add page number
                    final_result["sections"].append(section)
        page_offset += 1
        
    return final_result


def extract_metadata_local(file_path: str, config: Dict[str, Any], logger: logging.Logger) -> Dict[str, Any]:
    """
    Extracts structured metadata from a PDF using a local Ollama model,
    processing the document page by page.
    """
    local_config = config.get('extraction', {}).get('local', {})
    model_name = local_config.get('model', 'llama3:8b')
    ollama_url = local_config.get('ollama_url')
    timeout = local_config.get('request_timeout', 120)

    if not ollama_url:
        return {"error": "Ollama URL not configured in config.yaml"}

    page_results = []

    try:
        doc = fitz.open(file_path)
        logger.info(f"Starting local extraction for '{os.path.basename(file_path)}' ({len(doc)} pages) using {model_name}.")

        for i, page in enumerate(doc):
            page_text = page.get_text("text")
            if not page_text.strip():
                continue

            try:
                # Use the json format feature for reliable output
                response = requests.post(
                    ollama_url,
                    json={
                        "model": model_name,
                        "format": "json",
                        "stream": False,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT_PER_PAGE},
                            {"role": "user", "content": f"Here is the text from page {i+1}:\n\n---\n\n{page_text}"}
                        ]
                    },
                    timeout=timeout
                )
                response.raise_for_status()
                
                # The response content is a JSON string, so we parse it directly
                page_data = json.loads(response.json().get("message", {}).get("content", "{}"))
                page_results.append(page_data)

            except requests.RequestException as e:
                logger.error(f"Ollama request failed on page {i+1} of {os.path.basename(file_path)}: {e}")
                continue # Skip to the next page
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from Ollama on page {i+1}: {e}")
                continue

        doc.close()
        
        if not page_results:
            return {"error": "No data could be extracted from any page."}

        # Merge results from all pages into a final object
        final_data = _merge_results(page_results)
        final_data["source"] = file_path
        final_data["extracted_at"] = datetime.now().isoformat()
        
        logger.info(f"Successfully completed local extraction for '{os.path.basename(file_path)}'.")
        return final_data

    except Exception as e:
        logger.error(f"A critical error occurred during local extraction for {file_path}: {e}", exc_info=True)
        return {"error": f"Critical failure in local extraction: {e}"}

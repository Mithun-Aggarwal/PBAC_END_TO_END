import os
import json
import requests
from datetime import datetime
from typing import Dict, Any
import sys
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.utils import extract_title_from_text

OLLAMA_CHAT_URL = os.getenv("OLLAMA_CHAT_URL", "http://localhost:11434/api/chat")
MODEL = "llama3:8b"

# --- System prompt ---
system_prompt = (
    "You are a senior policy analyst working with the Australian Department of Health. "
    "Your job is to extract structured metadata from PBAC-related documents.\n"
    "Given a full document, return ONLY a single valid JSON object with the following fields:\n"
    "- doc_id\n- title\n- doc_type\n- submission_type\n- pbac_meeting_date\n- drug_name\n- sponsor\n"
    "- indication\n- outcome\n- source\n- topics\n- sections (with heading, text, page_start, semantic_tags[])"
)

def extract_json_object(text: str) -> dict:
    """
    Extracts the first valid JSON object from a string by finding balanced curly braces.
    """
    try:
        brace_level = 0
        start_index = -1
        
        for i, char in enumerate(text):
            if char == '{':
                if start_index == -1:
                    start_index = i
                brace_level += 1
            elif char == '}':
                if start_index != -1:
                    brace_level -= 1
                    if brace_level == 0:
                        potential_json = text[start_index : i + 1]
                        try:
                            return json.loads(potential_json)
                        except json.JSONDecodeError:
                            # Reset and continue searching for another JSON object
                            start_index = -1
        
    except Exception as e:
        return {"error": f"JSON extraction failed: {str(e)}"}

    raise ValueError("No valid JSON object found in response.")

def enrich_with_metadata(text: str, source_file: str, page_count: int = 1) -> Dict[str, Any]:
    if not text or len(text.strip()) < 30:
        return {"error": "Text too short for enrichment."}

    title = extract_title_from_text(text)

    prompt = (
        f"Filename: {os.path.basename(source_file)}\n"
        f"Total pages: {page_count}\n"
        f"Title (guess): {title}\n"
        f"\n---\n\n{text}\n\n---"
    )

    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt[:10000]}
                ]
            },
            timeout=300
        )
        response.raise_for_status()
        
        # The response is now a single JSON object
        response_data = response.json()
        raw_response = response_data.get("message", {}).get("content", "")
        structured = extract_json_object(raw_response)

        structured.setdefault("source", source_file)
        structured.setdefault("page_count", page_count)
        structured.setdefault("extracted_at", datetime.now().isoformat())
        return structured

    except Exception as e:
        return {"error": f"LLM enrichment failed: {str(e)}"}

# Example usage
if __name__ == "__main__":
    with open("/home/mit/Learning_and_growing/AI_DATA_EXTRACTION_AND_SEARCH_V1/Curated_information/documents/golden_dataset/Asthma-Stakeholder-Meeting-Dec-2018-Outcome-Statement.json") as f:
        data = json.load(f)
        result = enrich_with_metadata(data["text"], data.get("source_file", "sample_doc.json"), data.get("page_count", 1))
        print(json.dumps(result, indent=2))
# doc_classifier.py

"""
Document Classifier & Metadata Extractor for PBAC Documents
- Uses local LLM via Ollama (e.g., mistral)
- Outputs document type, date, drug name, summary, and topics
- Designed for integration into the main processing pipeline
"""

import os
import json
from datetime import datetime
import requests

from dotenv import load_dotenv
load_dotenv()

OLLAMA_CHAT_URL = os.getenv("OLLAMA_CHAT_URL", "http://localhost:11434/api/chat")

# --- Prompt Template ---
CLASSIFIER_PROMPT = """
You are a domain expert assistant helping classify PBAC-related government documents.
Given a document snippet, respond in JSON with the following fields:

- Document Type: One of [GUIDELINE, PSD, MEETING_OUTCOME, COST_MANUAL, CONSULTATION_INPUT, NEWSLETTER, MISC]
- Date: [If available, else null]
- Related Drug: [Name of the main drug, if mentioned, else null]
- Topics: [List of up to 4 keywords: e.g., access, clinical data, cost-effectiveness]
- Summary: [2–3 sentence factual summary of the document]

Respond only with a valid JSON object.
"""

def classify_document(text: str, model: str = "mistral") -> dict:
    if not text or len(text.strip()) < 100:
        return {"error": "Text too short for classification"}

    truncated = text[:1500]

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a government document classification expert."},
            {"role": "user", "content": f"{CLASSIFIER_PROMPT}\n\nText:\n{truncated}"}
        ]
    }

    try:
        response = requests.post(OLLAMA_CHAT_URL, json=payload)
        response.raise_for_status()
        content = response.json()["message"]["content"]
        return json.loads(content)
    except Exception as e:
        return {"error": str(e)}

def enrich_with_metadata(text: str, source_file: str, page_count: int) -> dict:
    llm_result = classify_document(text)
    now = datetime.now().isoformat()

    return {
        "metadata": {
            "source_file": source_file,
            "page_count": page_count,
            "extracted_at": now,
            **llm_result
        },
        "text": text
    }

# Example usage (for test file or batch mode):
if __name__ == "__main__":
    with open("/home/mit/Learning_and_growing/AI_DATA_EXTRACTION_AND_SEARCH_V1/Curated_information/documents/output_folder/pbac_guidelines_version_5.json") as f:
        data = json.load(f)
        result = enrich_with_metadata(data["text"], data["source_file"], data.get("page_count", 1))
        print(json.dumps(result, indent=2))

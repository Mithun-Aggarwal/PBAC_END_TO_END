# llm_processor.py

"""
LLM Post-Processing Module: Supports summarization, tagging, and classification
using Gemini (or pluggable API endpoints). Can be extended for OpenAI or local models.
"""

import os
import requests
import json
from typing import Dict

def run_llm_processing(clean_text: str, config: Dict) -> Dict:
    """
    Processes cleaned text using a configured LLM API (Gemini by default).

    Args:
        clean_text (str): Text to process
        config (Dict): Config with model info and options

    Returns:
        Dict: Structured output such as summary, tags, classification
    """
    if not clean_text or len(clean_text.strip()) < 30:
        return {"summary": "", "tags": [], "classification": "n/a"}

    api_key = os.getenv("GEMINI_API_KEY")
    model = config.get("llm_model", "gemini-pro")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    prompt = {
        "contents": [{
            "parts": [{
                "text": (
                    "You are a document analyst helping summarize Australian government and health regulatory documents.\n"
                    "Return a JSON object with:\n"
                    "1. A concise 4-5 sentence summary.\n"
                    "2. Up to 5 suggested semantic tags.\n"
                    "3. A classification label (e.g., 'PBAC PSD', 'Policy Manual', 'Cost Table').\n\n"
                    f"Document:\n{clean_text[:4000]}"
                )
            }]
        }]
    }

    try:
        response = requests.post(endpoint, headers={"Content-Type": "application/json"}, json=prompt)
        response.raise_for_status()
        output = response.json()

        text_block = output["candidates"][0]["content"]["parts"][0]["text"]
        return safe_parse_llm_json(text_block)

    except requests.exceptions.RequestException as e:
        logger = config.get("logger", None)
        if logger:
            try:
                logger.error(f"GEMINI LLM request failed: {e}")
                logger.error(f"Status Code: {e.response.status_code}")
                logger.error(f"Response: {e.response.text}")
            except:
                logger.error("Could not parse error response from Gemini.")
        return {"summary": "", "tags": [], "classification": "gemini_error"}


def safe_parse_llm_json(raw_output: str) -> Dict:
    """
    Try to parse the raw string from LLM as a dictionary. Fallback if invalid.
    """
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        return {
            "summary": raw_output.strip(),
            "tags": [],
            "classification": "manual_review_required"
        }

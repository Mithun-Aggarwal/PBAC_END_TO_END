# label_golden_file.py
#INPUT_DIR = "/home/mit/Learning_and_growing/AI_DATA_EXTRACTION_AND_SEARCH_V1/Curated_information/documents/output_folder"
#GOLDEN_DIR = "/home/mit/Learning_and_growing/AI_DATA_EXTRACTION_AND_SEARCH_V1/Curated_information/documents_golder_dataset"
#os.makedirs(GOLDEN_DIR, exist_ok=True)
"""
Golden Labeling Helper Script (LLM-Enhanced v2)
-----------------------------------------------
- Allows multi-label manual classification
- Fetches label suggestion from LLM
- Allows full acceptance of suggestion
- Prints LLM's raw output in a structured table
"""

import os
import json
import shutil
import requests
from pathlib import Path
from dotenv import load_dotenv
from tabulate import tabulate
load_dotenv()

LABELS = [
    "GUIDELINE",
    "PSD",
    "MEETING_OUTCOME",
    "COST_MANUAL",
    "CONSULTATION_INPUT",
    "NEWSLETTER",
    "MISC"
]

INPUT_DIR = "/home/mit/Learning_and_growing/AI_DATA_EXTRACTION_AND_SEARCH_V1/Curated_information/documents/output_folder"
GOLDEN_DIR = "/home/mit/Learning_and_growing/AI_DATA_EXTRACTION_AND_SEARCH_V1/Curated_information/documents/golden_dataset"
OLLAMA_CHAT_URL = os.getenv("OLLAMA_CHAT_URL", "http://localhost:11434/api/chat")
os.makedirs(GOLDEN_DIR, exist_ok=True)

PROMPT_TEMPLATE = """
You are a PBAC document classification expert. Given the following text, respond in valid JSON format with:

- document_type: One or more labels from [GUIDELINE, PSD, MEETING_OUTCOME, COST_MANUAL, CONSULTATION_INPUT, NEWSLETTER, MISC]
- topics: A list of 2–5 topics from the document (e.g., pricing, access, effectiveness, submission ID, stakeholders)
- reasoning: A short justification of your classification

Respond ONLY in JSON.

Text:
"""


def list_json_files():
    return [f for f in os.listdir(INPUT_DIR) if f.endswith(".json")]


def get_llm_classification(text):
    payload = {
        "model": "mistral",
        "messages": [
            {"role": "system", "content": "You are a PBAC document labeling assistant."},
            {"role": "user", "content": PROMPT_TEMPLATE + text[:15000]}
        ],
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_CHAT_URL, json=payload)
        response.raise_for_status()
        content = response.json()["message"]["content"]
        return json.loads(content)
    except Exception as e:
        return {"error": str(e)}


def auto_label_file(filename):
    path = os.path.join(INPUT_DIR, filename)
    with open(path) as f:
        data = json.load(f)

    preview = data.get("text", "")[:600]
    llm_response = get_llm_classification(preview)

    if "error" in llm_response:
        print(f"❌ Error classifying {filename}: {llm_response['error']}")
        return

    data.setdefault("metadata", {})
    data["metadata"]["detected_type"] = llm_response.get("document_type")
    data["metadata"]["topics"] = llm_response.get("topics")
    data["metadata"]["llm_reasoning"] = llm_response.get("reasoning")

    output_path = os.path.join(GOLDEN_DIR, filename)
    with open(output_path, "w") as out:
        json.dump(data, out, indent=2)

    print(f"✅ {filename} labeled and saved to {output_path}")


def main():
    files = list_json_files()
    if not files:
        print("❌ No JSON files found in output_folder.")
        return

    print("🚀 Running in fully automated mode...")
    for f in files:
        auto_label_file(f)

if __name__ == "__main__":
    main()

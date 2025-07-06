import json
import os
import re
from datetime import datetime
from .date_extractor import DateExtractor # <-- IMPORT NEW MODULE

def structure_and_enrich_json(raw_json_dir='raw_json', structured_json_dir='structured_json'):
    """
    Processes raw JSON files, standardizes their structure, and enriches them with metadata.

    This script reads each JSON file from the `raw_json` directory, transforms it
    into a standardized schema with 'metadata' and 'content' objects, and saves the
    newly structured file into the `structured_json` directory.

    Args:
        raw_json_dir (str): The directory containing the raw JSON files.
        structured_json_dir (str): The directory where the structured JSON files will be saved.
    """
    if not os.path.exists(structured_json_dir):
        os.makedirs(structured_json_dir)
        print(f"Created directory: {structured_json_dir}")

    for filename in os.listdir(raw_json_dir):
        if filename.endswith('.json'):
            raw_filepath = os.path.join(raw_json_dir, filename)
            structured_filepath = os.path.join(structured_json_dir, filename)

            try:
                with open(raw_filepath, 'r') as f:
                    data = json.load(f)

                # --- Date Extraction ---
                source_pdf_path = data.get("source_file", "")
                raw_text = data.get("data", {}).get("raw_text", "")
                
                date_extractor = DateExtractor(file_path=source_pdf_path, document_text=raw_text)
                date_info = date_extractor.extract_date()


                # --- Metadata Enrichment ---
                source_document = "Unknown"
                source_page_number = "Unknown"
                
                # Parse filename to get source document and page number
                match = re.match(r'(.+)_page_(\d+)\.json', filename)
                if match:
                    source_document = match.group(1) + ".pdf"
                    source_page_number = int(match.group(2))

                metadata = {
                    "source_document": source_document,
                    "source_page_number": source_page_number,
                    "processing_timestamp": datetime.utcnow().isoformat() + "Z",
                    "classified_page_type": data.get("classified_page_type", "Unknown"),
                    "extraction_tool_used": "content_extractor.py"
                }
                metadata.update(date_info) # <-- ADD DATE METADATA

                # --- Structuring ---
                structured_data = {
                    "metadata": metadata,
                    "content": data 
                }
                
                # Remove redundant key from content if it exists
                if "classified_page_type" in structured_data["content"]:
                    del structured_data["content"]["classified_page_type"]


                # --- Save Structured JSON ---
                with open(structured_filepath, 'w') as f:
                    json.dump(structured_data, f, indent=4)
                
                print(f"Successfully processed and structured {filename}")

            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON from {filename}. Skipping.")
            except Exception as e:
                print(f"An unexpected error occurred while processing {filename}: {e}")

if __name__ == '__main__':
    # For demonstration, let's assume 'raw_json' contains some files.
    # You would run this script as part of your pipeline.
    
    # Create dummy raw_json directory and a file for testing
    if not os.path.exists('raw_json'):
        os.makedirs('raw_json')
    
    dummy_data = {
        "classified_page_type": "TOC",
        "header": "TABLE OF CONTENTS",
        "items": [
            {"text": "Section 1", "page": 3},
            {"text": "Section 2", "page": 5}
        ]
    }
    with open('raw_json/dummy_document_page_1.json', 'w') as f:
        json.dump(dummy_data, f, indent=4)

    structure_and_enrich_json()
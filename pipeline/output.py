# output.py

"""
Output module: Saves processed document content, metadata, and optional LLM enhancements.
Supports JSON, plain text, or Markdown format. Logs output status.
"""

import os
import json
from typing import Dict
from pipeline.refresh import mark_as_processed

def save_output(
    original_path: str,
    clean_text: str,
    metadata: Dict,
    llm_data: Dict,
    config: Dict
):
    """
    Save processed output (text + metadata) in the configured format.

    Args:
        original_path (str): Path to source document
        clean_text (str): Normalized content
        metadata (Dict): Extracted metadata
        llm_data (Dict): Optional LLM-enhanced outputs
        config (Dict): Configuration settings
    """
    output_dir = config.get("output_folder", "./documents/processed")
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(original_path))[0]
    output_format = config.get("output_format", "json").lower()
    output_path = os.path.join(output_dir, f"{base_name}.{output_format}")

    if output_format == "json":
        combined = {
            "metadata": metadata,
            "text": clean_text,
            "llm_output": llm_data
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(combined, f, indent=2)

    elif output_format == "txt":
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(clean_text)

    elif output_format == "md":
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(clean_text)

    else:
        raise ValueError(f"Unsupported output format: {output_format}")

    # Record in cache
    doc_hash = metadata.get("doc_hash") or base_name
    mark_as_processed(doc_hash, metadata, config)

    if logger := config.get("logger"):
        logger.info(f"Saved output for {base_name} as {output_format.upper()}")

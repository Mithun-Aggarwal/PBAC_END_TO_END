# normalize.py

"""
Normalization module: cleans extracted text to ensure consistency, readability,
and downstream compatibility (e.g., for embeddings or summarization).
"""

import re
from typing import Dict

def normalize_text(raw_text: str, config: Dict) -> str:
    """
    Normalize and clean the extracted text.

    Args:
        raw_text (str): Raw text from extract.py
        config (Dict): Configuration dictionary for custom behavior

    Returns:
        str: Normalized, clean text
    """

    # 1. Remove redundant whitespace and normalize newlines
    text = re.sub(r'\r\n|\r', '\n', raw_text)         # Normalize line endings
    text = re.sub(r'\n{3,}', '\n\n', text)             # Reduce excessive newlines
    text = re.sub(r'[ \t]+', ' ', text)                 # Normalize spaces

    # 2. Remove page markers (optional, keep if needed for traceability)
    text = re.sub(r'\n\s*--- Page \d+ ---\s*\n', '\n', text)

    # 3. Remove headers/footers if common (basic rule-based demo)
    text = re.sub(r'(Confidential|PBAC Public Summary Document|Page \d+ of \d+)', '', text, flags=re.IGNORECASE)

    # 4. Strip overall leading/trailing space
    text = text.strip()

    # 5. Convert to Markdown-style headers (optional demo)
    if config.get("normalize_to_markdown", False):
        text = convert_to_markdown(text)

    return text

def convert_to_markdown(text: str) -> str:
    """Basic heuristic to format common headers into markdown."""
    lines = text.split('\n')
    output = []
    for line in lines:
        stripped = line.strip()
        if len(stripped) > 0 and stripped.isupper():
            output.append(f"## {stripped}")
        else:
            output.append(stripped)
    return "\n".join(output)

# refresh.py

"""
Document refresh logic: checks whether a document has been previously processed
based on a content hash. Supports force refresh and metadata caching.
"""

import os
import hashlib
import json
from typing import Tuple, Dict

def check_if_processed(file_path: str, config: Dict) -> Tuple[str, bool]:
    """
    Determine if a document has already been processed.

    Args:
        file_path (str): Full path to the document.
        config (Dict): Configuration with cache and refresh flags

    Returns:
        Tuple[str, bool]: (document hash, already_processed flag)
    """
    force = config.get("force_refresh", False)
    cache_dir = config.get("cache_folder", "./cache")
    os.makedirs(cache_dir, exist_ok=True)

    doc_hash = hash_file(file_path)
    cache_path = os.path.join(cache_dir, f"{doc_hash}.json")

    if force:
        return doc_hash, False

    if os.path.exists(cache_path):
        return doc_hash, True

    return doc_hash, False

def mark_as_processed(doc_hash: str, metadata: Dict, config: Dict):
    """
    Save metadata to mark the document as processed.

    Args:
        doc_hash (str): Unique hash of the document
        metadata (Dict): Metadata to save
        config (Dict): Config dict with cache path
    """
    cache_dir = config.get("cache_folder", "./cache")
    os.makedirs(cache_dir, exist_ok=True)

    cache_path = os.path.join(cache_dir, f"{doc_hash}.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

def hash_file(file_path: str, chunk_size: int = 4096) -> str:
    """
    Generate a SHA256 hash of a file's content.

    Args:
        file_path (str): Path to the file
        chunk_size (int): Chunk size for reading the file

    Returns:
        str: Hexadecimal SHA256 hash
    """
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()

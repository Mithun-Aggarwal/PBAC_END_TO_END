# pipeline/indexer.py

"""
Pinecone Indexer Module
-----------------------
This script reads the final processed JSON files and populates a Pinecone
vector index. The index is the core of the semantic search system.
"""

import os
import json
import pinecone
import argparse
import yaml
from tqdm import tqdm
from typing import Dict, List, Any

def resolve_paths(config: Dict):
    """Resolves path placeholders in the config."""
    paths = config['paths']
    output_base = paths.get('output_base', '')

    for key, val in list(paths.items()):
        if isinstance(val, str):
            paths[key] = val.replace('{paths.output_base}', output_base)
    return config

def _prepare_vectors_for_pinecone(processed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Prepares a list of vectors for upserting to Pinecone from the processed data.
    """
    vectors = []
    doc_id = processed_data.get("document_id")
    source_file = processed_data.get("source_file")

    for page in processed_data.get("pages", []):
        page_num = page.get("page_number")
        page_meta = page.get("page_metadata", {})

        for chunk in page.get("chunks", []):
            if chunk.get("embedding"):
                vector = {
                    "id": chunk["chunk_id"],
                    "values": chunk["embedding"],
                    "metadata": {
                        "document_id": doc_id,
                        "source_file": source_file,
                        "page_number": page_num,
                        "chunk_type": chunk.get("chunk_type"),
                        "page_summary": page_meta.get("summary"),
                        "page_content_type": page_meta.get("content_type"),
                        "text": chunk.get("text") # Storing original text in metadata
                    }
                }
                vectors.append(vector)
    return vectors

def index_documents_to_pinecone(config: Dict[str, Any]):
    """
    Scans the processed_json directory, loads the data, and populates the
    Pinecone vector index.
    """
    paths = config['paths']
    db_config = config['vector_db']['pinecone']
    
    processed_dir = paths['processed_json']
    index_name = db_config['index_name']

    if not os.path.isdir(processed_dir):
        print(f"❌ Error: Processed JSON directory not found at '{processed_dir}'.")
        return

    # 1. Initialize Pinecone
    pinecone.init(api_key=os.getenv("PINECONE_API_KEY"), environment=os.getenv("PINECONE_ENVIRONMENT"))
    
    if index_name not in pinecone.list_indexes():
        print(f"Index '{index_name}' not found. Please create it in the Pinecone console.")
        return
        
    index = pinecone.Index(index_name)
    print(f"Pinecone index '{index_name}' loaded. Current vector count: {index.describe_index_stats()['total_vector_count']}")

    # 2. Find all processed files to index
    processed_files = [os.path.join(processed_dir, f) for f in os.listdir(processed_dir) if f.endswith('.json')]
    
    if not processed_files:
        print("🤷 No new processed files found to index.")
        return

    print(f"Found {len(processed_files)} processed files to index...")

    # 3. Process each file and upsert its vectors to Pinecone
    for file_path in tqdm(processed_files, desc="Indexing Files", unit="file"):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        vectors_to_upsert = _prepare_vectors_for_pinecone(data)
        
        if vectors_to_upsert:
            index.upsert(vectors=vectors_to_upsert)

    print("\n✅ Indexing complete.")
    print(f"Index '{index_name}' now contains {index.describe_index_stats()['total_vector_count']} vectors.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Populate a Pinecone vector index from processed JSON files.")
    parser.add_argument("--config", required=True, help="Path to the config.yaml file.")
    args = parser.parse_args()

    try:
        with open(args.config, 'r') as file:
            config = yaml.safe_load(file)
        
        config = resolve_paths(config)
        index_documents_to_pinecone(config)

    except FileNotFoundError:
        print(f"❌ Error: Config file not found at '{args.config}'")
    except Exception as e:
        print(f"🔥 An unexpected error occurred: {e}")
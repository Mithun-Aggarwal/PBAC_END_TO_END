import os
import json
import pickle
from sentence_transformers import SentenceTransformer
import numpy as np

# --- Configuration ---
STRUCTURED_JSON_DIR = 'structured_json'
EMBEDDINGS_DIR = 'embeddings'
EMBEDDING_MODEL = 'all-MiniLM-L6-v2'  # A good starting model
EMBEDDINGS_FILE = os.path.join(EMBEDDINGS_DIR, 'embeddings.pkl')

def create_text_chunk(page_type, content):
    """
    Creates a context-aware text chunk for embedding.

    This function combines the classified page type with the core content
    to provide richer context for the embedding model.

    Args:
        page_type (str): The type of the page (e.g., 'dense_text', 'table').
        content (str): The extracted text content of the page.

    Returns:
        str: A formatted string ready for embedding.
    """
    if not content:
        return "" # Return empty string if content is empty
    return f"This page is classified as `{page_type}` and contains the following content: {content}"

def generate_embeddings(structured_json_dir: str, embeddings_dir: str):
    """
    Generates embeddings for all structured JSON files and saves them to a file.

    This function processes each JSON file in the structured_json directory,
    creates a context-aware text chunk, generates a vector embedding using
    a sentence-transformer model, and stores the result in a pickle file.
    """
    # 1. Ensure the output directory exists
    os.makedirs(embeddings_dir, exist_ok=True)
    embeddings_file = os.path.join(embeddings_dir, 'embeddings.pkl')

    # 2. Load the sentence-transformer model
    print(f"Loading embedding model: {EMBEDDING_MODEL}...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print("Model loaded successfully.")

    # 3. Process each JSON file
    embeddings_map = {}
    json_files = [f for f in os.listdir(structured_json_dir) if f.endswith('.json')]

    if not json_files:
        print(f"No JSON files found in '{structured_json_dir}'. Exiting.")
        return

    print(f"Found {len(json_files)} JSON files to process...")

    for filename in json_files:
        json_path = os.path.join(structured_json_dir, filename)
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)

            # 4. Create the strategic text chunk
            page_type = data.get('classified_page_type', 'unknown')
            content = data.get('content', '')
            
            text_chunk = create_text_chunk(page_type, content)

            if not text_chunk:
                print(f"Skipping {filename} due to empty content.")
                continue

            # 5. Generate the embedding
            embedding = model.encode(text_chunk, convert_to_numpy=True)
            embeddings_map[filename] = embedding

            print(f"Generated embedding for {filename}")

        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {filename}. Skipping.")
        except Exception as e:
            print(f"An unexpected error occurred while processing {filename}: {e}")

    # 6. Store the embeddings
    if not embeddings_map:
        print("No embeddings were generated. The output file will not be created.")
        return
        
    print(f"\nSaving {len(embeddings_map)} embeddings to {embeddings_file}...")
    with open(embeddings_file, 'wb') as f:
        pickle.dump(embeddings_map, f)

    print("Embedding generation complete.")
    print(f"Embeddings saved successfully to {embeddings_file}")

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Generate embeddings from structured JSON files.")
    parser.add_argument("structured_dir", help="The directory containing the structured JSON files.")
    parser.add_argument("embeddings_dir", help="The directory where the embeddings file will be saved.")
    
    args = parser.parse_args()

    if not os.path.isdir(args.structured_dir):
        print(f"Error: Structured JSON directory not found at '{args.structured_dir}'")
    else:
        generate_embeddings(args.structured_dir, args.embeddings_dir)
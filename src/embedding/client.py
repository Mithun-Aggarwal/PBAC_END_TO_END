# FILE: src/embedding/client.py
# Kilo-Architect - Embedding Client Wrapper V1.0

"""
This module provides a simple, robust wrapper for interacting with the
Google AI embedding model. It standardizes the embedding generation process
and provides a single point of change if the model or its API ever needs
to be updated.
"""

import logging
import os
import google.generativeai as genai
from typing import List

# Ensure the API key is configured from the environment.
# This relies on the bootstrap loader in the main executable scripts.
if not os.environ.get("GOOGLE_API_KEY"):
    raise ImportError("GOOGLE_API_KEY not found in environment. Ensure dotenv is loaded.")
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))


class EmbeddingClient:
    """A simple, robust wrapper for the Google AI embedding model."""
    def __init__(self, model_name: str = "text-embedding-004"):
        self.model_name = f"models/{model_name}"
        logging.info(f"EmbeddingClient prepared for model: {self.model_name}")

    def embed(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> List[float]:
        """
        Generates an embedding for a single piece of text.

        Args:
            text: The text to embed.
            task_type: The task type for the embedding (e.g., "RETRIEVAL_DOCUMENT").

        Returns:
            A list of floats representing the vector embedding.
        """
        if not text or not isinstance(text, str):
            logging.warning("Embedding requested for empty or invalid text. Returning empty list.")
            return []
        try:
            # Use the recommended embed_content function
            result = genai.embed_content(
                model=self.model_name,
                content=text,
                task_type=task_type
            )
            return result['embedding']
        except Exception as e:
            logging.error(f"Failed to generate embedding. Text snippet: '{text[:80]}...'. Error: {e}")
            # Re-raise the exception to allow the calling function to handle it.
            raise
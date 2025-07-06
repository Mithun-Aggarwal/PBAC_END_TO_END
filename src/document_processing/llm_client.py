# FILE: src/document_processing/llm_client.py
# Kilo-Architect - LLM Client Module V7.3 (FINAL - Production Ready)

import os
import re
import json
import logging
import google.generativeai as genai
import yaml
from pathlib import Path
from json_repair import repair_json
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.generativeai import GenerationConfig

# --- Configuration Loading ---
def _load_config():
    """Loads the main config.yml file from the project root."""
    try:
        config_path = Path(__file__).resolve().parents[2] / 'config.yml'
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        if not config:
            raise ValueError("Config file is empty or could not be parsed.")
        return config
    except (FileNotFoundError, IndexError):
        logging.warning("config.yml not found. Using default fallback for repair model.")
        return {'llm_configs': {'repair_model_name': 'gemini-1.5-flash-latest'}}
    except yaml.YAMLError as e:
        logging.error(f"Error parsing config.yml: {e}. Using default fallback for repair model.")
        return {'llm_configs': {'repair_model_name': 'gemini-1.5-flash-latest'}}

_config = _load_config()
REPAIR_MODEL_NAME = _config.get('llm_configs', {}).get('repair_model_name', 'gemini-1.5-flash-latest')

google_api_key = os.environ.get("GOOGLE_API_KEY")
if not google_api_key:
    raise ValueError("GOOGLE_API_KEY environment variable not set.")
genai.configure(api_key=google_api_key)

SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

class LLMAPIError(Exception):
    """Custom exception for LLM API-related errors, including parsing failures."""
    pass

def _sanitize_llm_response(raw_response: str) -> str:
    """(Legacy) Extracts JSON from a non-JSON mode response string."""
    json_match = re.search(r"```(?:json)?\s*({.*?}|\[.*?\])\s*```", raw_response, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()
    start = raw_response.find('{')
    end = raw_response.rfind('}')
    if start != -1 and end != -1:
        return raw_response[start:end+1]
    return raw_response

def _repair_json_with_llm(broken_json: str) -> str:
    """Uses a fallback LLM to repair a badly broken JSON string."""
    logging.info(f"Attempting to repair JSON with model: {REPAIR_MODEL_NAME}")
    repair_prompt = f"""The following text is a malformed JSON object. Please fix it. Correct syntax errors like missing commas, brackets, or quotes. Return ONLY the corrected JSON object. Broken JSON:\n---\n{broken_json}\n---"""
    try:
        model = genai.GenerativeModel(REPAIR_MODEL_NAME)
        generation_config = GenerationConfig(response_mime_type="application/json")
        response = model.generate_content(repair_prompt, safety_settings=SAFETY_SETTINGS, generation_config=generation_config)
        if not response.parts:
            raise LLMAPIError("LLM-based JSON repair resulted in a BLOCKED or EMPTY response.")
        repaired_text = response.text
        json.loads(repaired_text)
        return repaired_text
    except Exception as e:
        raise LLMAPIError(f"The LLM-based repair process failed: {e}")

def call_gemini(prompt: str, model_name: str, force_json: bool = True) -> str:
    """
    Calls the Gemini API with a robust, multi-stage self-healing JSON repair process.
    """
    logging.debug(f"Calling Gemini model '{model_name}' with force_json={force_json}")
    try:
        generation_config = GenerationConfig(max_output_tokens=8192)
        if force_json:
            generation_config.response_mime_type = "application/json"
        
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt, safety_settings=SAFETY_SETTINGS, generation_config=generation_config)
        
        if not response.parts:
            raise LLMAPIError(f"LLM Response from model '{model_name}' was BLOCKED or EMPTY.")
            
        raw_response_text = response.text

        if not force_json:
            return _sanitize_llm_response(raw_response_text)
        
        # --- V6 SELF-HEALING PARSER PIPELINE ---
        # Stage 1: Attempt direct validation (strict parse)
        try:
            json.loads(raw_response_text)
            logging.debug("LLM returned valid JSON on the first try.")
            return raw_response_text
        except json.JSONDecodeError:
            logging.warning("LLM response is not valid JSON. Proceeding to Stage 2: Automated Repair.")

        # Stage 2: Attempt automated repair with `json-repair` library
        try:
            repaired_string = repair_json(raw_response_text)
            json.loads(repaired_string) 
            logging.info("Successfully repaired JSON with `json-repair` library.")
            return repaired_string
        except Exception as e:
            logging.warning(f"Automated JSON repair failed. Reason: {e}. Proceeding to Stage 3: LLM-Based Repair.")
            
        # Stage 3: Attempt repair using a fallback LLM
        try:
            return _repair_json_with_llm(raw_response_text)
        except LLMAPIError as e:
            logging.error(f"All JSON repair attempts failed. Original malformed response from '{model_name}':\n{raw_response_text}", exc_info=True)
            raise LLMAPIError(f"All JSON repair attempts failed. Final error: {e}") from e

    except Exception as e:
        if not isinstance(e, LLMAPIError):
            raise LLMAPIError(f"Gemini API call to model '{model_name}' failed unexpectedly: {e}") from e
        raise e
import yaml
from pathlib import Path

PROMPTS_FILE = Path(__file__).parent / "prompts.yml"

def load_prompt(prompt_name: str) -> str:
    """
    Loads a prompt template from the prompts.yml file.

    Args:
        prompt_name: The name of the prompt to load (e.g., 'deconstruct_document_v1').

    Returns:
        The prompt template string.
    """
    with open(PROMPTS_FILE, 'r') as f:
        prompts = yaml.safe_load(f)
    
    if prompt_name not in prompts:
        raise ValueError(f"Prompt '{prompt_name}' not found in {PROMPTS_FILE}")
        
    return prompts[prompt_name]['template']
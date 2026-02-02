import json
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage
import sys
import os

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

def get_llm(temperature: float = 0.7, max_tokens: int | None = None):
    """
    Returns a ChatOpenAI instance configured with the settings from config.py.
    """
    return ChatOpenAI(
        model=config.MODEL_NAME,
        openai_api_base=config.BASE_URL,
        openai_api_key=config.API_KEY,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout=config.LLM_TIMEOUT_SECONDS,
    )

def extract_json(text: str) -> Dict[str, Any]:
    """
    Helper to extract JSON from LLM response.
    Robustly finds the substring between the first '{' and the last '}'.
    """
    text = text.strip()
    
    try:
        # Try to find the JSON brace pointers
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = text[start_idx : end_idx + 1]
            return json.loads(json_str)
        else:
            # Try direct load if braces aren't found (unlikely for object)
            return json.loads(text)
    except json.JSONDecodeError:
        return {"score": 0, "feedback": "Failed to parse evaluation response.", "reasoning": "Parser Error"}

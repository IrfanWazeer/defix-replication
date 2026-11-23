import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")
    VALIDATION_MODE: str = os.getenv("DEFIX_VALIDATION_MODE", "strict").strip().lower()
    if VALIDATION_MODE not in {"strict", "hybrid"}:
        raise ValueError(
            "DEFIX_VALIDATION_MODE must be either 'strict' or 'hybrid'."
        )
    
    # Active fast model with token management
    DEFAULT_MODEL: str = os.getenv("DEFIX_MODEL", "qwen/qwen3.8-27b").strip()
    TEMPERATURE: float = 0.0
    
    MAX_RETRY_ITERATIONS: int = 3
    
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

settings = Settings()
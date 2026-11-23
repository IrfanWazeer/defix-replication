import os
import time
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from config.settings import settings


def _is_reasoning_model(name: str) -> bool:
    return "gpt-oss" in (name or "").lower()


def get_llm():
    """
    Returns configured LLM instance with strict max_tokens limit
    and rate limit prevention.

    For gpt-oss models (reasoning models) the thinking tokens are counted inside
    max_tokens, so reasoning effort is set to "low" and the cap is raised to 1500.
    All other models keep the original cap of 800.
    """
    provider = settings.LLM_PROVIDER.lower()

    sleep_seconds = float(os.getenv("DEFIX_LLM_SLEEP", "0"))
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)

    if provider == "groq":
        kwargs = dict(
            model_name=settings.DEFAULT_MODEL,
            groq_api_key=settings.GROQ_API_KEY,
            temperature=settings.TEMPERATURE,
            max_tokens=800,  # Enforces response within Groq 1000 OTPM limit
            max_retries=5,
        )
        if _is_reasoning_model(settings.DEFAULT_MODEL):
            kwargs["max_tokens"] = int(os.getenv("DEFIX_MAX_TOKENS", "1500"))
            try:
                return ChatGroq(reasoning_effort="low", **kwargs)
            except Exception:
                return ChatGroq(model_kwargs={"reasoning_effort": "low"}, **kwargs)
        return ChatGroq(**kwargs)
    elif provider == "openai":
        return ChatOpenAI(
            model_name=settings.DEFAULT_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
            temperature=settings.TEMPERATURE,
            max_retries=5,
        )
    else:
        raise ValueError(f"Unsupported LLM Provider: {provider}")
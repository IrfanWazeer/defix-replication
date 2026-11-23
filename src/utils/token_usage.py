from collections.abc import Mapping
from typing import Any, Optional


def response_token_usage(response: Any) -> dict[str, Optional[int]]:
    metadata = getattr(response, "usage_metadata", None)
    if not isinstance(metadata, Mapping):
        response_metadata = getattr(response, "response_metadata", None)
        metadata = (
            response_metadata.get("token_usage")
            if isinstance(response_metadata, Mapping)
            else None
        )
    if not isinstance(metadata, Mapping):
        return {"prompt_tokens": None, "completion_tokens": None}

    prompt = metadata.get("input_tokens", metadata.get("prompt_tokens"))
    completion = metadata.get("output_tokens", metadata.get("completion_tokens"))
    return {
        "prompt_tokens": prompt if isinstance(prompt, int) else None,
        "completion_tokens": completion if isinstance(completion, int) else None,
    }


def append_token_usage(state: dict[str, Any], response: Any) -> list[dict[str, Optional[int]]]:
    usage = list(state.get("llm_usage", []))
    usage.append(response_token_usage(response))
    return usage

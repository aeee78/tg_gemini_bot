"""Record Gemini API calls without storing prompts, responses, or error text."""
import logging
from datetime import datetime, timezone
from time import perf_counter

from database.db import SessionLocal
from database.models import UsageRecord

logger = logging.getLogger(__name__)
TOKEN_FIELDS = {
    "prompt_tokens": "prompt_token_count",
    "output_tokens": "candidates_token_count",
    "thinking_tokens": "thoughts_token_count",
    "cached_tokens": "cached_content_token_count",
    "tool_tokens": "tool_use_prompt_token_count",
    "total_tokens": "total_token_count",
}


def nonnegative_integer(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def save_usage(user_id, model_name, operation, started_at, duration, response=None, error=None):
    # Telemetry failures must not suppress a Gemini response or its original error.
    try:
        metadata = getattr(response, "usage_metadata", None)
        tokens = {
            field: nonnegative_integer(
                metadata.get(attribute) if isinstance(metadata, dict)
                else getattr(metadata, attribute, None)
            )
            for field, attribute in TOKEN_FIELDS.items()
        }
        with SessionLocal() as session:
            session.add(UsageRecord(
                user_id=user_id, model=model_name, operation=operation,
                started_at=started_at, duration_seconds=duration,
                success=error is None,
                error_type=type(error).__name__ if error is not None else None,
                error_code=nonnegative_integer(getattr(error, "code", None)),
                **tokens,
            ))
            session.commit()
    except Exception as recording_error:
        logger.error("Could not record Gemini usage (%s)", type(recording_error).__name__)


def track_gemini_call(user_id, model_name, operation, request, **kwargs):
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    timer = perf_counter()
    try:
        response = request(**kwargs)
    except Exception as error:
        save_usage(user_id, model_name, operation, started_at, perf_counter() - timer, error=error)
        raise
    save_usage(user_id, model_name, operation, started_at, perf_counter() - timer, response=response)
    return response

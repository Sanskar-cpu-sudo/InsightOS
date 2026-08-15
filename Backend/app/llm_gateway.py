import time
import json
import litellm
import logfire

from app.config import get_settings
from app.monitoring import configure_monitoring

settings = get_settings()
configure_monitoring()

# LiteLLM expects the provider's API key as an environment variable
# (or passed explicitly). We set it explicitly here based on whichever
# provider is active in config.py, so .env is the only place keys live.
_PROVIDER_KEY_MAP = {
    "openai": ("OPENAI_API_KEY", settings.OPENAI_API_KEY),
    "groq": ("GROQ_API_KEY", settings.GROQ_API_KEY),
    "gemini": ("GEMINI_API_KEY", settings.GEMINI_API_KEY),
}


# With .get():

# _PROVIDER_KEY_MAP.get("xyz", (None, None))

# you get:

# (None, None)

# instead of an error.
_env_var, _key_value = _PROVIDER_KEY_MAP.get(settings.LLM_PROVIDER, (None, None))
if _env_var and _key_value:
    import os
    os.environ[_env_var] = _key_value

# LiteLLM identifies the provider from a "provider/model" prefix on the
# model string, e.g. "groq/llama-3.3-70b-versatile", "gpt-4o-mini" (openai
# doesn't need a prefix), "gemini/gemini-1.5-flash".
_PROVIDER_MODEL_PREFIX = {
    "openai": "",              # no prefix needed for openai models
    "groq": "groq/",
    "gemini": "gemini/",
}


def _full_model_name(model_name: str | None = None) -> str:
    """Builds the litellm-formatted model string, e.g. 'groq/llama-3.3-70b-versatile'."""
    prefix = _PROVIDER_MODEL_PREFIX.get(settings.LLM_PROVIDER, "")
    model = model_name or settings.LLM_MODEL
    return f"{prefix}{model}"


# The chain of models to try, in order. If the primary fails (timeout,
# rate limit, outage, malformed response from the provider itself), we
# fall back to the next one before giving up entirely.
def _model_chain() -> list[str]:
    chain = [_full_model_name(settings.LLM_MODEL)]
    if settings.LLM_FALLBACK_MODEL and settings.LLM_FALLBACK_MODEL != settings.LLM_MODEL:
        chain.append(_full_model_name(settings.LLM_FALLBACK_MODEL))
    return chain


class LLMGatewayError(Exception):
    """Raised only when EVERY model in the fallback chain has failed."""
    def __init__(self, attempts: list[dict]):
        self.attempts = attempts  # [{"model": ..., "error": ...}, ...]
        summary = "; ".join(f"{a['model']}: {a['error']}" for a in attempts)
        super().__init__(f"All models in fallback chain failed -> {summary}")


class LLMResponse:
    """Simple wrapper so callers get text + useful metadata together."""
    def __init__(self, text: str, latency_seconds: float, input_tokens: int,
                 output_tokens: int, model: str):
        self.text = text
        self.latency_seconds = latency_seconds
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model

    def estimated_cost_usd(self) -> float:
        """
        Rough cost estimate. Groq's Llama models are priced per-million-tokens
        and are very cheap; exact pricing changes over time, so treat this as
        an approximate figure for the Evaluation Engine's 'cost' metric,
        not a billing-accurate number.
        """
        try:
            cost = litellm.completion_cost(
                model=self.model,
                prompt_tokens=self.input_tokens,
                completion_tokens=self.output_tokens,
            )
            return round(cost, 6)
        except Exception:
            return 0.0


def complete(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
) -> LLMResponse:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    attempts = []

    for model in _model_chain():
        # V2, Step 6.1: one Logfire span per model attempt -- this is
        # what lets us see, per call, which model actually answered,
        # whether the primary model failed and we fell back, and how
        # long/expensive each attempt was, all without changing any of
        # the function's actual return behavior below.
        with logfire.span("llm_completion", model=model) as span:
            start = time.time()
            try:
                response = litellm.completion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    timeout=30,  # seconds -- don't let one hung request stall the whole pipeline
                )
            except Exception as e:
                span.set_attribute("success", False)
                span.set_attribute("error", str(e))
                attempts.append({"model": model, "error": str(e)})
                continue

            latency = time.time() - start
            text = response.choices[0].message.content
            usage = response.usage

            llm_response = LLMResponse(
                text=text,
                latency_seconds=round(latency, 3),
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                model=model,
            )

            span.set_attribute("success", True)
            span.set_attribute("latency_seconds", llm_response.latency_seconds)
            span.set_attribute("input_tokens", llm_response.input_tokens)
            span.set_attribute("output_tokens", llm_response.output_tokens)
            span.set_attribute("estimated_cost_usd", llm_response.estimated_cost_usd())

            return llm_response

    # Every model in the chain failed -- surface this clearly instead of
    # silently returning something broken.
    raise LLMGatewayError(attempts)


def complete_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    max_retries: int = 2,
) -> tuple[dict, LLMResponse]:
    """
    Used by the Decision Agent, which MUST get back structured JSON
    (root_cause, evidence, confidence, recommendation) -- not free text.

    We ask the model to respond in JSON, then parse it. If parsing fails
    (models occasionally wrap JSON in markdown fences or add stray text),
    we retry up to `max_retries` times with a stricter reminder.

    Returns (parsed_dict, raw_llm_response) so the caller has both the
    structured data AND the latency/token info for evaluation/logging.
    """
    strict_system_prompt = (
        system_prompt
        + "\n\nIMPORTANT: Respond with ONLY valid JSON. No markdown fences, "
        "no explanation text before or after the JSON object."
    )

    last_response = None
    last_error = None

    # V2, Step 6.1: one span covering the whole retry loop, so Logfire
    # shows how many attempts a call actually needed to get valid JSON
    # back, not just whether it eventually succeeded.
    with logfire.span("llm_completion_json", max_retries=max_retries) as span:
        for attempt in range(max_retries + 1):
            prompt = user_prompt
            if attempt > 0:
                prompt += (
                    f"\n\n(Your previous response could not be parsed as JSON: "
                    f"{last_error}. Return ONLY a valid JSON object this time.)"
                )

            try:
                last_response = complete(strict_system_prompt, prompt, temperature=temperature)
            except LLMGatewayError as e:
                # Every model in the fallback chain failed for this attempt --
                # no point retrying with the same broken chain, fail fast.
                span.set_attribute("success", False)
                span.set_attribute("error", "llm_gateway_unavailable")
                span.set_attribute("attempts_used", attempt + 1)
                return (
                    {"error": "llm_gateway_unavailable", "detail": str(e)},
                    None,
                )

            cleaned = last_response.text.strip()
            # Defensive cleanup in case the model wraps JSON in ```json fences
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                cleaned = cleaned.replace("json\n", "", 1).replace("json", "", 1)

            try:
                parsed = json.loads(cleaned)
                span.set_attribute("success", True)
                span.set_attribute("attempts_used", attempt + 1)
                return parsed, last_response
            except json.JSONDecodeError as e:
                last_error = str(e)
                continue

        # All retries failed -- return an explicit failure marker rather than
        # silently returning garbage. Guardrails (Step 11) will catch this.
        span.set_attribute("success", False)
        span.set_attribute("error", "failed_to_parse_json")
        span.set_attribute("attempts_used", max_retries + 1)
        return (
            {
                "error": "failed_to_parse_json",
                "raw_text": last_response.text if last_response else "",
            },
            last_response,
        )
import json
import os
import time

import litellm
import logfire

from app.config import get_settings
from app.monitoring import configure_monitoring


settings = get_settings()
configure_monitoring()


# -------------------------------------------------------------------
# Provider API keys
# -------------------------------------------------------------------

_PROVIDER_KEY_MAP = {
    "openai": ("OPENAI_API_KEY", settings.OPENAI_API_KEY),
    "groq": ("GROQ_API_KEY", settings.GROQ_API_KEY),
    "gemini": ("GEMINI_API_KEY", settings.GEMINI_API_KEY),
}


_env_var, _key_value = _PROVIDER_KEY_MAP.get(
    settings.LLM_PROVIDER,
    (None, None),
)

if _env_var and _key_value:
    os.environ[_env_var] = _key_value


# -------------------------------------------------------------------
# Model naming
# -------------------------------------------------------------------

_PROVIDER_MODEL_PREFIX = {
    "openai": "",
    "groq": "groq/",
    "gemini": "gemini/",
}


def _full_model_name(model_name: str | None = None) -> str:
    """
    Convert the configured model name into the model format expected
    by LiteLLM.

    Example:

        provider = groq
        model = openai/gpt-oss-120b

    becomes:

        groq/openai/gpt-oss-120b
    """

    model = model_name or settings.LLM_MODEL

    prefix = _PROVIDER_MODEL_PREFIX.get(
        settings.LLM_PROVIDER,
        "",
    )

    # Avoid accidentally producing:
    # groq/groq/openai/gpt-oss-120b
    if prefix and model.startswith(prefix):
        return model

    return f"{prefix}{model}"


# -------------------------------------------------------------------
# Model fallback chain
# -------------------------------------------------------------------

def _model_chain() -> list[str]:
    """
    Primary model first, fallback model second.
    """

    chain = [
        _full_model_name(settings.LLM_MODEL)
    ]

    if (
        settings.LLM_FALLBACK_MODEL
        and settings.LLM_FALLBACK_MODEL != settings.LLM_MODEL
    ):
        chain.append(
            _full_model_name(settings.LLM_FALLBACK_MODEL)
        )

    return chain


# -------------------------------------------------------------------
# Errors
# -------------------------------------------------------------------

class LLMGatewayError(Exception):
    """
    Raised when every model in the fallback chain fails.
    """

    def __init__(self, attempts: list[dict]):
        self.attempts = attempts

        summary = "; ".join(
            f"{attempt['model']}: {attempt['error']}"
            for attempt in attempts
        )

        super().__init__(
            f"All models in fallback chain failed -> {summary}"
        )


# -------------------------------------------------------------------
# LLM response
# -------------------------------------------------------------------

class LLMResponse:
    """
    Wrapper around the raw LLM response.

    Gives callers:
    - generated text
    - latency
    - token usage
    - model used
    """

    def __init__(
        self,
        text: str,
        latency_seconds: float,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ):
        self.text = text
        self.latency_seconds = latency_seconds
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model

    def estimated_cost_usd(self) -> float:
        """
        Approximate cost calculated by LiteLLM.
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


# -------------------------------------------------------------------
# Normal completion
# -------------------------------------------------------------------

def complete(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
) -> LLMResponse:

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]

    attempts = []

    model_chain = _model_chain()

    print("\n" + "=" * 60)
    print("LLM GATEWAY")
    print("Provider:", settings.LLM_PROVIDER)
    print("Models:", model_chain)
    print(
        "API key available:",
        bool(_key_value),
    )
    print("=" * 60)

    for model in model_chain:

        print(f"\nTrying model: {model}")

        with logfire.span(
            "llm_completion",
            model=model,
        ) as span:

            start = time.time()

            try:

                response = litellm.completion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    timeout=30,
                )

            except Exception as e:

                error_text = repr(e)

                # IMPORTANT:
                # Print the actual LiteLLM error instead of hiding it.
                print("\n🔥 LITELLM ERROR")
                print("Model:", model)
                print("Provider:", settings.LLM_PROVIDER)
                print("Error:", error_text)
                print("=" * 60)

                span.set_attribute(
                    "success",
                    False,
                )

                span.set_attribute(
                    "error",
                    str(e),
                )

                attempts.append(
                    {
                        "model": model,
                        "error": str(e),
                    }
                )

                continue

            latency = time.time() - start

            try:
                text = response.choices[0].message.content
            except Exception as e:

                error_text = repr(e)

                print("\n🔥 INVALID LLM RESPONSE")
                print("Model:", model)
                print("Error:", error_text)

                span.set_attribute(
                    "success",
                    False,
                )

                span.set_attribute(
                    "error",
                    error_text,
                )

                attempts.append(
                    {
                        "model": model,
                        "error": error_text,
                    }
                )

                continue

            usage = response.usage

            input_tokens = getattr(
                usage,
                "prompt_tokens",
                0,
            )

            output_tokens = getattr(
                usage,
                "completion_tokens",
                0,
            )

            llm_response = LLMResponse(
                text=text or "",
                latency_seconds=round(
                    latency,
                    3,
                ),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
            )

            estimated_cost = (
                llm_response.estimated_cost_usd()
            )

            span.set_attribute(
                "success",
                True,
            )

            span.set_attribute(
                "latency_seconds",
                llm_response.latency_seconds,
            )

            span.set_attribute(
                "input_tokens",
                llm_response.input_tokens,
            )

            span.set_attribute(
                "output_tokens",
                llm_response.output_tokens,
            )

            span.set_attribute(
                "estimated_cost_usd",
                estimated_cost,
            )

            print("\n✅ LLM SUCCESS")
            print("Model:", model)
            print(
                "Latency:",
                llm_response.latency_seconds,
                "seconds",
            )
            print(
                "Input tokens:",
                input_tokens,
            )
            print(
                "Output tokens:",
                output_tokens,
            )
            print("=" * 60)

            return llm_response

    # ---------------------------------------------------------------
    # Every model failed
    # ---------------------------------------------------------------

    print("\n🔥 ALL LLM MODELS FAILED")

    for attempt in attempts:
        print(
            f"Model: {attempt['model']}\n"
            f"Error: {attempt['error']}\n"
        )

    raise LLMGatewayError(attempts)


# -------------------------------------------------------------------
# JSON completion
# -------------------------------------------------------------------

def complete_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    max_retries: int = 2,
) -> tuple[dict, LLMResponse | None]:

    """
    Used by the Decision Agent.

    The LLM must return a valid JSON object.

    If JSON parsing fails, retry.

    Returns:

        (
            parsed_json,
            llm_response
        )
    """

    strict_system_prompt = (
        system_prompt
        + "\n\nIMPORTANT: Respond with ONLY valid JSON. "
        "No markdown fences, no explanation before the JSON, "
        "and no explanation after the JSON object."
    )

    last_response = None
    last_error = None

    with logfire.span(
        "llm_completion_json",
        max_retries=max_retries,
    ) as span:

        for attempt in range(max_retries + 1):

            print(
                f"\nJSON attempt "
                f"{attempt + 1}/{max_retries + 1}"
            )

            prompt = user_prompt

            if attempt > 0:

                prompt += (
                    "\n\nYour previous response could not "
                    "be parsed as JSON.\n"
                    f"Parser error: {last_error}\n"
                    "Return ONLY a valid JSON object."
                )

            try:

                last_response = complete(
                    strict_system_prompt,
                    prompt,
                    temperature=temperature,
                )

            except LLMGatewayError as e:

                print(
                    "\n🔥 LLM GATEWAY UNAVAILABLE "
                    "FOR JSON REQUEST"
                )

                print("Details:", str(e))

                span.set_attribute(
                    "success",
                    False,
                )

                span.set_attribute(
                    "error",
                    "llm_gateway_unavailable",
                )

                span.set_attribute(
                    "attempts_used",
                    attempt + 1,
                )

                return (
                    {
                        "error": "llm_gateway_unavailable",
                        "detail": str(e),
                    },
                    None,
                )

            cleaned = last_response.text.strip()

            # -------------------------------------------------------
            # Remove markdown fences if model returns:
            #
            # ```json
            # {...}
            # ```
            # -------------------------------------------------------

            if cleaned.startswith("```"):

                cleaned = cleaned.strip("`")

                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]

                cleaned = cleaned.strip()

            # -------------------------------------------------------
            # Parse JSON
            # -------------------------------------------------------

            try:

                parsed = json.loads(cleaned)

                if not isinstance(parsed, dict):

                    raise json.JSONDecodeError(
                        "Expected a JSON object",
                        cleaned,
                        0,
                    )

                span.set_attribute(
                    "success",
                    True,
                )

                span.set_attribute(
                    "attempts_used",
                    attempt + 1,
                )

                print("\n✅ VALID JSON RECEIVED")

                return (
                    parsed,
                    last_response,
                )

            except json.JSONDecodeError as e:

                last_error = str(e)

                print("\n⚠️ JSON PARSING FAILED")
                print("Error:", last_error)
                print("Raw response:")
                print(last_response.text)

                continue

        # -----------------------------------------------------------
        # All JSON retries failed
        # -----------------------------------------------------------

        span.set_attribute(
            "success",
            False,
        )

        span.set_attribute(
            "error",
            "failed_to_parse_json",
        )

        span.set_attribute(
            "attempts_used",
            max_retries + 1,
        )

        print(
            "\n🔥 FAILED TO GET VALID JSON "
            "AFTER ALL RETRIES"
        )

        return (
            {
                "error": "failed_to_parse_json",
                "raw_text": (
                    last_response.text
                    if last_response
                    else ""
                ),
                "detail": last_error or "",
            },
            last_response,
        )
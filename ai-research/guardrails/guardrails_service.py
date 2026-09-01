"""NeMo Guardrails service: fast, embeddings-based input safety checks."""

from typing import Optional
from pydantic import BaseModel, Field
from nemoguardrails import RailsConfig, LLMRails
from config import settings
import logging
import os


class GuardrailResult(BaseModel):
    """Result of a guardrails check."""
    allowed: bool = Field(description="True if input is safe, False if blocked")
    reason: Optional[str] = Field(
        default=None,
        description="Explanation for blocking (None if allowed)"
    )
    blocked_flow: Optional[str] = Field(
        default=None,
        description="Name of the triggered rail flow (e.g., 'check jailbreak')"
    )


class NeMoGuardrailsService:
    """Singleton service running NeMo Guardrails input safety checks."""

    def __init__(self, config_path: str = "guardrails"):
        # NeMo's colang runtime + action dispatcher log at INFO by default, which
        # floods the terminal per request (event traces, action registrations).
        # Operational chatter, not errors - silence below WARNING.
        for _logger_name in (
            "nemoguardrails",
            "nemoguardrails.actions",
            "nemoguardrails.colang",
            "nemoguardrails.llm",
            "nemoguardrails.rails",
            "nemoguardrails.kb",
        ):
            logging.getLogger(_logger_name).setLevel(logging.WARNING)

        print(f"⏳ Loading NeMo Guardrails from {config_path}...")

        if not os.path.exists(config_path):
            raise FileNotFoundError(
                f"Guardrails config directory not found: {config_path}\n"
                f"Expected structure:\n"
                f"  {config_path}/config.yml\n"
                f"  {config_path}/rails/input_rails.co"
            )

        try:
            self.config = RailsConfig.from_path(config_path)
            self.rails = LLMRails(self.config)
            print("✅ NeMo Guardrails loaded successfully (embeddings-based, no LLM calls)")
        except Exception as e:
            print(f"❌ Failed to load NeMo Guardrails: {e}")
            raise

    async def check_input(self, message: str) -> GuardrailResult:
        """Check whether the input message is safe; returns GuardrailResult."""
        try:
            response = await self.rails.generate_async(
                messages=[{"role": "user", "content": message}]
            )
            response_text = response.get("content", "")

            blocked_patterns = [
                "cannot ignore my system instructions",
                "cannot override my instructions",
                "cannot share system credentials"
            ]

            is_blocked = any(pattern in response_text.lower() for pattern in blocked_patterns)

            if is_blocked:
                blocked_flow = None
                if "system instructions" in response_text.lower():
                    blocked_flow = "check jailbreak"
                elif "override" in response_text.lower():
                    blocked_flow = "check prompt injection"
                elif "credentials" in response_text.lower():
                    blocked_flow = "check pii leak"

                return GuardrailResult(
                    allowed=False,
                    reason=response_text,
                    blocked_flow=blocked_flow
                )

            return GuardrailResult(allowed=True)

        except Exception as e:
            # Fail closed: block the input if the guardrails check errors.
            print(f"⚠️ Guardrails check failed: {e}")
            return GuardrailResult(
                allowed=False,
                reason="Safety check temporarily unavailable. Please try again shortly.",
                blocked_flow="error_fail_closed"
            )


_guardrails_service: Optional[NeMoGuardrailsService] = None


def get_guardrails_service() -> NeMoGuardrailsService:
    """Get or create the singleton NeMo Guardrails service instance."""
    global _guardrails_service
    if _guardrails_service is None:
        _guardrails_service = NeMoGuardrailsService()
    return _guardrails_service

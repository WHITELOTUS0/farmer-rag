"""Prompt templates for the agent."""

from src.agent.prompts.system import SYSTEM_PROMPT, REASONING_PROMPT
from src.agent.prompts.verification import VERIFICATION_PROMPT, CLAIM_EXTRACTION_PROMPT

__all__ = [
    "SYSTEM_PROMPT",
    "REASONING_PROMPT",
    "VERIFICATION_PROMPT",
    "CLAIM_EXTRACTION_PROMPT",
]

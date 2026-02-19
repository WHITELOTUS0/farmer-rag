"""
Verification node for groundedness checking.

Implements the two-stage verification pipeline:
1. Claim extraction
2. Citation matching + LLM verification
3. Groundedness score calculation
"""

import json
import logging
from typing import Dict, Any, List, Optional

from openai import OpenAI

from src.config.settings import get_settings
from src.agent.state import AgentState, VerificationResult
from src.agent.prompts.verification import (
    CLAIM_EXTRACTION_PROMPT,
    GROUNDEDNESS_CHECK_PROMPT,
)

logger = logging.getLogger(__name__)


def verification_node(state: AgentState) -> Dict[str, Any]:
    """
    Verify the groundedness of the agent's response.

    This node:
    1. Extracts factual claims from the draft response
    2. Checks each claim against retrieved sources
    3. Calculates a groundedness score
    4. Flags unreliable responses for revision

    Args:
        state: Current agent state with draft_response

    Returns:
        Updated state with verification results
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    draft_response = state.get("draft_response")
    if not draft_response:
        logger.warning("No draft response to verify - ending execution")
        return {
            "final_response": "I apologize, but I couldn't generate a response. Please try again.",
            "verification": {
                "groundedness_score": 0.0,
                "claims": [],
                "is_reliable": False,
                "suggestion": "No response generated",
            },
            "should_continue": False,  # Explicitly stop the loop
        }

    # Get sources for verification (defensive: .get(k, []) returns None if key exists with None)
    retrieved_sources = state.get("retrieved_sources") or []
    tool_calls = state.get("tool_calls") or []

    # Build source context for verification
    sources_text = _format_sources_for_verification(retrieved_sources, tool_calls)

    try:
        # Step 1: Extract claims
        claims = _extract_claims(client, draft_response, settings.verification_model) or []
        logger.info(f"Extracted {len(claims)} claims from response")

        if not claims:
            # No verifiable claims - response is likely conversational
            return {
                "final_response": draft_response,
                "verification": {
                    "groundedness_score": 1.0,
                    "claims": [],
                    "is_reliable": True,
                    "suggestion": None,
                },
            }

        # Step 2: Verify claims
        verified_claims = _verify_claims(
            client,
            claims,
            sources_text,
            settings.verification_model,
        ) or []

        # Step 3: Calculate groundedness score
        supported_count = sum(1 for c in verified_claims if c.get("supported", False))
        groundedness_score = supported_count / len(verified_claims) if verified_claims else 1.0

        logger.info(f"Groundedness score: {groundedness_score:.2f} "
                   f"({supported_count}/{len(verified_claims)} claims supported)")

        # Step 4: Determine if response is reliable
        is_reliable = groundedness_score >= settings.confidence_threshold

        # Build verification result
        verification: VerificationResult = {
            "groundedness_score": round(groundedness_score, 3),
            "claims": verified_claims,
            "is_reliable": is_reliable,
            "suggestion": None,
        }

        # If not reliable, add suggestion
        if not is_reliable:
            unsupported = [c for c in verified_claims if not c.get("supported", False)]
            verification["suggestion"] = (
                f"Response contains {len(unsupported)} unsupported claims. "
                "Consider revising or adding uncertainty language."
            )

        # For now, use draft as final (could add revision step)
        final_response = draft_response

        # Add groundedness info to response
        final_response += f"\n\n---\n📊 **Groundedness Score: {groundedness_score:.0%}**"
        if retrieved_sources:
            final_response += f"\n📚 Based on {len(retrieved_sources)} source(s) from the knowledge base."

        return {
            "final_response": final_response,
            "verification": verification,
        }

    except Exception as e:
        logger.error(f"Verification error: {e}")
        # On verification failure, still return the response but flag it
        return {
            "final_response": draft_response + "\n\n⚠️ *Response verification unavailable*",
            "verification": {
                "groundedness_score": 0.5,  # Unknown
                "claims": [],
                "is_reliable": False,
                "suggestion": f"Verification failed: {str(e)}",
            },
        }


def _extract_claims(
    client: OpenAI,
    response: str,
    model: str,
) -> List[Dict[str, str]]:
    """
    Extract factual claims from a response.

    Args:
        client: OpenAI client
        response: The response text to analyze
        model: Model to use for extraction

    Returns:
        List of claim dictionaries
    """
    prompt = CLAIM_EXTRACTION_PROMPT.format(response=response)

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You extract factual claims from text. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=1000,
        )

        content = completion.choices[0].message.content.strip()

        # Clean up response
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        claims = json.loads(content)
        return claims if isinstance(claims, list) else []

    except Exception as e:
        logger.warning(f"Claim extraction failed: {e}")
        return []


def _verify_claims(
    client: OpenAI,
    claims: List[Dict[str, str]],
    sources_text: str,
    model: str,
) -> List[Dict[str, Any]]:
    """
    Verify claims against source documents.

    Args:
        client: OpenAI client
        claims: List of claims to verify
        sources_text: Formatted source documents
        model: Model to use for verification

    Returns:
        List of claims with verification results
    """
    if not sources_text:
        # No sources to verify against
        return [
            {**claim, "supported": False, "explanation": "No source documents available"}
            for claim in claims
        ]

    verified = []

    # Batch verify for efficiency
    claims_text = "\n".join([f"{i+1}. {c['claim']}" for i, c in enumerate(claims)])

    prompt = f"""Verify each of these claims against the provided sources.

## Claims to Verify:
{claims_text}

## Source Documents:
{sources_text}

For each claim, determine if it is supported by the sources.

Respond with a JSON array:
[
    {{"claim_number": 1, "supported": true/false, "explanation": "brief reason"}},
    ...
]
"""

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You verify factual claims against source documents. Be strict - only mark claims as supported if the information is clearly present in the sources."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=1500,
        )

        content = completion.choices[0].message.content.strip()

        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        verifications = json.loads(content)
        if not isinstance(verifications, list):
            verifications = []

        # Merge verification results with original claims
        for i, claim in enumerate(claims):
            verification = next(
                (v for v in verifications if isinstance(v, dict) and v.get("claim_number") == i + 1),
                {"supported": False, "explanation": "Verification missing"}
            )
            verified.append({
                **claim,
                "supported": verification.get("supported", False),
                "explanation": verification.get("explanation", ""),
            })

    except Exception as e:
        logger.warning(f"Batch verification failed: {e}")
        # Mark all as unverified
        verified = [
            {**claim, "supported": False, "explanation": f"Verification error: {str(e)}"}
            for claim in claims
        ]

    return verified


def _format_sources_for_verification(
    retrieved_sources: List[Dict[str, Any]],
    tool_calls: List[Dict[str, Any]],
) -> str:
    """
    Format sources and tool outputs for verification context.

    Args:
        retrieved_sources: Retrieved knowledge base documents
        tool_calls: Tool execution results

    Returns:
        Formatted string of all sources
    """
    parts = []

    # Add retrieved documents (defensive: handle None)
    for i, source in enumerate((retrieved_sources or [])[:5], 1):
        if source is None:
            continue
        if i == 1:
            parts.append("### Knowledge Base Sources:")
        parts.append(f"\n[Source {i}: {(source or {}).get('source', 'Unknown')}]")
        text = ((source or {}).get("text") or "")[:800]  # Truncate (guard: text may be None)
        parts.append(text)

    # Add relevant tool outputs (defensive: handle None)
    for tc in (tool_calls or []):
        if tc is None:
            continue
        tc = tc or {}
        if tc.get("success") and tc.get("tool_name") in ["get_weather_forecast", "get_market_prices"]:
                parts.append(f"\n### {tc.get('tool_name', 'unknown')} Output:")
                output = json.dumps(tc.get("tool_output", ""), indent=2, default=str)
                if len(output) > 1000:
                    output = output[:1000] + "..."
                parts.append(output)

    return "\n".join(parts) if parts else ""

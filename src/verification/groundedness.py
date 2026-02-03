"""
Groundedness verification service.
"""

import json
import logging
import math
import re
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from src.config.settings import get_settings
from src.retrieval.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class VerificationService:
    """Two-stage verification: claim extraction + similarity matching."""

    def __init__(self):
        settings = get_settings()
        self.llm = ChatOpenAI(
            model=settings.verification_model,
            temperature=0,
            api_key=settings.openai_api_key,
        )
        self.embeddings = EmbeddingService()
        self.similarity_threshold = settings.confidence_threshold
        self.max_sources = 3
        self.max_claims = 6

    def verify(self, response: str, sources: List[str]) -> Dict[str, Any]:
        claims = self._extract_claims(response)[: self.max_claims]
        if not claims:
            return {
                "groundedness_score": 1.0,
                "is_reliable": True,
                "claims": [],
                "notes": "No factual claims detected.",
            }

        sources = sources[: self.max_sources]
        supported = self._score_claims(claims, sources)

        supported_count = sum(1 for c in supported if c["supported"])
        groundedness = supported_count / len(supported) if supported else 0.0
        return {
            "groundedness_score": round(groundedness, 3),
            "is_reliable": groundedness >= self.similarity_threshold,
            "claims": supported,
        }

    def _extract_claims(self, response: str) -> List[str]:
        class ClaimsOutput(BaseModel):
            claims: List[str] = Field(
                default_factory=list,
                description="List of factual claims extracted from the response.",
            )

        parser = PydanticOutputParser(pydantic_object=ClaimsOutput)
        prompt = (
            "Extract all factual claims from the response below.\n"
            "Return them using the required JSON schema.\n\n"
            f"Response:\n{response}\n\n"
            f"{parser.get_format_instructions()}"
        )
        try:
            result = self.llm.invoke(prompt)
            content = result.content.strip()
            parsed = parser.parse(content)
            return [c.strip() for c in parsed.claims if c.strip()]
        except Exception as e:
            logger.warning("Claim extraction failed: %s", e)

        # Fallback: simple sentence split
        sentences = re.split(r"(?<=[.!?])\s+", response.strip())
        claims = [s.strip() for s in sentences if len(s.strip()) > 10]
        return claims

    def _score_claims(self, claims: List[str], sources: List[str]) -> List[Dict[str, Any]]:
        if not sources or not claims:
            return [{"claim": claim, "score": 0.0, "supported": False} for claim in claims]

        claim_vecs = self.embeddings.embed_documents(claims)
        source_vecs = self.embeddings.embed_documents(sources)

        results: List[Dict[str, Any]] = []
        for claim, claim_vec in zip(claims, claim_vecs):
            best = 0.0
            for source_vec in source_vecs:
                best = max(best, _cosine_similarity(claim_vec, source_vec))
            results.append(
                {
                    "claim": claim,
                    "score": best,
                    "supported": best >= self.similarity_threshold,
                }
            )
        return results


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

"""
Metadata extraction for document chunks.

Uses a combination of rule-based and LLM-based extraction to
identify crop types, topics, growth stages, and other relevant
metadata for agricultural content.
"""

import re
import logging
from typing import List, Dict, Any, Optional

from openai import OpenAI

from src.config.settings import get_settings
from src.retrieval.chunking.base import Chunk, ChunkMetadata

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """
    Extracts agricultural metadata from text chunks.

    Uses a two-stage approach:
    1. Rule-based extraction for obvious patterns (fast, free)
    2. LLM-based extraction for semantic understanding (when needed)
    """

    # Keywords for rule-based extraction
    CROP_KEYWORDS = {
        "maize": ["maize", "corn", "zea mays"],
        "beans": ["beans", "bean", "phaseolus", "legume", "legumes"],
        "tomatoes": ["tomato", "tomatoes", "solanum lycopersicum"],
    }

    TOPIC_KEYWORDS = {
        "fertilizer": [
            "fertilizer", "fertiliser", "npk", "urea", "dap", "manure",
            "compost", "nutrient", "nitrogen", "phosphorus", "potassium",
            "organic matter", "soil amendment"
        ],
        "pest_control": [
            "pest", "insect", "bug", "aphid", "worm", "beetle", "borer",
            "caterpillar", "mite", "pesticide", "insecticide", "spray",
            "infestation", "damage"
        ],
        "disease": [
            "disease", "blight", "wilt", "rot", "fungus", "fungal", "virus",
            "bacterial", "infection", "pathogen", "lesion", "spot"
        ],
        "irrigation": [
            "water", "irrigation", "irrigate", "drought", "moisture",
            "rainfall", "rain", "dry", "flooding", "drainage", "sprinkler"
        ],
        "planting": [
            "plant", "planting", "seed", "sow", "sowing", "spacing", "depth",
            "germination", "transplant", "seedling", "nursery"
        ],
        "harvesting": [
            "harvest", "harvesting", "mature", "maturity", "ripe", "yield",
            "storage", "post-harvest", "picking", "collection"
        ],
        "weeding": [
            "weed", "weeding", "weeds", "herbicide", "grass", "competition",
            "mulch", "mulching"
        ],
        "soil": [
            "soil", "ph", "acidity", "alkaline", "clay", "loam", "sandy",
            "organic", "fertility", "erosion", "tillage"
        ],
    }

    GROWTH_STAGE_KEYWORDS = {
        "planting": ["planting", "sowing", "transplanting", "establishment"],
        "germination": ["germination", "emergence", "sprouting", "seedling"],
        "vegetative": ["vegetative", "v1", "v2", "v3", "v4", "v5", "v6", "leaf", "growth"],
        "flowering": ["flowering", "tasseling", "silking", "bloom", "flower"],
        "fruiting": ["fruiting", "pod", "ear", "fruit development", "grain fill"],
        "maturity": ["maturity", "mature", "drying", "senescence", "ripening"],
        "harvest": ["harvest", "harvesting", "ready to harvest"],
    }

    def __init__(
        self,
        use_llm: bool = True,
        llm_model: Optional[str] = None,
    ):
        """
        Initialize the metadata extractor.

        Args:
            use_llm: Whether to use LLM for uncertain extractions
            llm_model: Model to use for LLM extraction
        """
        self.use_llm = use_llm
        settings = get_settings()
        self.llm_model = llm_model or settings.verification_model  # Use cheaper model

        if use_llm:
            self.client = OpenAI(api_key=settings.openai_api_key)

    def extract_metadata(self, chunk: Chunk) -> ChunkMetadata:
        """
        Extract metadata from a chunk.

        Args:
            chunk: The text chunk to analyze

        Returns:
            ChunkMetadata with extracted information
        """
        text = chunk.text.lower()

        # Stage 1: Rule-based extraction
        crop_types = self._extract_crops_rule_based(text)
        topics = self._extract_topics_rule_based(text)
        growth_stages = self._extract_growth_stages_rule_based(text)
        has_numerical = self._has_numerical_data(chunk.text)
        region_specific = self._is_region_specific(text)

        confidence = 1.0

        # Stage 2: LLM extraction if needed
        if self.use_llm and self._needs_llm_extraction(crop_types, topics):
            llm_metadata = self._extract_with_llm(chunk.text)
            if llm_metadata:
                # Merge LLM results
                if not crop_types and llm_metadata.get("crop_types"):
                    crop_types = llm_metadata["crop_types"]
                    confidence = 0.9

                if not topics and llm_metadata.get("topics"):
                    topics = llm_metadata["topics"]
                    confidence = min(confidence, 0.9)

                if not growth_stages and llm_metadata.get("growth_stages"):
                    growth_stages = llm_metadata["growth_stages"]

        return ChunkMetadata(
            crop_types=crop_types,
            topics=topics,
            growth_stages=growth_stages,
            has_numerical_data=has_numerical,
            region_specific=region_specific,
            confidence=confidence,
        )

    def extract_metadata_batch(
        self,
        chunks: List[Chunk],
        use_llm_batch: bool = False,
    ) -> List[ChunkMetadata]:
        """
        Extract metadata from multiple chunks.

        Args:
            chunks: List of chunks to process
            use_llm_batch: Whether to batch LLM calls (not implemented yet)

        Returns:
            List of ChunkMetadata objects
        """
        # For now, process individually
        # TODO: Implement batch LLM extraction for efficiency
        return [self.extract_metadata(chunk) for chunk in chunks]

    def _extract_crops_rule_based(self, text: str) -> List[str]:
        """Extract crop types using keyword matching."""
        found_crops = []

        for crop, keywords in self.CROP_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    found_crops.append(crop)
                    break

        return list(set(found_crops))

    def _extract_topics_rule_based(self, text: str) -> List[str]:
        """Extract topics using keyword matching."""
        found_topics = []

        for topic, keywords in self.TOPIC_KEYWORDS.items():
            keyword_count = sum(1 for kw in keywords if kw in text)
            # Require at least 2 keyword matches for confidence
            if keyword_count >= 2:
                found_topics.append(topic)
            elif keyword_count == 1 and len(text) < 500:
                # For shorter texts, one keyword might be enough
                found_topics.append(topic)

        return list(set(found_topics))

    def _extract_growth_stages_rule_based(self, text: str) -> List[str]:
        """Extract growth stages using keyword matching."""
        found_stages = []

        for stage, keywords in self.GROWTH_STAGE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    found_stages.append(stage)
                    break

        return list(set(found_stages))

    def _has_numerical_data(self, text: str) -> bool:
        """Check if text contains agricultural measurements."""
        patterns = [
            r'\d+\s*kg',
            r'\d+\s*ha',
            r'\d+\s*hectare',
            r'\d+\s*cm',
            r'\d+\s*mm',
            r'\d+\s*%',
            r'\d+\s*ml',
            r'\d+\s*l(?:iter)?',
            r'\d+\s*g(?:ram)?',
            r'\d+\/ha',
            r'\d+-\d+\s*days',
        ]

        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def _is_region_specific(self, text: str) -> bool:
        """Check if text is specific to East Africa."""
        region_keywords = [
            "east africa", "africa", "kenya", "uganda", "tanzania",
            "rwanda", "burundi", "ethiopia", "kigali", "nairobi",
            "kampala", "dar es salaam", "tropical", "sub-saharan",
            "smallholder", "small-scale farmer"
        ]

        return any(kw in text for kw in region_keywords)

    def _needs_llm_extraction(
        self,
        crop_types: List[str],
        topics: List[str],
    ) -> bool:
        """Determine if LLM extraction would be beneficial."""
        # Use LLM if rule-based extraction found nothing
        return not crop_types and not topics

    def _extract_with_llm(self, text: str) -> Optional[Dict[str, List[str]]]:
        """
        Use LLM to extract metadata from text.

        Args:
            text: The chunk text

        Returns:
            Dictionary with extracted metadata or None if failed
        """
        try:
            prompt = f"""Analyze this agricultural text and extract metadata.

Text:
{text[:1500]}  # Limit to control costs

Extract the following (respond with ONLY JSON, no explanation):
{{
    "crop_types": ["list of crops mentioned: maize, beans, or tomatoes only"],
    "topics": ["list of topics: fertilizer, pest_control, disease, irrigation, planting, harvesting, weeding, soil"],
    "growth_stages": ["list of stages: planting, germination, vegetative, flowering, fruiting, maturity, harvest"]
}}

If a category doesn't apply, use an empty list [].
Only include items if clearly mentioned or strongly implied."""

            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "You are an agricultural metadata extractor. Respond only with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=200,
            )

            content = response.choices[0].message.content.strip()

            # Parse JSON response
            import json

            # Clean up response if needed
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            result = json.loads(content)

            # Validate and clean results
            valid_crops = {"maize", "beans", "tomatoes"}
            valid_topics = set(self.TOPIC_KEYWORDS.keys())
            valid_stages = set(self.GROWTH_STAGE_KEYWORDS.keys())

            return {
                "crop_types": [c for c in result.get("crop_types", []) if c in valid_crops],
                "topics": [t for t in result.get("topics", []) if t in valid_topics],
                "growth_stages": [s for s in result.get("growth_stages", []) if s in valid_stages],
            }

        except Exception as e:
            logger.warning(f"LLM metadata extraction failed: {e}")
            return None

    def enrich_chunk(self, chunk: Chunk) -> Chunk:
        """
        Enrich a chunk with extracted metadata.

        Modifies the chunk's metadata in place and returns it.

        Args:
            chunk: The chunk to enrich

        Returns:
            The enriched chunk
        """
        extracted = self.extract_metadata(chunk)
        chunk.metadata.update(extracted.to_dict())
        return chunk

    def enrich_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        Enrich multiple chunks with extracted metadata.

        Args:
            chunks: List of chunks to enrich

        Returns:
            List of enriched chunks
        """
        logger.info(f"Enriching {len(chunks)} chunks with metadata...")
        return [self.enrich_chunk(chunk) for chunk in chunks]

"""
Verification prompts for groundedness checking and claim extraction.
"""

CLAIM_EXTRACTION_PROMPT = """Extract all factual claims from the following agricultural advisory response. A factual claim is a statement that can be verified as true or false.

Response to analyze:
{response}

Extract each distinct factual claim. Focus on:
- Specific recommendations (dosages, quantities, timing)
- Facts about crops, pests, or diseases
- Weather-related statements
- Market price information
- Cause-and-effect statements

Respond with a JSON array of claims:
[
    {{"claim": "statement 1", "type": "recommendation|fact|statistic"}},
    {{"claim": "statement 2", "type": "recommendation|fact|statistic"}},
    ...
]

Only include verifiable factual claims. Exclude:
- Greetings or pleasantries
- Questions back to the farmer
- General encouragement
- Obvious common knowledge
"""

VERIFICATION_PROMPT = """Verify whether the following claim is supported by the provided source documents.

## Claim to Verify
{claim}

## Source Documents
{sources}

## Instructions
Carefully analyze whether the claim is explicitly or implicitly supported by the source documents.

Consider:
1. Is the specific information in the claim present in the sources?
2. Are quantities, dosages, or timing mentioned in the claim consistent with the sources?
3. Is the claim a reasonable inference from the source material?

Respond in JSON format:
{{
    "supported": true or false,
    "confidence": 0.0 to 1.0,
    "explanation": "Brief explanation of why the claim is or isn't supported",
    "source_quote": "Relevant quote from source if supported, or null"
}}
"""

GROUNDEDNESS_CHECK_PROMPT = """Evaluate the groundedness of this agricultural advisory response against the retrieved sources.

## Advisory Response
{response}

## Retrieved Sources
{sources}

## Tool Outputs Used
{tool_outputs}

## Evaluation Criteria
For each key factual claim in the response:
1. Is it supported by the retrieved sources or tool outputs?
2. Is any critical information (dosages, timing, specific recommendations) accurate?
3. Are there any statements that appear to be hallucinated (not in sources)?

## Response Format
Provide a JSON evaluation:
{{
    "groundedness_score": 0.0 to 1.0,
    "total_claims": number,
    "supported_claims": number,
    "unsupported_claims": [
        {{"claim": "...", "issue": "..."}}
    ],
    "critical_errors": [
        // Any dangerous misinformation about pesticides, chemicals, etc.
    ],
    "overall_assessment": "reliable|needs_revision|unreliable",
    "suggested_revision": "If needs_revision, what should be changed"
}}
"""

RESPONSE_REVISION_PROMPT = """Revise the following response to improve its groundedness. Remove or correct any unsupported claims.

## Original Response
{original_response}

## Unsupported Claims
{unsupported_claims}

## Available Sources
{sources}

## Instructions
1. Remove any claims that are not supported by the sources
2. Correct any inaccurate information
3. Add appropriate uncertainty language where evidence is weak
4. Maintain the helpful tone and structure
5. Keep all accurately sourced information

Provide the revised response that only includes information supported by the sources.
"""

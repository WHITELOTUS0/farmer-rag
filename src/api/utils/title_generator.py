"""
Utility to generate conversation titles from user messages.
"""

import re
from typing import Optional


def generate_conversation_title(message: str, max_length: int = 60) -> str:
    """
    Generate a concise title from a user message.
    
    Extracts key information like crop types, topics, and questions.
    
    Args:
        message: The user's message/question
        max_length: Maximum length of the generated title
        
    Returns:
        A concise title for the conversation
    """
    if not message:
        return "New conversation"
    
    # Clean the message
    text = message.strip()
    
    # Remove common prefixes
    prefixes = [
        r"^(using the knowledge base,?\s*)?",
        r"^(tell me about|what is|how to|can you|please)\s+",
        r"^(i want to know|i need|help me with)\s+",
    ]
    for prefix in prefixes:
        text = re.sub(prefix, "", text, flags=re.IGNORECASE)
    
    # Extract crop types (common ones)
    crops = ["maize", "corn", "beans", "tomatoes", "tomato", "wheat", "rice", "potato", "potatoes"]
    found_crops = [crop for crop in crops if crop.lower() in text.lower()]
    
    # Extract key topics
    topics = [
        "spacing", "planting", "fertilizer", "fertilization", "watering", "irrigation",
        "harvesting", "pests", "diseases", "yield", "soil", "weather", "season",
        "growth", "care", "management", "practices", "tips", "advice"
    ]
    found_topics = [topic for topic in topics if topic.lower() in text.lower()]
    
    # Build title
    title_parts = []
    
    if found_crops:
        # Use the first crop found, capitalize it
        crop = found_crops[0].capitalize()
        if crop.lower() == "corn":
            crop = "Maize"  # Normalize corn to maize
        title_parts.append(crop)
    
    if found_topics:
        # Use the first topic found, capitalize it
        topic = found_topics[0].capitalize()
        title_parts.append(topic)
    
    # If we have both crop and topic, create a nice title
    if len(title_parts) >= 2:
        title = f"{title_parts[0]} {title_parts[1]}"
    elif len(title_parts) == 1:
        title = title_parts[0]
    else:
        # Fallback: use first few words of the message
        words = text.split()[:6]  # First 6 words
        title = " ".join(words)
        # Remove trailing punctuation
        title = re.sub(r"[.,!?;:]+$", "", title)
    
    # Truncate if too long
    if len(title) > max_length:
        title = title[:max_length - 3] + "..."
    
    # Capitalize first letter
    if title:
        title = title[0].upper() + title[1:] if len(title) > 1 else title.upper()
    
    return title or "New conversation"

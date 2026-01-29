"""
Pytest fixtures for testing.
"""

import pytest
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set test environment
os.environ.setdefault("APP_ENV", "development")


@pytest.fixture
def sample_farmer_context():
    """Sample farmer context for testing."""
    return {
        "farmer": {
            "name": "Test Farmer",
            "region": "Kigali",
            "location": {"lat": -1.9403, "lon": 29.8739},
        },
        "farms": [
            {
                "name": "Test Farm",
                "crops": [
                    {"type": "maize", "growth_stage": "vegetative"},
                ],
            }
        ],
    }


@pytest.fixture
def sample_document_text():
    """Sample agricultural text for testing."""
    return """
    Maize Fertilizer Application Guidelines

    1. Planting Time Application:
       - Apply DAP (Diammonium Phosphate) at 50 kg/ha at planting
       - Place fertilizer 5cm to the side and 5cm below the seed

    2. Top Dressing (V6-V8 Stage):
       - Apply Urea at 50 kg/ha when maize is knee-high
       - Apply during cool morning hours
       - Avoid application if heavy rain is expected

    3. Important Notes:
       - Soil test recommended before application
       - Adjust rates based on soil fertility
    """

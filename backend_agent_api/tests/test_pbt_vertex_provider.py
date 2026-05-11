"""Property-based test: Model configuration respects environment variable.

**Validates: Requirements 1.4**

Property 1: For any valid Gemini model name string set in the `LLM_CHOICE`
environment variable, calling `get_model()` SHALL return a `GoogleModel`
instance configured with that exact model name.

Uses hypothesis to generate random valid model name strings (non-empty,
alphanumeric with hyphens, dots, and underscores) and verifies that
get_model() always returns a GoogleModel with the matching name.
"""

import os
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic_ai.models.google import GoogleModel

from vertex_provider import get_model

# ---------------------------------------------------------------------------
# Strategy: valid Gemini model name strings
# ---------------------------------------------------------------------------
# Model names are non-empty strings composed of alphanumeric characters,
# hyphens, dots, and underscores (e.g. "gemini-2.0-flash", "gemini-2.5-pro").

model_name_chars = st.sampled_from(
    list("abcdefghijklmnopqrstuvwxyz"
         "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
         "0123456789"
         "-._")
)

valid_model_names = st.text(
    alphabet=model_name_chars,
    min_size=1,
    max_size=80,
)


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

class TestModelConfigProperty:
    """Property 1: Model configuration respects environment variable.

    **Validates: Requirements 1.4**
    """

    @given(model_name=valid_model_names)
    @settings(max_examples=100, deadline=None)
    def test_get_model_uses_llm_choice(self, model_name: str):
        """For any valid model name in LLM_CHOICE, get_model() returns
        a GoogleModel configured with that exact name."""
        with patch.dict(os.environ, {
            "LLM_CHOICE": model_name,
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GOOGLE_CLOUD_REGION": "us-central1",
        }):
            model = get_model()
            assert isinstance(model, GoogleModel)
            assert model._model_name == model_name

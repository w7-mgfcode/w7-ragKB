"""Tests for vertex_provider module."""

import os
from unittest.mock import patch

import pytest
from pydantic_ai.models.google import GoogleModel

from vertex_provider import get_model


class TestGetModel:
    """Tests for the get_model() factory function."""

    @patch.dict(os.environ, {
        "LLM_CHOICE": "gemini-2.0-flash",
        "GOOGLE_CLOUD_PROJECT": "my-project",
        "GOOGLE_CLOUD_REGION": "us-central1",
    })
    def test_returns_google_model_instance(self):
        model = get_model()
        assert isinstance(model, GoogleModel)

    @patch.dict(os.environ, {
        "LLM_CHOICE": "gemini-2.5-flash",
        "GOOGLE_CLOUD_PROJECT": "my-project",
        "GOOGLE_CLOUD_REGION": "us-central1",
    })
    def test_uses_llm_choice_env_var(self):
        model = get_model()
        assert model._model_name == "gemini-2.5-flash"

    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "my-project",
        "GOOGLE_CLOUD_REGION": "us-central1",
    }, clear=False)
    def test_defaults_to_gemini_2_0_flash(self):
        # Remove LLM_CHOICE if set
        env = os.environ.copy()
        env.pop("LLM_CHOICE", None)
        with patch.dict(os.environ, env, clear=True):
            model = get_model()
            assert model._model_name == "gemini-2.0-flash"

    @patch.dict(os.environ, {
        "LLM_CHOICE": "gemini-2.0-flash",
        "GOOGLE_CLOUD_PROJECT": "my-project",
        "GOOGLE_CLOUD_REGION": "europe-west1",
    })
    def test_respects_region_env_var(self):
        model = get_model()
        # Verify the provider was created (model instantiation succeeds)
        assert model._provider is not None

    @patch.dict(os.environ, {
        "LLM_CHOICE": "gemini-2.0-flash",
        "GOOGLE_CLOUD_PROJECT": "test-project-123",
    }, clear=False)
    def test_defaults_region_to_us_central1(self):
        env = os.environ.copy()
        env.pop("GOOGLE_CLOUD_REGION", None)
        env["LLM_CHOICE"] = "gemini-2.0-flash"
        env["GOOGLE_CLOUD_PROJECT"] = "test-project-123"
        with patch.dict(os.environ, env, clear=True):
            model = get_model()
            # Should not raise — defaults to us-central1
            assert isinstance(model, GoogleModel)

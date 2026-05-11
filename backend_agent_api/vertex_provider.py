"""Vertex AI Gemini model factory for Pydantic AI.

Creates a Google Vertex AI provider using Application Default Credentials
or GOOGLE_APPLICATION_CREDENTIALS env var.
"""

import os

from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider


def get_model() -> GoogleModel:
    """Create a Gemini model configured from environment variables.

    Env vars:
        LLM_CHOICE: Gemini model name (default: gemini-2.0-flash)
        GOOGLE_CLOUD_PROJECT: GCP project ID (required)
        GOOGLE_CLOUD_REGION: GCP region (default: us-central1)
    """
    model_name = os.getenv("LLM_CHOICE", "gemini-2.0-flash")
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    region = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")

    provider = GoogleProvider(
        project=project_id,
        location=region,
    )
    return GoogleModel(model_name, provider=provider)

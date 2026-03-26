"""Google Gen AI client factory for standard Vertex AI via ADC."""

from __future__ import annotations

import google.auth
from google import genai
from google.genai import types

from config.settings import (
    GOOGLE_CLOUD_PROJECT,
    GOOGLE_CLOUD_LOCATION,
)


def has_genai_credentials() -> bool:
    if not GOOGLE_CLOUD_PROJECT:
        return False
    try:
        google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        return True
    except Exception:
        return False


def create_genai_client(
    http_options: types.HttpOptions | dict | None = None,
) -> genai.Client:
    if not GOOGLE_CLOUD_PROJECT:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for standard Vertex AI access.")

    kwargs = {}
    if http_options is not None:
        kwargs["http_options"] = http_options

    return genai.Client(
        vertexai=True,
        project=GOOGLE_CLOUD_PROJECT,
        location=GOOGLE_CLOUD_LOCATION,
        **kwargs,
    )

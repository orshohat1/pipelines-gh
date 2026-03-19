"""Application configuration with BYOK support."""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class BYOKProviderConfig(BaseModel):
    """BYOK provider configuration matching Copilot SDK provider options."""

    provider_type: Literal["openai", "azure", "anthropic"] = Field(
        default="openai",
        description="Provider type for the model API.",
    )
    base_url: str | None = Field(
        default=None,
        description="API endpoint URL. Required for BYOK.",
    )
    api_key: str | None = Field(
        default=None,
        description="API key for authentication.",
    )
    model_name: str = Field(
        default="claude-sonnet-4.6",
        description="Model identifier to use.",
    )
    wire_api: Literal["completions", "responses"] = Field(
        default="completions",
        description="OpenAI API format.",
    )

    def to_sdk_provider(self) -> dict | None:
        """Convert to Copilot SDK provider dict. Returns None if no BYOK configured."""
        if not self.base_url:
            return None
        provider: dict = {
            "type": self.provider_type,
            "base_url": self.base_url,
            "wire_api": self.wire_api,
        }
        if self.api_key:
            provider["api_key"] = self.api_key
        return provider


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    default_model: str = "claude-sonnet-4.6"
    max_concurrent_pipelines: int = 5
    hitl_timeout_seconds: int = 300  # 5 minutes
    host: str = "0.0.0.0"
    port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    actionlint_path: str = "actionlint"

    model_config = {"env_prefix": "PIPELINES_GH_"}


settings = Settings()

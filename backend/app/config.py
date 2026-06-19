from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, read from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://jobintel:jobintel@localhost:5432/jobintel"
    cors_origins: list[str] = ["*"]

    # LLM (OpenAI-compatible). Defaults target OpenRouter's free tier; swap the
    # base_url/model/key for OpenAI, AWS Bedrock proxy, etc. without code changes.
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openai/gpt-oss-20b:free"
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"),
    )

    # Candidate intent (tracks, locations, …) — separate from resume text.
    candidate_profile_path: str = "evals/golden_set/candidate_profile.yaml"

    # Dev/eval default resume; extension uploads override per request.
    default_resume_path: str = "evals/golden_set/resume.md"

    # Embeddings for resume RAG (OpenAI-compatible API).
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Resume fit: auto tries LLM after RAG retrieval, falls back to vector thresholds.
    resume_fit_method: str = "auto"  # auto | llm | vector


settings = Settings()

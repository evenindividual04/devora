from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    app_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"

    api_key: str = "devora-local-admin-key"
    share_token_secret: str = "devora-local-share-secret"
    share_token_ttl_minutes: int = 1440
    access_token_secret: str = "devora-local-access-secret"
    refresh_token_secret: str = "devora-local-refresh-secret"
    oauth_token_enc_key: str = ""

    access_token_ttl_minutes: int = 60
    refresh_token_ttl_minutes: int = 10080

    github_token: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    github_oauth_redirect_uri: str = "http://localhost:8000/auth/github/callback"
    github_api_base: str = "https://api.github.com"

    database_url: str = "sqlite+aiosqlite:///./app.db"
    redis_url: str = "redis://localhost:6379/0"
    use_redis_queue: bool = False
    run_worker_in_api: bool = True

    worker_max_attempts: int = 3
    worker_base_backoff_seconds: float = 0.5

    cors_origins: list[str] = ["http://localhost:3000"]
    rate_limit_per_minute: int = 60

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    github_max_repos: int = 30
    github_commits_per_repo: int = 15
    github_signal_repos: int = 5  # top repos for languages/contributors fetch

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    cerebras_api_key: str = ""
    cerebras_model: str = "llama3.1-70b"

    cache_github_ttl: int = 21600       # 6 hours
    cache_narrative_ttl: int = 2592000  # 30 days
    cache_analysis_ttl: int = 3600      # 1 hour

    eval_judge_providers: list[str] = ["deterministic"]
    eval_openai_base_url: str = ""
    eval_openai_api_key: str = ""
    eval_openai_model: str = ""
    eval_sample_rate: float = 0.1


settings = Settings()

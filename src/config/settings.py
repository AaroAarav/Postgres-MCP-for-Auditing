from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/postgres",
        description="PostgreSQL connection string"
    )
    
    # Production Hardening Settings
    pool_min_size: int = Field(default=2, description="Minimum number of connections to keep open")
    pool_max_size: int = Field(default=10, description="Maximum number of connections allowed in the pool")
    pool_timeout: float = Field(default=30.0, description="Seconds to wait for an available connection")
    
    # Security: Prevent LLM queries from hanging the database
    statement_timeout_ms: int = Field(default=15000, description="Max execution time for a query (15 seconds)")

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str 
    anthropic_api_key: str 
    jwt_secret: str 
    credential_encryption_key: str 

settings = Settings()


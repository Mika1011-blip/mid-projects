from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL : str
    S3_ENDPOINT : str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY : str
    S3_BUCKET : str
    S3_REGION : str
    S3_SECURE : bool
    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8",
        extra = "ignore",
    )

settings = Settings()
def check_settings_attributes():
    print(f"""
          DATABASE_URL:{settings.DATABASE_URL}
          S3_ENDPOINT:{settings.S3_ENDPOINT}
          S3_ACCESS_KEY:{settings.S3_ACCESS_KEY}
          S3_SECRET_KEY:{settings.S3_SECRET_KEY}
          S3_BUCKET:{settings.S3_BUCKET}
          S3_REGION:{settings.S3_REGION}
          S3_SECURE:{settings.S3_SECURE}
""")
    return
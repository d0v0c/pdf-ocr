from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    # Pydantic 默认不区分大小写
    google_api_key_free: str
    google_api_key_paid: str
    STAMP_PATH: Path = Path("./stamp.png").resolve()

    # 指定从哪个文件读取环境变量
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# 在这里实例化一次，确保整个应用只读取一次文件
settings = Settings()
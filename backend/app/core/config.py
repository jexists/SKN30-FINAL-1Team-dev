"""애플리케이션 설정.

환경변수를 읽는 유일한 창구입니다.
코드 다른 곳에서 os.getenv 를 직접 호출하지 마세요.
"""

from typing import Literal, Self
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["local", "test", "production"]
    debug: bool = True

    # 프론트 개발 서버 주소. 쉼표로 여러 개 지정 가능.
    cors_origins: str = "http://localhost:5173"

    # Supabase 등에서 받은 접속 문자열을 그대로 넣으면 됩니다.
    # 드라이버 접두사(+asyncpg)는 아래에서 자동으로 붙입니다.
    database_url: str = ""

    session_secret: SecretStr = Field(min_length=32)
    session_ttl_seconds: int = Field(default=28_800, ge=300, le=86_400)
    login_max_attempts: int = Field(default=5, ge=1, le=20)
    login_window_seconds: int = Field(default=60, ge=10, le=3_600)

    # 공유 개발 DB에 합성 계정을 넣는 일회성 seed 전용 값입니다.
    demo_filled_manager_login_id: str = ""
    demo_filled_member_login_id: str = ""
    demo_filled_member2_login_id: str = ""
    demo_empty_manager_login_id: str = ""
    demo_empty_member_login_id: str = ""
    demo_empty_member2_login_id: str = ""
    demo_password: SecretStr = SecretStr("")

    # LLM 공급자. API key 는 서버 프로세스 안에서만 쓰고 응답이나 로그에 남기지 않는다.
    llm_api_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    @property
    def llm_configured(self) -> bool:
        """LLM 호출에 필요한 값이 모두 있는지. 없으면 기능을 503 으로 막는다."""
        return bool(self.llm_api_url and self.llm_api_key.get_secret_value() and self.llm_model)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def session_cookie_secure(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        if self.app_env != "production":
            return self
        if self.debug:
            raise ValueError("production에서는 DEBUG=false여야 합니다.")
        if not self.cors_origin_list:
            raise ValueError("production CORS origin이 비어 있습니다.")
        for origin in self.cors_origin_list:
            parts = urlsplit(origin)
            if (
                parts.scheme != "https"
                or not parts.hostname
                or parts.username is not None
                or parts.password is not None
                or parts.path
                or parts.query
                or parts.fragment
            ):
                raise ValueError("production CORS origin은 경로 없는 HTTPS origin이어야 합니다.")
        return self

    @property
    def async_database_url(self) -> str:
        """앱이 실제로 쓰는 접속 문자열 (asyncpg).

        SQLAlchemy 는 postgresql:// 만으로는 어떤 드라이버를 쓸지 모릅니다.
        .env 에는 Supabase 가 준 문자열을 그대로 두고 여기서 접두사를 붙입니다.
        """
        return _with_driver(self.database_url, "postgresql+asyncpg")


def _with_driver(url: str, driver: str) -> str:
    """postgresql:// → postgresql+asyncpg:// 처럼 드라이버 접두사를 보정한다."""
    if not url:
        return url
    parts = urlsplit(url)
    if "+" in parts.scheme:
        return url
    return urlunsplit(parts._replace(scheme=driver))


settings = Settings()

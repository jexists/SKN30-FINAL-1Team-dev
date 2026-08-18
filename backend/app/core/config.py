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

    # 로그인 시도 제한은 IP 단위로만 겁니다. 계정 단위 버킷은 두지 않습니다.
    login_max_attempts: int = Field(default=5, ge=1, le=20)
    login_window_seconds: int = Field(default=60, ge=10, le=3_600)

    # refresh 쿠키 수명. 갱신할 때마다 다시 내려 미사용 기간만 만료로 이어집니다.
    # Supabase Dashboard 의 Inactivity timeout 과 같은 값으로 맞춥니다.
    refresh_cookie_max_age_seconds: int = Field(default=30 * 86_400, ge=3_600, le=90 * 86_400)

    # LLM 공급자. API key 는 서버 프로세스 안에서만 쓰고 응답이나 로그에 남기지 않는다.
    llm_api_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    # Supabase Auth. password login 은 secret 이 아니라 publishable 키를 씁니다.
    # 두 키 모두 서버 프로세스 안에서만 쓰고 브라우저로 보내지 않습니다.
    supabase_publishable_key: SecretStr = SecretStr("")

    # Supabase Storage. secret 키는 RLS 를 우회하므로 서버에서만 쓴다.
    supabase_secret_key: SecretStr = SecretStr("")
    supabase_storage_bucket: str = ""
    # 보통은 DATABASE_URL 에서 뽑아 쓴다. 다른 호스트를 쓸 때만 채운다.
    supabase_url: str = ""
    upload_max_bytes: int = Field(default=50 * 1024 * 1024, gt=0, le=1024 * 1024 * 1024)

    @property
    def supabase_project_url(self) -> str:
        """Auth/Storage REST 주소. DATABASE_URL 의 `postgres.<project_ref>` 에서 뽑는다."""
        if self.supabase_url:
            return self.supabase_url.rstrip("/")
        user = urlsplit(self.database_url).username or ""
        _, _, project_ref = user.partition(".")
        return f"https://{project_ref}.supabase.co" if project_ref else ""

    @property
    def auth_configured(self) -> bool:
        """Supabase Auth 호출에 필요한 값이 모두 있는지. 없으면 인증을 503 으로 막는다."""
        return bool(self.supabase_project_url and self.supabase_publishable_key.get_secret_value())

    @property
    def storage_configured(self) -> bool:
        """업로드에 필요한 값이 모두 있는지. 없으면 기능을 503 으로 막는다."""
        return bool(
            self.supabase_project_url
            and self.supabase_secret_key.get_secret_value()
            and self.supabase_storage_bucket
        )

    @property
    def llm_configured(self) -> bool:
        """LLM 호출에 필요한 값이 모두 있는지. 없으면 기능을 503 으로 막는다."""
        return bool(self.llm_api_url and self.llm_api_key.get_secret_value() and self.llm_model)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def session_cookie_secure(self) -> bool:
        """access/refresh 쿠키가 함께 쓰는 Secure 플래그."""
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

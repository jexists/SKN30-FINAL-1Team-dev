"""애플리케이션 설정.

환경변수를 읽는 유일한 창구입니다.
코드 다른 곳에서 os.getenv 를 직접 호출하지 마세요.
"""

from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

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
    # 비용·외부 데이터가 발생하는 LLM/DB 실통합 테스트는 명시적으로 켭니다.
    run_integration_tests: bool = False

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
    llm_provider: Literal["external", "ollama"] = "external"
    llm_api_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    # OpenAI를 직접 사용할 때의 관용적인 이름도 지원한다. LLM_API_KEY가
    # 있으면 그것을 우선하고, 비어 있을 때만 OPENAI_API_KEY를 사용한다.
    openai_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=180.0, gt=0, le=300)

    # 문서 청크 임베딩. 비워 두면 RAG는 출처 보존 키워드 검색으로 동작한다.
    embedding_provider: Literal["none", "external", "local"] = "none"
    embedding_api_url: str = ""
    embedding_api_key: SecretStr = SecretStr("")
    embedding_model: str = ""
    embedding_local_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    # 스캔 PDF·이미지 OCR. Runpod Serverless, Azure 또는 선택적 로컬 엔진을 지원한다.
    ocr_provider: Literal["none", "runpod", "azure", "local"] = "none"
    # Runpod 자체 워커 또는 공개 MinerU 워커의 입출력 계약을 선택한다.
    ocr_runpod_contract: Literal["salesluv", "mineru"] = "salesluv"
    ocr_local_language: str = "korean"
    ocr_api_url: str = ""
    ocr_api_key: SecretStr = SecretStr("")
    # runsync 대기시간보다 여유 있게 잡아 클라이언트가 먼저 연결을 끊지 않도록 한다.
    ocr_timeout_seconds: float = Field(default=150.0, gt=0, le=300)
    ocr_runpod_wait_seconds: int = Field(default=120, ge=1, le=300)
    ocr_runpod_inline_max_bytes: int = Field(default=14 * 1024 * 1024, gt=0, le=20 * 1024 * 1024)
    ocr_runpod_signed_url_expires_seconds: int = Field(default=300, ge=60, le=3_600)
    # 원격 장애 시 로컬 OCR이 과부하되지 않도록 프로세스별 동시 실행 수를 제한한다.
    ocr_max_concurrency: int = Field(default=2, ge=1, le=8)
    business_card_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0, le=50 * 1024 * 1024)
    business_card_max_side: int = Field(default=2_400, ge=640, le=6_000)
    pdf_inspector_model_directory: str = ""
    paddlex_cache_home: str = ""

    # 자료실 보관 정책. 임시 결과·미승인 원본·승인/수정 이력을 서로 다른
    # 수명으로 관리한다. 환경변수로만 조정하고 코드에 비밀값을 두지 않는다.
    document_review_draft_retention_days: int = Field(default=7, ge=1, le=30)
    document_unapproved_file_retention_days: int = Field(default=30, ge=1, le=365)
    document_audit_log_retention_days: int = Field(default=1_825, ge=365, le=3_650)

    # HWP5 추출기 경로. 비워 두면 PATH에서 hwp5txt 또는 hwp5txt.exe를 찾는다.
    hwp5txt_path: str = ""
    # hwp5txt가 없을 때 사용할 LibreOffice 실행 파일 경로.
    soffice_path: str = ""

    # 미팅 음성은 저장하지 않고 OpenAI 전사 API 로 바로 보낸다.
    stt_api_key: SecretStr = SecretStr("")
    stt_model: str = "gpt-4o-transcribe"
    stt_timeout_seconds: float = Field(default=120.0, gt=0, le=300)
    stt_max_bytes: int = Field(default=25 * 1024 * 1024, gt=0, le=25 * 1024 * 1024)

    # 모델 산출물은 Git에 넣지 않고 배포 환경에서 이 디렉터리에 읽기 전용으로 주입한다.
    deal_model_dir: Path = Path(__file__).resolve().parents[2] / "pipeline" / "artifacts"

    # Supabase Auth. password login 은 secret 이 아니라 publishable 키를 씁니다.
    # 두 키 모두 서버 프로세스 안에서만 쓰고 브라우저로 보내지 않습니다.
    supabase_publishable_key: SecretStr = SecretStr("")

    # 계정을 발급할 수 있는 Supabase 사용자 id 목록 (쉼표 구분).
    # 권한의 근거를 DB 밖에 둔다. member 행만 고쳐서는 어드민이 될 수 없다.
    admin_user_ids: str = ""

    # 초대 메일이 착지할 프론트 주소. Supabase Dashboard 의 Redirect URLs 에도 같은 값을 등록한다.
    frontend_base_url: str = "http://localhost:5173"

    # 계정 요청(/signup)이 도착하는 팀 Discord 채널의 웹훅.
    # URL 자체가 곧 채널에 글을 쓸 권한이라 비밀값으로 다룬다.
    discord_webhook_url: SecretStr = SecretStr("")
    discord_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

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
    def admin_user_id_set(self) -> frozenset[UUID]:
        """계정을 발급할 수 있는 사용자들. 형식이 틀린 값은 조용히 버리지 않는다.

        조용히 버리면 오타 하나로 어드민이 사라지고, 그 사실을 403 을 받고 나서야 안다.
        """
        ids = [part.strip() for part in self.admin_user_ids.split(",") if part.strip()]
        try:
            return frozenset(UUID(value) for value in ids)
        except ValueError as error:
            raise ValueError("ADMIN_USER_IDS 는 쉼표로 구분한 UUID 목록이어야 합니다.") from error

    @property
    def admin_configured(self) -> bool:
        """계정 발급에 필요한 값이 모두 있는지. 없으면 기능을 503 으로 막는다."""
        return bool(
            self.admin_user_id_set
            and self.supabase_project_url
            and self.supabase_secret_key.get_secret_value()
            and self.frontend_base_url
        )

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
        if self.llm_provider == "ollama":
            return bool(self.llm_api_url and self.llm_model)
        return bool(self.llm_api_url and self.effective_llm_api_key and self.llm_model)

    @property
    def effective_llm_api_key(self) -> str:
        """LLM_API_KEY를 우선하고 없을 때 OPENAI_API_KEY를 사용한다."""
        return self.llm_api_key.get_secret_value() or self.openai_api_key.get_secret_value()

    @property
    def embedding_configured(self) -> bool:
        """임베딩 호출에 필요한 값이 모두 있는지 확인한다."""
        if self.embedding_provider == "local":
            return bool(self.embedding_local_model)
        if self.embedding_provider == "none":
            return False
        return bool(
            self.embedding_api_url
            and self.embedding_api_key.get_secret_value()
            and self.embedding_model
        )

    @property
    def ocr_configured(self) -> bool:
        """OCR 제공자 호출에 필요한 값이 모두 있는지 확인한다."""
        if self.ocr_provider == "local":
            return True
        if self.ocr_provider == "runpod" and _contains_endpoint_placeholder(self.ocr_api_url):
            return False
        return bool(
            self.ocr_provider != "none" and self.ocr_api_url and self.ocr_api_key.get_secret_value()
        )

    @property
    def stt_configured(self) -> bool:
        """STT 호출에 필요한 값이 모두 있는지. 없으면 기능을 503 으로 막는다."""
        return bool(self.stt_api_key.get_secret_value() and self.stt_model)

    @property
    def discord_configured(self) -> bool:
        """계정 요청 알림에 필요한 값이 있는지. 없으면 기능을 503 으로 막는다."""
        return bool(self.discord_webhook_url.get_secret_value())

    @property
    def cors_origin_list(self) -> list[str]:
        """쉼표로 구분된 CORS origin 설정을 정리된 목록으로 반환한다."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def session_cookie_secure(self) -> bool:
        """access/refresh 쿠키가 함께 쓰는 Secure 플래그."""
        return self.app_env == "production"

    @model_validator(mode="after")
    def validate_admin_user_ids(self) -> Self:
        """형식이 틀린 목록은 부팅에서 잡는다. 403 을 받고 나서 알게 하지 않는다."""
        _ = self.admin_user_id_set
        return self

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        """운영 환경의 필수 보안 설정과 URL 계약을 검증한다."""
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


def _contains_endpoint_placeholder(url: str) -> bool:
    """문서에 적힌 Runpod URL 템플릿을 실제 엔드포인트로 오인하지 않는다."""
    return any(marker in url for marker in ("{ENDPOINT_ID}", "<ENDPOINT_ID>"))


settings = Settings()

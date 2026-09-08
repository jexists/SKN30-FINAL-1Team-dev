"""실제 앱 import 경계에서 production 설정을 검증한다. 외부 연결은 하지 않는다."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("debug", "origins", "error"),
    [
        ("true", "https://salesluv.example", "DEBUG=false"),
        ("false", "", "CORS origin이 비어"),
        ("false", " , ", "CORS origin이 비어"),
        ("false", "http://salesluv.example", "경로 없는 HTTPS"),
        ("false", "https://salesluv.example/path", "경로 없는 HTTPS"),
        ("false", "https://salesluv.example?query=1", "경로 없는 HTTPS"),
        ("false", "https://salesluv.example#fragment", "경로 없는 HTTPS"),
        ("false", "https://user@salesluv.example", "경로 없는 HTTPS"),
        ("false", "https://salesluv.example,http://other.example", "경로 없는 HTTPS"),
        ("false", "*", "경로 없는 HTTPS"),
    ],
)
def test_invalid_production_settings_prevent_app_import(tmp_path, debug, origins, error):
    result = _import_app(tmp_path, debug=debug, origins=origins)
    assert result.returncode != 0
    assert error in result.stderr
    assert "APP_IMPORT_OK" not in result.stdout


def test_valid_production_settings_allow_app_import(tmp_path):
    result = _import_app(
        tmp_path,
        debug="false",
        origins="https://salesluv.example, https://other.example",
    )
    assert result.returncode == 0, result.stderr
    assert "APP_IMPORT_OK" in result.stdout


def _import_app(tmp_path, *, debug, origins):
    # 부모 프로세스의 키·DB 주소를 넘기지 않고, .env 없는 디렉터리에서 시작한다.
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    }
    env.update(
        APP_ENV="production",
        DEBUG=debug,
        CORS_ORIGINS=origins,
        PYTHONPATH=str(Path(__file__).resolve().parents[1]),
        PYTHONIOENCODING="utf-8",
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.main import app; "
            "from app.core.config import settings; "
            "assert settings.session_cookie_secure; print('APP_IMPORT_OK')",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

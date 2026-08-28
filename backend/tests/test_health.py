import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# DB 가 없는 환경(CI 등)에서는 건너뛴다.
# 앱 import 자체는 DATABASE_URL 없이도 되어야 하므로 위 테스트는 항상 돈다.
@pytest.mark.skipif(
    not settings.run_integration_tests or not settings.database_url,
    reason="실통합 테스트 비활성화 또는 DATABASE_URL 미설정",
)
def test_health_db_connects():
    response = client.get("/api/health/db")

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "database": "connected"}

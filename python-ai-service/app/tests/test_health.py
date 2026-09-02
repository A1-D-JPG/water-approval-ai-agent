from fastapi.testclient import TestClient

from app.main import app
from app.services import review_engine


client = TestClient(app)


def test_health_returns_ok_when_kb_is_available(monkeypatch):
    """知识库正常时，服务状态应为 ok。"""

    monkeypatch.setattr(
        review_engine,
        "kb_status",
        lambda: {
            "chroma_exists": True,
            "vector_count": 106,
            "vector_error": "",
            "knowledge_file_count": 8,
            "embedding_model": "LocalHashEmbeddings",
        },
    )

    response = client.get(
        "/health",
        headers={"X-Request-Id": "health-ok-test"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "python-ai-service"
    assert body["version"] == "2.0.0"
    assert body["knowledge_base"]["vector_count"] == 106
    assert response.headers["X-Request-Id"] == "health-ok-test"


def test_health_returns_degraded_when_kb_has_error(monkeypatch):
    """知识库异常时，服务仍能响应，但状态应为 degraded。"""

    monkeypatch.setattr(
        review_engine,
        "kb_status",
        lambda: {
            "chroma_exists": False,
            "vector_count": 0,
            "vector_error": "ChromaDB connection failed",
            "knowledge_file_count": 0,
            "embedding_model": "LocalHashEmbeddings",
        },
    )

    response = client.get("/health")

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "degraded"
    assert body["knowledge_base"]["vector_error"]


def test_readiness_returns_503_when_kb_is_empty(monkeypatch):
    """知识库没有可用向量时，就绪检查必须拒绝接收业务流量。"""

    monkeypatch.setattr(
        review_engine,
        "kb_status",
        lambda: {
            "chroma_exists": True,
            "vector_count": 0,
            "vector_error": "",
            "knowledge_file_count": 8,
            "embedding_model": "LocalHashEmbeddings",
        },
    )

    response = client.get("/health/ready")

    assert response.status_code == 503

    body = response.json()
    assert body["status"] == "degraded"
    assert body["knowledge_base"]["vector_count"] == 0


def test_liveness_returns_ok_without_checking_knowledge_base(monkeypatch):
    """存活检查不得依赖知识库、模型或外部服务。"""

    def unexpected_kb_call():
        raise AssertionError("liveness endpoint must not query the knowledge base")

    monkeypatch.setattr(review_engine, "kb_status", unexpected_kb_call)

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "python-ai-service",
        "version": "2.0.0",
    }

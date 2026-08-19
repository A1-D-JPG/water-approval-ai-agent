from fastapi.testclient import TestClient

from app.main import app
from app.services import tool_service


client = TestClient(app)


def test_unknown_tool_returns_readable_error():
    """调用不存在的工具时，应返回统一的 404 错误结构。"""

    response = client.post(
        "/mcp/call",
        headers={"X-Request-Id": "test-tool-not-found"},
        json={
            "name": "not_exists",
            "arguments": {},
        },
    )

    assert response.status_code == 404

    body = response.json()
    assert body["code"] == "TOOL_NOT_FOUND"
    assert body["message"] == "工具不存在：not_exists"
    assert body["request_id"] == "test-tool-not-found"
    assert body["details"] is None

    assert response.headers["X-Request-Id"] == "test-tool-not-found"


def test_tool_runtime_failure_returns_readable_error(monkeypatch):
    """底层依赖异常时，接口不能直接暴露 Python 堆栈。"""

    def fake_search_failure(query: str, top_k: int):
        raise RuntimeError("模拟 ChromaDB 连接失败")

    monkeypatch.setattr(
        tool_service.review_engine,
        "knowledge_search",
        fake_search_failure,
    )

    response = client.post(
        "/mcp/call",
        headers={"X-Request-Id": "test-tool-execution-failed"},
        json={
            "name": "knowledge_search",
            "arguments": {
                "query": "取水许可需要哪些材料",
                "top_k": 3,
            },
        },
    )

    assert response.status_code == 422

    body = response.json()
    assert body["code"] == "TOOL_EXECUTION_FAILED"
    assert "knowledge_search" in body["message"]
    assert "执行失败" in body["message"]
    assert body["request_id"] == "test-tool-execution-failed"
    assert "模拟 ChromaDB 连接失败" in body["details"]

    assert response.headers["X-Request-Id"] == "test-tool-execution-failed"
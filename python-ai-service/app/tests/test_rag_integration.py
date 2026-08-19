import pytest

from app.rag.service import guarded_search
from app.services import review_engine


@pytest.mark.integration
def test_real_chroma_search_returns_source_and_score():
    """使用本地 ChromaDB 完成一次真实语义检索。"""

    status = review_engine.kb_status()

    assert status["chroma_exists"] is True
    assert status["vector_count"] > 0
    assert status["vector_error"] == ""

    result = guarded_search(
        query="申请取水许可证需要提交哪些材料",
        top_k=3,
    )

    assert result["decision"] == "ANSWERED"
    assert result["retrieval_mode"] == "bge_only"
    assert len(result["items"]) > 0
    assert len(result["items"]) <= 3
    assert len(result["citations"]) == len(result["items"])

    for item in result["items"]:
        assert isinstance(item["content"], str)
        assert item["content"].strip()
        assert "\n\n\n" not in item["content"]

        assert isinstance(item["source"], str)
        assert item["source"].strip()

        assert isinstance(item["score"], (int, float))
        assert item["score"] >= 0

        assert isinstance(item["chunk_index"], int)
        assert item["chunk_index"] >= 0
        assert item["citation_id"] == f"{item['source']}#chunk-{item['chunk_index'] + 1}"

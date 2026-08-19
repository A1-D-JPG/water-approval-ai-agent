from app.rag import service
from app.schemas import RAGQueryResponse


def test_llm_grounded_answer_uses_real_citation_whitelist(monkeypatch):
    captured = {}

    class FakeResponse:
        content = "需要提交批准文件。[真实来源.docx#chunk-1]"

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def invoke(self, messages):
            captured["messages"] = messages
            return FakeResponse()

    monkeypatch.setenv("RAG_LLM_GENERATION_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(service, "ChatOpenAI", FakeChatOpenAI)
    items = [
        {
            "content": "申请人应提交建设项目批准文件。",
            "source": "真实来源.docx",
            "citation_id": "真实来源.docx#chunk-1",
        }
    ]

    answer, mode = service._generate_grounded_answer("需要哪些材料", items)

    assert mode == "llm_grounded"
    assert "[真实来源.docx#chunk-1]" in answer
    prompt = str(captured["messages"])
    assert "[真实来源.docx#chunk-1]" in prompt
    assert "[文件.docx#chunk-1]" not in prompt


def test_rag_search_returns_content_source_and_score(monkeypatch):
    """相关问题的检索结果必须包含正文、来源和分数。"""

    def fake_knowledge_search(query: str, top_k: int):
        assert query == "取水许可需要提交哪些材料"
        assert top_k == 3

        return {
            "tool": "knowledge_search",
            "query": query,
            "retrieval_mode": "bge_only",
            "items": [
                {
                    "content": "申请取水许可应当提交取水许可申请书及相关证明材料。",
                    "source": "取水许可办理需资料及流程.docx",
                    "chunk_index": 0,
                    "citation_id": "取水许可办理需资料及流程.docx#chunk-1",
                    "score": 0.125,
                }
            ],
            "citations": [
                {
                    "citation_id": "取水许可办理需资料及流程.docx#chunk-1",
                    "source": "取水许可办理需资料及流程.docx",
                    "chunk_index": 0,
                }
            ],
        }

    monkeypatch.setattr(
        service.review_engine,
        "knowledge_search",
        fake_knowledge_search,
    )

    result = service.guarded_search(
        query="取水许可需要提交哪些材料",
        top_k=3,
    )

    assert result["decision"] == "ANSWERED"
    assert result["message"] == "已返回相关知识片段。"
    assert result["answer_mode"] == "extractive_grounded"
    assert "取水许可办理需资料及流程.docx#chunk-1" in result["answer"]
    assert len(result["items"]) == 1

    item = result["items"][0]
    assert item["content"]
    assert item["source"] == "取水许可办理需资料及流程.docx"
    assert isinstance(item["score"], float)
    assert item["citation_id"] == "取水许可办理需资料及流程.docx#chunk-1"

    response = RAGQueryResponse.model_validate(result).model_dump()
    assert response["retrieval_mode"] == "bge_only"
    assert response["answer"] == result["answer"]
    assert response["citations"][0]["citation_id"] == item["citation_id"]


def test_unrelated_question_is_refused_without_search(monkeypatch):
    """无关问题应直接拒答，并且不能调用向量数据库。"""

    def should_not_be_called(*args, **kwargs):
        raise AssertionError("无关问题不应该调用知识库检索")

    monkeypatch.setattr(
        service.review_engine,
        "knowledge_search",
        should_not_be_called,
    )

    result = service.guarded_search(
        query="请告诉我今天杭州天气怎么样",
        top_k=3,
    )

    assert result["decision"] == "REFUSED"
    assert "涉水审批材料审核无关" in result["message"]
    assert result["retrieval_mode"] == "none"
    assert result["answer"] == ""
    assert result["answer_mode"] == "none"
    assert result["items"] == []
    assert result["citations"] == []


def test_industry_classification_question_passes_domain_gate(monkeypatch):
    def fake_knowledge_search(query: str, top_k: int):
        assert "国民经济行业分类" in query
        return {
            "retrieval_mode": "bge_only",
            "items": [
                {
                    "content": "011 谷物种植",
                    "source": "国民经济分类国标.pdf",
                    "chunk_index": 0,
                    "citation_id": "国民经济分类国标.pdf#chunk-1",
                    "score": 0.1,
                }
            ],
            "citations": [
                {
                    "citation_id": "国民经济分类国标.pdf#chunk-1",
                    "source": "国民经济分类国标.pdf",
                    "chunk_index": 0,
                }
            ],
        }

    monkeypatch.setattr(service.review_engine, "knowledge_search", fake_knowledge_search)
    result = service.guarded_search("011谷物种植在国民经济行业分类中属于什么类别？", 3)

    assert result["decision"] == "ANSWERED"
    assert result["items"][0]["source"] == "国民经济分类国标.pdf"

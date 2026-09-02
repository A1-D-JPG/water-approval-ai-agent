from __future__ import annotations

from typing import Any

import pytest

from app.services import review_engine


class FakeVectorStore:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.add_calls = 0
        self.deleted_ids: list[str] = []
        self.fail_add = False

    def get(self, include: list[str] | None = None) -> dict[str, Any]:
        return {
            "ids": list(self.records),
            "metadatas": [record["metadata"] for record in self.records.values()],
        }

    def add_texts(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        if self.fail_add:
            raise RuntimeError("simulated embedding failure")
        self.add_calls += 1
        for item_id, text, metadata in zip(ids, texts, metadatas, strict=True):
            self.records[item_id] = {"text": text, "metadata": metadata}

    def delete(self, ids: list[str]) -> None:
        self.deleted_ids.extend(ids)
        for item_id in ids:
            self.records.pop(item_id, None)


def test_incremental_build_adds_skips_updates_and_deletes(tmp_path, monkeypatch):
    docs_dir = tmp_path / "knowledge_docs"
    source_dir = tmp_path / "source_docs"
    docs_dir.mkdir()
    source_dir.mkdir()
    document = docs_dir / "测试规则.txt"
    document.write_text("申请取水许可证需要提交批准文件和监测报告。", encoding="utf-8")

    store = FakeVectorStore()
    monkeypatch.setattr(review_engine, "DOCS_DIR", docs_dir)
    monkeypatch.setattr(review_engine, "SOURCE_DOCS_DIR", source_dir)
    monkeypatch.setattr(review_engine, "vector_store", lambda: store)

    first = review_engine.build_knowledge_base()
    assert first["added"] == 1
    assert first["updated"] == 0
    assert first["deleted"] == 0
    assert first["unchanged"] == 0
    assert first["embedded_chunks"] == 1
    assert store.add_calls == 1

    second = review_engine.build_knowledge_base()
    assert second["added"] == 0
    assert second["updated"] == 0
    assert second["deleted"] == 0
    assert second["unchanged"] == 1
    assert second["embedded_chunks"] == 0
    assert store.add_calls == 1

    old_ids = set(store.records)
    document.write_text("申请取水许可证需要提交批准文件、工程图和水质监测报告。", encoding="utf-8")
    third = review_engine.build_knowledge_base()
    assert third["added"] == 0
    assert third["updated"] == 1
    assert third["deleted"] == 0
    assert third["unchanged"] == 0
    assert third["embedded_chunks"] == 1
    assert old_ids.isdisjoint(store.records)

    document.unlink()
    fourth = review_engine.build_knowledge_base()
    assert fourth["added"] == 0
    assert fourth["updated"] == 0
    assert fourth["deleted"] == 1
    assert fourth["unchanged"] == 0
    assert fourth["embedded_chunks"] == 0
    assert store.records == {}


def test_failed_update_keeps_previous_vectors(tmp_path, monkeypatch):
    docs_dir = tmp_path / "knowledge_docs"
    source_dir = tmp_path / "source_docs"
    docs_dir.mkdir()
    source_dir.mkdir()
    document = docs_dir / "测试规则.txt"
    document.write_text("旧版本规则内容。", encoding="utf-8")

    store = FakeVectorStore()
    monkeypatch.setattr(review_engine, "DOCS_DIR", docs_dir)
    monkeypatch.setattr(review_engine, "SOURCE_DOCS_DIR", source_dir)
    monkeypatch.setattr(review_engine, "vector_store", lambda: store)
    review_engine.build_knowledge_base()
    previous_records = dict(store.records)

    document.write_text("新版本规则内容。", encoding="utf-8")
    store.fail_add = True
    with pytest.raises(RuntimeError, match="simulated embedding failure"):
        review_engine.build_knowledge_base()

    assert store.records == previous_records

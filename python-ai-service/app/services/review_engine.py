from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import docx2txt
import pdfplumber
from chromadb.config import Settings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from rank_bm25 import BM25Okapi
from app.config import load_env_file
from pypdf import PdfReader
load_env_file()
SERVICE_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = SERVICE_DIR.parent
CHROMA_DIR = SERVICE_DIR / "chroma_db"


def _configured_directory(env_name: str, default: Path) -> Path:
    """Return an absolute directory configured by environment or its default."""
    configured = os.getenv(env_name, "").strip()
    return Path(configured).expanduser().resolve() if configured else default


DOCS_DIR = _configured_directory("KNOWLEDGE_DOCS_DIR", SERVICE_DIR / "knowledge_docs")
SOURCE_DOCS_DIR = _configured_directory("KNOWLEDGE_SOURCE_DOCS_DIR", PROJECT_DIR / "资料")
EMBED_MODEL = "BAAI/bge-small-zh-v1.5"
MAX_CHUNKS_PER_FILE = int(os.getenv("KB_MAX_CHUNKS_PER_FILE", "80"))
EXCLUDED_KB_NAMES = {"README.md", "TEAM.md", ".gitkeep"}
TITLE_MATCH_BOOST = float(os.getenv("RAG_TITLE_MATCH_BOOST", "0.35"))
RAG_HYBRID_ENABLED = os.getenv("RAG_HYBRID_ENABLED", "0") == "1"
RRF_K = int(os.getenv("RAG_RRF_K", "60"))

_embeddings: Any | None = None
_vector_store: Chroma | None = None
_bm25_index: BM25Okapi | None = None
_bm25_documents: list[str] = []
_bm25_metadatas: list[dict[str, Any]] = []
_bm25_ready = False


@dataclass
class Material:
    path: Path
    text: str
    readable: bool
    error: str = ""
    doc_type: str = "UNKNOWN"
    expected_type: str = "UNKNOWN"


class LocalHashEmbeddings:
    """Deterministic fallback used when the local BGE model is unavailable."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in re.findall(r"[\w\u4e00-\u9fff]+", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            vector[index] += 1.0
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / norm for value in vector]


def embeddings() -> Any:
    global _embeddings
    if _embeddings is None:
        if os.getenv("USE_HF_EMBEDDINGS", "0") != "1":
            _embeddings = LocalHashEmbeddings()
            return _embeddings
        try:
            _embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
        except Exception:
            _embeddings = LocalHashEmbeddings()
    return _embeddings


def vector_store() -> Chroma:
    global _vector_store
    if _vector_store is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _vector_store = Chroma(
            collection_name="water-approval-rules",
            embedding_function=embeddings(),
            persist_directory=str(CHROMA_DIR),
            client_settings=Settings(anonymized_telemetry=False),
        )
    return _vector_store


def reset_vector_store() -> None:
    global _vector_store, _bm25_index, _bm25_documents, _bm25_metadatas, _bm25_ready
    _vector_store = None
    _bm25_index = None
    _bm25_documents = []
    _bm25_metadatas = []
    _bm25_ready = False
    if CHROMA_DIR.exists():
        try:
            shutil.rmtree(CHROMA_DIR)
        except PermissionError:
            # On Windows, an old uvicorn process may still hold Chroma files.
            # Reuse the existing database instead of failing service startup.
            pass


def read_unstructured_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text_parts: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
        text = "\n".join(text_parts).strip()
        if text:
            return text
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if suffix == ".docx":
        return docx2txt.process(str(path)).strip()
    if suffix == ".doc":
        try:
            return docx2txt.process(str(path)).strip()
        except Exception:
            return _read_legacy_doc_text(path)
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    if suffix in {".png", ".jpg", ".jpeg", ".bmp"}:
        return _read_image_text(path)
    raise ValueError(f"不支持的文件格式：{suffix}")


def _read_image_text(path: Path) -> str:
    parts: list[str] = []
    try:
        import pytesseract
        from PIL import Image

        parts.append(pytesseract.image_to_string(Image.open(path), lang="chi_sim+eng").strip())
    except Exception as exc:
        parts.append(f"[OCR不可用：{exc}]")

    sample_type = type_by_sample_hash(path)
    if sample_type != "UNKNOWN":
        parts.append(f"[样例图片匹配：{sample_type}]")
    return "\n".join(part for part in parts if part).strip()


def _read_legacy_doc_text(path: Path) -> str:
    data = path.read_bytes()
    text = data.decode("utf-16le", errors="ignore")
    chunks = re.findall(r"[\u4e00-\u9fffA-Za-z0-9:：；;，,。\s]{8,}", text)
    return "\n".join(chunk.strip() for chunk in chunks if chunk.strip())


def load_materials(paths: list[str]) -> list[Material]:
    materials: list[Material] = []
    for item in paths:
        path = Path(item)
        try:
            text = read_unstructured_text(path)
            expected_type = expected_type_by_name(path.name)
            doc_type = detect_document_type(path, text)
            materials.append(
                Material(
                    path=path,
                    text=text,
                    readable=bool(text),
                    doc_type=doc_type,
                    expected_type=expected_type,
                )
            )
        except Exception as exc:
            materials.append(Material(path=path, text="", readable=False, error=str(exc)))
    return materials


def build_knowledge_base(reset: bool = False) -> dict[str, Any]:
    if reset:
        reset_vector_store()
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    source_dirs = [DOCS_DIR, SOURCE_DOCS_DIR]
    files: list[Path] = []
    for folder in source_dirs:
        if folder.exists():
            files.extend(
                p
                for p in folder.iterdir()
                if p.is_file()
                and p.suffix.lower() in {".pdf", ".doc", ".docx", ".txt", ".md"}
                and p.name not in EXCLUDED_KB_NAMES
                and not p.name.startswith("~$")
            )

    splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=120)
    docs: list[str] = []
    metas: list[dict[str, Any]] = []
    seen_files: set[str] = set()
    unique_files: list[Path] = []
    for file in files:
        file_key = file.name.lower()
        if file_key not in seen_files:
            seen_files.add(file_key)
            unique_files.append(file)

    for file in unique_files:
        try:
            text = read_unstructured_text(file)
        except Exception:
            continue
        for i, chunk in enumerate(splitter.split_text(text)):
            if i >= MAX_CHUNKS_PER_FILE:
                break
            if chunk.strip():
                docs.append(chunk)
                metas.append({"source": file.name, "path": str(file), "chunk": i})
    if docs:
        ids = [
            f"{hashlib.sha1(m['path'].encode('utf-8')).hexdigest()[:12]}-{m['chunk']}"
            for m in metas
        ]
        vector_store().add_texts(docs, metadatas=metas, ids=ids)
    return {"files": len(unique_files), "chunks": len(docs), "sources": [p.name for p in unique_files]}


def _normalize_title(text: str) -> str:
    """Normalize a document title or query for conservative exact-title matching."""
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text).lower()


def _title_match_bonus(query: str, source: str | None) -> float:
    """Boost only when the query explicitly names the retrieved document."""
    if not source:
        return 0.0
    normalized_query = _normalize_title(query)
    title = _normalize_title(Path(source).stem)
    title_without_year = re.sub(r"\d{4}", "", title)
    candidates = {title, title_without_year}
    if any(len(candidate) >= 4 and candidate in normalized_query for candidate in candidates):
        return TITLE_MATCH_BOOST
    return 0.0


def _citation_id(metadata: dict[str, Any]) -> str:
    source = str(metadata.get("source") or "unknown-source")
    chunk = int(metadata.get("chunk", -1))
    return f"{source}#chunk-{chunk + 1}" if chunk >= 0 else source


def _clean_excerpt(text: str, limit: int = 500) -> str:
    """Normalize document-extraction whitespace for API and UI display only."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[\t\f\v ]+", " ", cleaned)
    cleaned = re.sub(r"(?<=[\u4e00-\u9fff]) (?=[\u4e00-\u9fff])", "", cleaned)
    cleaned = re.sub(r"\n +", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()[:limit]


def _tokenize_for_bm25(text: str) -> list[str]:
    """Use Chinese characters and alphanumeric words as a dependency-free BM25 tokenizer."""
    return re.findall(r"[\u4e00-\u9fff]|[a-z0-9]+", text.lower())


def _load_bm25_index() -> tuple[BM25Okapi | None, list[str], list[dict[str, Any]]]:
    """Build a lexical index from the persisted Chroma chunks on first use."""
    global _bm25_index, _bm25_documents, _bm25_metadatas, _bm25_ready
    if not _bm25_ready:
        stored = vector_store().get(include=["documents", "metadatas"])
        documents = [text for text in (stored.get("documents") or []) if text]
        metadatas = list(stored.get("metadatas") or [])
        _bm25_documents = documents
        _bm25_metadatas = [metadata or {} for metadata in metadatas]
        tokens = [_tokenize_for_bm25(text) for text in documents]
        _bm25_index = BM25Okapi(tokens) if tokens else None
        _bm25_ready = True
    return _bm25_index, _bm25_documents, _bm25_metadatas


def _hybrid_rerank(query: str, matches: list[tuple[Document, float]], candidate_k: int) -> list[tuple[Document, float, float]]:
    """Fuse BGE and BM25 rankings with reciprocal-rank fusion (RRF)."""
    candidates: dict[tuple[str, int], tuple[Document, float]] = {}
    rrf_scores: dict[tuple[str, int], float] = {}

    def key_for(document: Document) -> tuple[str, int]:
        metadata = document.metadata
        return str(metadata.get("path") or metadata.get("source") or document.page_content), int(metadata.get("chunk", -1))

    for rank, (document, distance) in enumerate(matches, start=1):
        key = key_for(document)
        candidates[key] = (document, float(distance))
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (RRF_K + rank)

    bm25, documents, metadatas = _load_bm25_index()
    if bm25 is not None:
        scores = bm25.get_scores(_tokenize_for_bm25(query))
        lexical_ranks = sorted(range(len(scores)), key=lambda index: float(scores[index]), reverse=True)[:candidate_k]
        for rank, index in enumerate(lexical_ranks, start=1):
            if scores[index] <= 0:
                continue
            document = Document(page_content=documents[index], metadata=metadatas[index])
            key = key_for(document)
            candidates.setdefault(key, (document, float("inf")))
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (RRF_K + rank)

    reranked = [
        (document, distance, rrf_scores[key])
        for key, (document, distance) in candidates.items()
    ]
    return sorted(
        reranked,
        key=lambda item: (
            -(item[2] + _title_match_bonus(query, item[0].metadata.get("source"))),
            item[1],
        ),
    )


def knowledge_search(query: str, top_k: int = 3) -> dict[str, Any]:
    if not query:
        raise ValueError("query is required")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    # Retrieve a small semantic candidate pool first. Document-title boosting is deliberately
    # limited to exact mentions, so ordinary natural-language queries keep their BGE order.
    candidate_k = top_k * 4
    matches = vector_store().similarity_search_with_score(query, k=candidate_k)
    if RAG_HYBRID_ENABLED:
        reranked = _hybrid_rerank(query, matches, candidate_k)[:top_k]
        items = [
            {
                "content": _clean_excerpt(document.page_content),
                "source": document.metadata.get("source"),
                "chunk_index": int(document.metadata.get("chunk", -1)),
                "citation_id": _citation_id(document.metadata),
                "score": distance,
                "hybrid_score": rrf_score,
            }
            for document, distance, rrf_score in reranked
        ]
        mode = "bge_bm25_rrf"
    else:
        reranked = sorted(
            matches,
            key=lambda item: (
                float(item[1]) - _title_match_bonus(query, item[0].metadata.get("source")),
                float(item[1]),
            ),
        )[:top_k]
        items = [
            {
                "content": _clean_excerpt(doc.page_content),
                "source": doc.metadata.get("source"),
                "chunk_index": int(doc.metadata.get("chunk", -1)),
                "citation_id": _citation_id(doc.metadata),
                "score": float(score),
            }
            for doc, score in reranked
        ]
        mode = "bge_only"
    return {
        "tool": "knowledge_search",
        "retrieval_mode": mode,
        "items": items,
        "citations": [
            {
                "citation_id": item["citation_id"],
                "source": item["source"],
                "chunk_index": item["chunk_index"],
            }
            for item in items
        ],
    }


def check_completeness(material_text: str, file_names: list[str] | None = None) -> dict[str, Any]:
    file_names = file_names or []
    required_fields = ["申请人", "证件号", "联系方式", "项目名称", "取水地点", "取水用途"]
    missing_fields = [field for field in required_fields if not has_field_value(material_text, field)]
    attachment_rules = {
        "申请表": any("申请" in name or "申领表" in name for name in file_names),
        "身份证": "身份证" in material_text or any("身份证" in name for name in file_names),
        "营业执照或主体资格证明": "营业执照" in material_text or any("营业执照" in name for name in file_names),
    }
    missing_attachments = [name for name, ok in attachment_rules.items() if not ok]
    return {
        "tool": "check_completeness",
        "required_fields": required_fields,
        "missing_fields": missing_fields,
        "required_attachments": list(attachment_rules.keys()),
        "missing_attachments": missing_attachments,
        "is_complete": not missing_fields and not missing_attachments,
    }


def check_completeness_by_materials(materials: list[Material], material_text: str) -> dict[str, Any]:
    file_names = [material.path.name for material in materials]
    required_fields = ["申请人", "证件号", "联系方式", "项目名称", "取水地点", "取水用途"]
    missing_fields = [field for field in required_fields if not has_field_value(material_text, field)]
    detected_types = {material.doc_type for material in materials}
    expected_names = {material.expected_type for material in materials}
    attachment_rules = {
        "申请表": ("申请表" in detected_types) or any("申请" in name or "申领表" in name for name in file_names),
        "身份证": "身份证" in detected_types,
        "营业执照或主体资格证明": "营业执照" in detected_types,
    }
    missing_attachments = [name for name, ok in attachment_rules.items() if not ok]
    return {
        "tool": "check_completeness",
        "required_fields": required_fields,
        "missing_fields": missing_fields,
        "required_attachments": list(attachment_rules.keys()),
        "missing_attachments": missing_attachments,
        "detected_types": sorted(detected_types),
        "expected_types": sorted(expected_names),
        "is_complete": not missing_fields and not missing_attachments,
    }


def deterministic_review(materials: list[Material], application: dict[str, str] | None = None) -> dict[str, Any]:
    application = application or {}
    file_names = [m.path.name for m in materials]
    combined_text = "\n\n".join(m.text for m in materials)
    issues: list[dict[str, str]] = []

    for material in materials:
        if not material.readable:
            issues.append(make_issue("文件格式不符", "高", f"{material.path.name} 无法解析：{material.error}", "附件", "重新上传可打开的 PDF、Word 或图片文件。"))
        type_check_targets = {"身份证", "营业执照", "驾驶证"}
        if (
            material.expected_type in type_check_targets
            and material.doc_type in type_check_targets
            and material.expected_type != material.doc_type
        ):
            issues.append(
                make_issue(
                    "证照类型不符",
                    "高",
                    f"文件名显示为{material.expected_type}，但识别到的实际内容为{material.doc_type}。",
                    material.path.name,
                    f"请上传真实的{material.expected_type}附件，不能用其他证照替代。",
                )
            )

    completeness = check_completeness_by_materials(materials, combined_text)
    issues.extend(check_required_application_fields(application, combined_text))
    issues.extend(check_other_water_use(application, combined_text))
    issues.extend(check_attachment_consistency(application, materials, combined_text))
    issues.extend(check_expired_documents(materials, combined_text))
    industry_check = industry_category_check(application.get("industry_category", ""))
    if application.get("industry_category") and not industry_check["valid"]:
        issues.append(
            make_issue(
                "行业类别不规范",
                "中",
                industry_check["message"],
                "行业类别",
                industry_check["suggestion"],
            )
        )

    for item in completeness["missing_attachments"]:
        issues.append(make_issue("要件缺失", "高", f"缺少必备附件：{item}", "附件清单", f"请补充上传{item}。"))

    try:
        rag = knowledge_search("取水许可申请材料完整性 内容规范 身份证 营业执照 有效期", top_k=4)
    except Exception:
        rag = {"items": []}

    decision = "APPROVED" if not issues else "REJECTED"
    return {
        "decision": decision,
        "issues": issues,
        "suggestions": build_suggestions(issues),
        "completeness": completeness,
        "content_check": {
            "extracted": extract_all_entities(combined_text),
            "application": application,
            "industry_category_check": industry_check,
        },
        "risk_summary": risk_summary(issues),
        "knowledge_hits": rag["items"],
        "raw_length": len(combined_text),
        "files": [{"name": m.path.name, "expected_type": m.expected_type, "detected_type": m.doc_type} for m in materials],
    }


def expected_type_by_name(name: str) -> str:
    lower = name.lower()
    if "身份证" in name:
        return "身份证"
    if "驾驶证" in name or "驾照" in name:
        return "驾驶证"
    if "营业执照" in name:
        return "营业执照"
    if "申请" in name or "申领表" in name:
        return "申请表"
    return "UNKNOWN"


def detect_document_type(path: Path, text: str) -> str:
    expected_type = expected_type_by_name(path.name)
    if expected_type == "申请表":
        return "申请表"
    if expected_type in {"身份证", "营业执照"} and path.suffix.lower() in {".doc", ".docx", ".pdf", ".txt", ".md"}:
        return expected_type
    sample_type = type_by_sample_hash(path)
    if sample_type != "UNKNOWN":
        return sample_type
    if any(word in text for word in ["机动车驾驶证", "驾驶证", "准驾车型", "档案编号"]):
        return "驾驶证"
    if any(word in text for word in ["居民身份证", "公民身份号码", "身份证号", "身份号码"]):
        return "身份证"
    if any(word in text for word in ["营业执照", "统一社会信用代码", "法定代表人", "经营范围"]):
        return "营业执照"
    if any(word in text for word in ["取水许可申请", "申请书", "取水地点", "取水用途"]):
        return "申请表"
    return expected_type


def type_by_sample_hash(path: Path) -> str:
    if not SOURCE_DOCS_DIR.exists() or not path.exists():
        return "UNKNOWN"
    digest = file_sha256(path)
    matched_names: list[str] = []
    for sample in SOURCE_DOCS_DIR.iterdir():
        if sample.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp"}:
            continue
        if file_sha256(sample) != digest:
            continue
        matched_names.append(sample.name)
    if any("驾驶" in name or "驾照" in name for name in matched_names):
        return "驾驶证"
    if any("身份证" in name for name in matched_names):
        return "身份证"
    if any("营业执照" in name for name in matched_names):
        return "营业执照"
    return "UNKNOWN"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_required_application_fields(application: dict[str, str], material_text: str) -> list[dict[str, str]]:
    fields = {
        "申请人": application.get("applicant_name", ""),
        "证件号": application.get("id_number", ""),
        "联系方式": application.get("contact_phone", ""),
        "项目名称": application.get("project_name", ""),
        "取水地点": application.get("water_location", ""),
        "取水用途": application.get("water_use", ""),
    }
    issues: list[dict[str, str]] = []
    for label, value in fields.items():
        if not value:
            issues.append(make_issue("关键信息缺失", "高" if label in {"申请人", "证件号"} else "中", f"{label}为空或未填写。", label, f"请补充填写{label}。"))
    return issues


def check_other_water_use(application: dict[str, str], material_text: str) -> list[dict[str, str]]:
    water_use = application.get("water_use", "")
    material_use = first_labeled_value(material_text, ["取水用途", "用途"])
    values = [water_use, material_use]
    if not any(value.strip() == "其他" or value.strip().startswith("其他") for value in values if value):
        return []
    if any(re.match(r"其他\s*[:：/、\-]\s*[\u4e00-\u9fffA-Za-z0-9]{2,}", value.strip()) for value in values if value):
        return []
    return [make_issue("关键信息缺失", "中", "取水用途选择了“其他”，但未补充说明具体用途。", "取水用途", "请在“其他”后填写明确用途说明。")]


def check_attachment_consistency(application: dict[str, str], materials: list[Material], combined_text: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    applicant_name = application.get("applicant_name", "")
    id_number = application.get("id_number", "")

    id_text = "\n".join(m.text for m in materials if m.doc_type == "身份证")
    license_text = "\n".join(m.text for m in materials if m.doc_type == "营业执照")
    all_entities = extract_all_entities(combined_text)
    id_entities = extract_all_entities(id_text)
    license_entities = extract_all_entities(license_text)

    if applicant_name:
        names = set(id_entities["names"])
        if names and applicant_name not in names:
            issues.append(make_issue("信息不一致", "高", f"申请表申请人“{applicant_name}”与身份证附件识别姓名不一致。", "申请人/身份证附件", "请核对申请表与身份证中的姓名。"))

    if id_number:
        numbers = set(id_entities["id_numbers"])
        if numbers and id_number not in numbers:
            issues.append(make_issue("信息不一致", "高", f"申请表证件号“{id_number}”与附件识别证件号不一致。", "证件号/身份证附件", "请上传与申请人一致的身份证附件，或修正申请表证件号。"))

    credit_code = application.get("credit_code", "")
    if credit_code:
        codes = set(license_entities["credit_codes"])
        if codes and credit_code not in codes:
            issues.append(make_issue("信息不一致", "高", f"统一社会信用代码“{credit_code}”与营业执照附件不一致。", "统一社会信用代码/营业执照", "请核对企业注册信息与营业执照。"))
    return issues


def check_expired_documents(materials: list[Material], combined_text: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    today = date.today()
    for material in materials:
        dates = extract_dates(material.text)
        expiry_dates = [d for label, d in dates if label == "expiry"]
        if not expiry_dates and material.doc_type in {"身份证", "营业执照"}:
            expiry_dates = [d for _, d in dates]
        for expiry in expiry_dates:
            if expiry < today:
                issues.append(make_issue("有效期冲突", "高", f"{material.doc_type}“{material.path.name}”已过期，有效期至 {expiry.isoformat()}。", material.path.name, "请上传有效期内的身份证或营业执照。"))
                break
    if "过期" in combined_text:
        issues.append(make_issue("有效期冲突", "高", "材料文本中出现“过期”描述，请人工复核证照有效期。", "证照有效期", "请上传有效期内的证照材料。"))
    return issues


def extract_all_entities(text: str) -> dict[str, list[str]]:
    return {
        "names": extract_names(text),
        "id_numbers": sorted(set(re.findall(r"[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]", text))),
        "credit_codes": sorted(set(re.findall(r"\b[0-9A-Z]{18}\b", text.upper()))),
        "phones": sorted(set(re.findall(r"1[3-9]\d{9}", text))),
    }


def extract_names(text: str) -> list[str]:
    names = []
    for value in labeled_values(text, ["姓名", "名称", "企业名称", "申请人", "法定代表人"]):
        if value not in names:
            names.append(value)
    patterns = [
        r"(?:姓名|名称|企业名称|申请人|法定代表人)\s*[:：]\s*([\u4e00-\u9fffA-Za-z0-9（）()·]{2,40})",
        r"(?:姓名|名称|企业名称|申请人|法定代表人)\s+([\u4e00-\u9fffA-Za-z0-9（）()·]{2,40})",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = match.group(1).strip()
            if value not in names:
                names.append(value)
    return names


def extract_dates(text: str) -> list[tuple[str, date]]:
    results: list[tuple[str, date]] = []
    range_pattern = r"(?:有效期限|有效期|营业期限|经营期限)\s*[:：]?\s*\d{4}[年./-]\d{1,2}[月./-]\d{1,2}日?\s*(?:至|-|到)\s*(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})日?"
    for match in re.finditer(range_pattern, text):
        parsed = safe_date(*match.groups())
        if parsed:
            results.append(("expiry", parsed))
    if results:
        return results

    date_patterns = [
        r"(有效期限|有效期|营业期限|经营期限|至)\s*[:：]?\s*(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})日?",
        r"(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})日?\s*(?:止|到期|过期)",
    ]
    for pattern in date_patterns:
        for match in re.finditer(pattern, text):
            groups = match.groups()
            nums = groups[-3:]
            parsed = safe_date(*nums)
            if parsed:
                results.append(("expiry", parsed))
    return results


def safe_date(year: str, month: str, day: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def has_field_value(text: str, label: str) -> bool:
    value = first_labeled_value(text, [label])
    if value:
        return True
    pattern = rf"{re.escape(label)}[ \t]*[:：][ \t]*([^\n\r，。；;]{{2,}})"
    return bool(re.search(pattern, text))


def first_labeled_value(text: str, labels: list[str]) -> str:
    values = labeled_values(text, labels)
    return values[0] if values else ""


def labeled_values(text: str, labels: list[str]) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    values: list[str] = []
    stop_labels = {
        "字段", "内容", "证照类型", "申请人", "证件号", "联系方式", "项目名称", "取水地点", "取水用途",
        "行业类别", "姓名", "公民身份号码", "有效期", "企业名称", "统一社会信用代码", "法定代表人",
        "经营范围", "营业期限", "名称", "用途",
    }
    label_set = set(labels)
    for index, line in enumerate(lines):
        matched = next((label for label in label_set if line == label or line.startswith(label + "：") or line.startswith(label + ":")), "")
        if not matched:
            continue
        if "：" in line or ":" in line:
            value = re.split(r"[:：]", line, maxsplit=1)[1].strip()
        else:
            value = ""
            for next_line in lines[index + 1:]:
                if next_line in stop_labels:
                    continue
                value = next_line.strip()
                break
        if value and value not in stop_labels and value not in values:
            values.append(value)
    return values


def build_suggestions(issues: list[dict[str, str]]) -> list[str]:
    if not issues:
        return ["材料初审通过，未发现明显形式或内容规范问题。"]
    return [issue["suggestion"] for issue in issues]


def make_issue(issue_type: str, severity: str, message: str, location: str, suggestion: str) -> dict[str, str]:
    return {
        "type": issue_type,
        "severity": severity,
        "message": message,
        "location": location,
        "legal_basis": "取水许可材料初审规则、实名制申报要求及证照有效性校验规则",
        "suggestion": suggestion,
    }



# --- Extended MCP tools: keep the required tools unchanged and add optional capabilities. ---
def industry_category_check(industry_category: str) -> dict[str, Any]:
    """Check whether an industry category follows the GB/T 4754 middle-category style."""
    value = (industry_category or "").strip()
    common_categories = {
        "011": "谷物种植",
        "012": "豆类、油料和薯类种植",
        "013": "棉、麻、糖、烟草种植",
        "014": "蔬菜、食用菌及园艺作物种植",
        "015": "水果种植",
        "016": "坚果、含油果、香料和饮料作物种植",
        "017": "中药材种植",
        "019": "其他农业",
        "031": "牲畜饲养",
        "032": "家禽饲养",
        "041": "水产养殖",
        "042": "水产捕捞",
        "461": "自来水生产和供应",
        "462": "污水处理及其再生利用",
    }
    match = re.match(r"^(\d{3})\s*([一-鿿A-Za-z（）()、·\-]{2,})$", value)
    if not value:
        return {
            "tool": "industry_category_check",
            "valid": False,
            "code": "",
            "name": "",
            "message": "行业类别不能为空，应按《国民经济行业分类》填写中类，如 011谷物种植。",
            "suggestion": "请填写三位行业中类代码加名称。",
        }
    if not match:
        return {
            "tool": "industry_category_check",
            "valid": False,
            "code": "",
            "name": value,
            "message": "行业类别格式不符合三位中类代码加名称的要求。",
            "suggestion": "示例：011谷物种植、015水果种植、461自来水生产和供应。",
        }
    code, name = match.groups()
    expected = common_categories.get(code)
    valid = expected is None or expected in name or name in expected
    return {
        "tool": "industry_category_check",
        "valid": valid,
        "code": code,
        "name": name,
        "matched_standard_name": expected or "未在内置常用表中命中，建议结合知识库人工复核",
        "message": "行业类别格式符合要求。" if valid else f"行业代码 {code} 常见名称为“{expected}”，当前填写为“{name}”。",
        "suggestion": "保持当前填写。" if valid else f"建议修改为 {code}{expected}，或根据国标文件确认正确中类名称。",
    }


def extract_key_entities(material_text: str) -> dict[str, Any]:
    """Extract key entities from application materials for cross-checking."""
    text = material_text or ""
    entities = extract_all_entities(text)
    dates = extract_dates(text)
    return {
        "tool": "extract_key_entities",
        "entities": entities,
        "dates": [{"type": label, "value": value.isoformat()} for label, value in dates],
        "summary": {
            "names": len(entities.get("names", [])),
            "id_numbers": len(entities.get("id_numbers", [])),
            "credit_codes": len(entities.get("credit_codes", [])),
            "phones": len(entities.get("phones", [])),
            "dates": len(dates),
        },
    }


def risk_summary(issues: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Summarize review issues by severity and type for dashboard or report output."""
    issues = issues or []
    severity_order = ["高", "中", "低"]
    by_severity = {level: 0 for level in severity_order}
    by_type: dict[str, int] = {}
    for issue in issues:
        severity = str(issue.get("severity") or "中")
        issue_type = str(issue.get("type") or "未分类")
        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_type[issue_type] = by_type.get(issue_type, 0) + 1
    conclusion = "通过" if not issues else "不通过，需补正或人工复核"
    return {
        "tool": "risk_summary",
        "total": len(issues),
        "by_severity": by_severity,
        "by_type": by_type,
        "conclusion": conclusion,
        "suggestion": "无明显问题。" if not issues else "优先处理高风险问题，再补充中低风险材料。",
    }

def kb_status() -> dict[str, Any]:
    """Return observable knowledge-base status for demos and health checks."""
    doc_files = []
    for folder in [DOCS_DIR, SOURCE_DOCS_DIR]:
        if folder.exists():
            doc_files.extend(
                p
                for p in folder.iterdir()
                if p.is_file()
                and p.suffix.lower() in {".pdf", ".doc", ".docx", ".txt", ".md"}
                and p.name not in EXCLUDED_KB_NAMES
                and not p.name.startswith("~$")
            )
    unique_files: dict[str, Path] = {}
    for path in doc_files:
        unique_files.setdefault(path.name.lower(), path)
    try:
        vector_count = vector_store()._collection.count()
    except Exception as exc:
        vector_count = -1
        vector_error = str(exc)
    else:
        vector_error = ""
    return {
        "tool": "kb_status",
        "chroma_dir": str(CHROMA_DIR),
        "chroma_exists": CHROMA_DIR.exists(),
        "vector_count": vector_count,
        "vector_error": vector_error,
        "knowledge_file_count": len(unique_files),
        "knowledge_files": [path.name for path in unique_files.values()],
        "embedding_model": EMBED_MODEL if os.getenv("USE_HF_EMBEDDINGS", "0") == "1" else "LocalHashEmbeddings",
    }

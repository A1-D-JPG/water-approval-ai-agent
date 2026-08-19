from __future__ import annotations

from app.agents.review_agent import run_review_agent
from app.errors import AppError
from app.schemas.review import ReviewRequest, ReviewResponse
from app.services import review_engine


def review_application(request: ReviewRequest) -> ReviewResponse:
    paths = request.file_paths or ([request.file_path] if request.file_path else [])
    if not paths:
        raise AppError("MATERIAL_REQUIRED", "请至少提供一个待审核附件路径。", 400)

    materials = review_engine.load_materials(paths)
    if not materials:
        raise AppError("MATERIAL_NOT_FOUND", "未找到可审查的附件。", 404)

    application = {
        "applicant_name": request.applicant_name,
        "id_number": request.id_number,
        "project_name": request.project_name,
        "water_location": request.water_location,
        "water_use": request.water_use,
        "industry_category": request.industry_category,
        "contact_phone": request.contact_phone,
        "credit_code": request.credit_code,
    }
    rule_result = review_engine.deterministic_review(materials, application)
    material_text = "\n\n".join(item.text for item in materials)
    agent_result = run_review_agent(material_text, rule_result)

    return ReviewResponse(
        application_id=request.application_id,
        applicant_name=request.applicant_name,
        id_number=request.id_number,
        ai_status=rule_result["decision"],
        issues=rule_result["issues"],
        suggestions=rule_result["suggestions"],
        completeness=rule_result["completeness"],
        content_check=rule_result["content_check"],
        risk_summary=rule_result["risk_summary"],
        knowledge_hits=rule_result["knowledge_hits"],
        agent_result=agent_result,
        raw_length=rule_result["raw_length"],
        files=rule_result["files"],
    )

import io
import json
import uuid
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.auth import TenantContext, get_ctx
from app.core.audit import write_audit
from app.db.session import SessionLocal
from app.models.core import EvidenceItem
from app.models.questionnaires import (
    QuestionnaireTemplate,
    QuestionnaireQuestion,
    TenantAnswer,
    TenantAnswerEvidence,
)

router = APIRouter(prefix="/questionnaires", tags=["questionnaires"])


class UpsertAnswerRequest(BaseModel):
    answer_text: str


class AttachEvidenceRequest(BaseModel):
    evidence_id: uuid.UUID


@router.get("/templates")
def list_templates() -> list[dict]:
    with SessionLocal() as session:
        tpls = session.execute(
            select(QuestionnaireTemplate).order_by(QuestionnaireTemplate.created_at.desc())
        ).scalars().all()
        return [
            {
                "id": str(t.id),
                "code": t.code,
                "name": t.name,
                "language": t.language,
                "version": t.version,
            }
            for t in tpls
        ]


@router.get("/templates/{template_id}")
def get_template(template_id: str) -> dict:
    tid = uuid.UUID(template_id)
    with SessionLocal() as session:
        tpl = session.execute(
            select(QuestionnaireTemplate).where(QuestionnaireTemplate.id == tid)
        ).scalar_one_or_none()
        if tpl is None:
            raise HTTPException(status_code=404, detail="not found")

        qs = session.execute(
            select(QuestionnaireQuestion)
            .where(QuestionnaireQuestion.template_id == tpl.id)
            .order_by(QuestionnaireQuestion.key.asc())
        ).scalars().all()

        return {
            "id": str(tpl.id),
            "code": tpl.code,
            "name": tpl.name,
            "language": tpl.language,
            "version": tpl.version,
            "questions": [{"id": str(q.id), "key": q.key, "prompt": q.prompt} for q in qs],
        }


@router.put("/answers/{question_id}")
def upsert_answer(
    question_id: str,
    req: UpsertAnswerRequest,
    ctx: TenantContext = Depends(get_ctx),
) -> dict:
    qid = uuid.UUID(question_id)
    answer_text = req.answer_text.strip()
    if not answer_text:
        raise HTTPException(status_code=400, detail="answer_text required")

    with SessionLocal() as session:
        q = session.execute(
            select(QuestionnaireQuestion).where(QuestionnaireQuestion.id == qid)
        ).scalar_one_or_none()
        if q is None:
            raise HTTPException(status_code=404, detail="question not found")

        ans = session.execute(
            select(TenantAnswer).where(
                TenantAnswer.tenant_id == ctx.tenant_id,
                TenantAnswer.question_id == qid,
            )
        ).scalar_one_or_none()

        now = datetime.utcnow()
        if ans is None:
            ans = TenantAnswer(
                tenant_id=ctx.tenant_id,
                question_id=qid,
                answer_text=answer_text,
                updated_at=now,
            )
            session.add(ans)
            session.flush()
            action = "answer.create"
        else:
            ans.answer_text = answer_text
            ans.updated_at = now
            action = "answer.update"

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action=action,
            object_type="answer",
            object_id=str(ans.id),
            meta={"question_id": str(qid)},
        )

        session.commit()
        return {"answer_id": str(ans.id)}


@router.post("/answers/{answer_id}/evidence")
def attach_evidence(
    answer_id: str,
    req: AttachEvidenceRequest,
    ctx: TenantContext = Depends(get_ctx),
) -> dict:
    aid = uuid.UUID(answer_id)

    with SessionLocal() as session:
        ans = session.execute(
            select(TenantAnswer).where(
                TenantAnswer.id == aid,
                TenantAnswer.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if ans is None:
            raise HTTPException(status_code=404, detail="answer not found")

        ev = session.execute(
            select(EvidenceItem).where(
                EvidenceItem.id == req.evidence_id,
                EvidenceItem.tenant_id == ctx.tenant_id,
            )
        ).scalar_one_or_none()
        if ev is None:
            raise HTTPException(status_code=404, detail="evidence not found")

        link = session.execute(
            select(TenantAnswerEvidence).where(
                TenantAnswerEvidence.answer_id == aid,
                TenantAnswerEvidence.evidence_id == req.evidence_id,
            )
        ).scalar_one_or_none()

        if link is None:
            link = TenantAnswerEvidence(
                tenant_id=ctx.tenant_id,
                answer_id=aid,
                evidence_id=req.evidence_id,
                created_at=datetime.utcnow(),
            )
            session.add(link)

            write_audit(
                db=session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                action="answer.attach_evidence",
                object_type="answer",
                object_id=str(aid),
                meta={"evidence_id": str(req.evidence_id)},
            )

            session.commit()

        return {"status": "ok"}


@router.get("/export/{template_code}")
def export_pack(template_code: str, ctx: TenantContext = Depends(get_ctx)):
    with SessionLocal() as session:
        tpl = session.execute(
            select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == template_code)
        ).scalar_one_or_none()
        if tpl is None:
            raise HTTPException(status_code=404, detail="template not found")

        questions = session.execute(
            select(QuestionnaireQuestion).where(QuestionnaireQuestion.template_id == tpl.id)
        ).scalars().all()
        qmap = {q.id: q for q in questions}
        qids = list(qmap.keys())

        answers = []
        if qids:
            answers = session.execute(
                select(TenantAnswer).where(
                    TenantAnswer.tenant_id == ctx.tenant_id,
                    TenantAnswer.question_id.in_(qids),
                )
            ).scalars().all()

        ans_ids = [a.id for a in answers]
        links = []
        if ans_ids:
            links = session.execute(
                select(TenantAnswerEvidence).where(
                    TenantAnswerEvidence.tenant_id == ctx.tenant_id,
                    TenantAnswerEvidence.answer_id.in_(ans_ids),
                )
            ).scalars().all()

        ev_ids = sorted({l.evidence_id for l in links})

        answer_to_evidence: dict[uuid.UUID, list[uuid.UUID]] = {}
        for l in links:
            answer_to_evidence.setdefault(l.answer_id, []).append(l.evidence_id)
        evidences = []
        if ev_ids:
            evidences = session.execute(
                select(EvidenceItem).where(
                    EvidenceItem.tenant_id == ctx.tenant_id,
                    EvidenceItem.id.in_(ev_ids),
                )
            ).scalars().all()

        pack = {
            "template": {
                "code": tpl.code,
                "name": tpl.name,
                "version": tpl.version,
                "language": tpl.language,
            },
            "tenant_id": str(ctx.tenant_id),
            "generated_at": datetime.utcnow().isoformat(),
            "answers": [
                {
                    "question_key": qmap[a.question_id].key,
                    "question_prompt": qmap[a.question_id].prompt,
                    "answer_text": a.answer_text,
                    "updated_at": a.updated_at.isoformat(),
                    "evidence_ids": [str(eid) for eid in sorted(answer_to_evidence.get(a.id, []))],
                }
                for a in sorted(answers, key=lambda x: qmap[x.question_id].key)
            ],
            "evidence": [
                {
                    "id": str(e.id),
                    "title": e.title,
                    "description": e.description,
                    "original_filename": e.original_filename,
                    "uploaded_at": e.uploaded_at.isoformat() if e.uploaded_at else None,
                    "storage_key": e.storage_key,
                    "content_hash": e.content_hash,
                }
                for e in sorted(evidences, key=lambda x: x.created_at, reverse=True)
            ],
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("pack.json", json.dumps(pack, indent=2))
        buf.seek(0)

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="pack.export",
            object_type="template",
            object_id=tpl.code,
            meta={},
        )
        session.commit()

    filename = f"{template_code}_pack.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

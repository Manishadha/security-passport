import io
import json
import uuid
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.auth import TenantContext, get_ctx
from app.core.audit import write_audit
from app.db.session import SessionLocal
from app.models.core import EvidenceItem

router = APIRouter(prefix="/questionnaires", tags=["questionnaires"])


def _q_tables(session):
    import sqlalchemy as sa

    md = sa.MetaData()
    bind = session.get_bind()
    insp = sa.inspect(bind)

    tpls = sa.Table("questionnaire_templates", md, autoload_with=bind)
    qs = sa.Table("questionnaire_questions", md, autoload_with=bind)
    ans = sa.Table("tenant_answers", md, autoload_with=bind)
    ae = sa.Table("tenant_answer_evidence", md, autoload_with=bind) if "tenant_answer_evidence" in insp.get_table_names() else None
    return md, bind, tpls, qs, ans, ae


class UpsertAnswerRequest(BaseModel):
    answer_text: str


class AttachEvidenceRequest(BaseModel):
    evidence_id: uuid.UUID


@router.get("/templates")
def list_templates() -> list[dict]:
    import sqlalchemy as sa

    with SessionLocal() as session:
        _, _, tpls, _, _, _ = _q_tables(session)
        rows = session.execute(
            sa.select(tpls).order_by(tpls.c.created_at.desc())
        ).mappings().all()

        return [
            {
                "id": str(r["id"]),
                "code": r["code"],
                "name": r["name"],
                "language": r.get("language"),
                "version": r.get("version"),
            }
            for r in rows
        ]


@router.get("/templates/{template_id}")
def get_template(template_id: str) -> dict:
    import sqlalchemy as sa

    tid = uuid.UUID(template_id)
    with SessionLocal() as session:
        _, _, tpls, qs, _, _ = _q_tables(session)

        tpl = session.execute(
            sa.select(tpls).where(tpls.c.id == tid)
        ).mappings().first()
        if tpl is None:
            raise HTTPException(status_code=404, detail="not found")

        qrows = session.execute(
            sa.select(qs)
            .where(qs.c.template_id == tpl["id"])
            .order_by(qs.c.key.asc())
        ).mappings().all()

        return {
            "id": str(tpl["id"]),
            "code": tpl["code"],
            "name": tpl["name"],
            "language": tpl.get("language"),
            "version": tpl.get("version"),
            "questions": [{"id": str(q["id"]), "key": q["key"], "prompt": q["prompt"]} for q in qrows],
        }


@router.put("/answers/{question_id}")
def upsert_answer(
    question_id: str,
    req: UpsertAnswerRequest,
    ctx: TenantContext = Depends(get_ctx),
) -> dict:
    import sqlalchemy as sa

    qid = uuid.UUID(question_id)
    answer_text = (req.answer_text or "").strip()
    if not answer_text:
        raise HTTPException(status_code=400, detail="answer_text required")

    with SessionLocal() as session:
        _, bind, _, qs, ans, _ = _q_tables(session)

        qrow = session.execute(
            sa.select(qs).where(qs.c.id == qid)
        ).mappings().first()
        if qrow is None:
            raise HTTPException(status_code=404, detail="question not found")

        now = datetime.utcnow()

        existing = session.execute(
            sa.select(ans).where(sa.and_(ans.c.tenant_id == ctx.tenant_id, ans.c.question_id == qid))
        ).mappings().first()

        if existing is None:
            ins = ans.insert().values(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                question_id=qid,
                answer_text=answer_text,
                updated_at=now,
            ).returning(ans.c.id)
            new_id = session.execute(ins).scalar_one()
            action = "answer.create"
            answer_id = new_id
        else:
            upd = ans.update().where(ans.c.id == existing["id"]).values(
                answer_text=answer_text,
                updated_at=now,
            )
            session.execute(upd)
            action = "answer.update"
            answer_id = existing["id"]

        session.commit()

        write_audit(session, ctx, action, {"question_id": str(qid), "answer_id": str(answer_id)})
        return {"ok": True, "answer_id": str(answer_id)}


@router.post("/answers/{answer_id}/evidence")
def attach_evidence(
    answer_id: str,
    req: AttachEvidenceRequest,
    ctx: TenantContext = Depends(get_ctx),
) -> dict:
    import sqlalchemy as sa

    aid = uuid.UUID(answer_id)

    with SessionLocal() as session:
        md, bind, _, _, ans, ae = _q_tables(session)

        arow = session.execute(
            sa.select(ans).where(sa.and_(ans.c.id == aid, ans.c.tenant_id == ctx.tenant_id))
        ).mappings().first()
        if arow is None:
            raise HTTPException(status_code=404, detail="answer not found")

        ev = session.execute(
            sa.select(EvidenceItem).where(EvidenceItem.id == req.evidence_id, EvidenceItem.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if ev is None:
            raise HTTPException(status_code=404, detail="evidence not found")

        if ae is None:
            raise HTTPException(status_code=400, detail="evidence linking not available")

        session.execute(
            ae.insert().values(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                answer_id=aid,
                evidence_id=req.evidence_id,
                created_at=datetime.utcnow(),
            )
        )
        session.commit()

        write_audit(session, ctx, "answer.attach_evidence", {"answer_id": str(aid), "evidence_id": str(req.evidence_id)})
        return {"ok": True}


@router.get("/export-pack/{template_code}.json")
def export_pack_json(template_code: str, ctx: TenantContext = Depends(get_ctx)):
    import sqlalchemy as sa

    with SessionLocal() as session:
        _, _, tpls, qs, ans, ae = _q_tables(session)

        tpl = session.execute(
            sa.select(tpls).where(tpls.c.code == template_code)
        ).mappings().first()
        if tpl is None:
            raise HTTPException(status_code=404, detail="unknown template")

        qrows = session.execute(
            sa.select(qs).where(qs.c.template_id == tpl["id"]).order_by(qs.c.key.asc())
        ).mappings().all()

        arows = session.execute(
            sa.select(ans).where(sa.and_(ans.c.tenant_id == ctx.tenant_id))
        ).mappings().all()

        by_qid = {r["question_id"]: r for r in arows if r.get("question_id") is not None}

        ev_ids_by_answer = {}
        if ae is not None:
            lrows = session.execute(
                sa.select(ae).where(ae.c.tenant_id == ctx.tenant_id)
            ).mappings().all()
            for lr in lrows:
                ev_ids_by_answer.setdefault(lr["answer_id"], []).append(lr["evidence_id"])

        all_ev_ids = set()
        answers_out = []

        for q in qrows:
            ar = by_qid.get(q["id"])
            if not ar:
                continue

            ev_ids = ev_ids_by_answer.get(ar["id"], [])
            ev_strs = [str(x) for x in ev_ids] if ev_ids else []
            all_ev_ids.update(ev_strs)

            updated_at = ar.get("updated_at") or ar.get("created_at")
            if updated_at is not None and hasattr(updated_at, "isoformat"):
                updated_at = updated_at.isoformat()

            answers_out.append(
                {
                    "question_key": q.get("key"),
                    "question_prompt": q.get("prompt"),
                    "answer_text": ar.get("answer_text"),
                    "updated_at": updated_at,
                    "evidence_ids": ev_strs if ev_strs else None,
                }
            )

        ev_out = []
        if all_ev_ids:
            ev_rows = session.execute(
                sa.select(EvidenceItem).where(sa.and_(EvidenceItem.tenant_id == ctx.tenant_id, EvidenceItem.id.in_(list(all_ev_ids))))
            ).all()
            for (ev,) in ev_rows:
                ev_out.append(
                    {
                        "id": str(ev.id),
                        "title": ev.title,
                        "description": ev.description,
                        "original_filename": ev.original_filename,
                        "uploaded_at": ev.uploaded_at.isoformat() if ev.uploaded_at else None,
                        "storage_key": ev.storage_key,
                        "content_hash": ev.content_hash,
                    }
                )

        pack = {
            "template": {
                "code": tpl["code"],
                "name": tpl["name"],
                "version": tpl.get("version"),
                "language": tpl.get("language"),
            },
            "tenant_id": str(ctx.tenant_id),
            "generated_at": datetime.utcnow().isoformat(),
            "answers": answers_out,
            "evidence": ev_out,
        }
        return pack

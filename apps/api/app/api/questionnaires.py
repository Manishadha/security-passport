import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import TenantContext, get_ctx
from app.db.session import SessionLocal

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
        rows = session.execute(sa.select(tpls).order_by(tpls.c.created_at.desc())).mappings().all()

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

        tpl = session.execute(sa.select(tpls).where(tpls.c.id == tid)).mappings().first()
        if tpl is None:
            raise HTTPException(status_code=404, detail="not found")

        qrows = session.execute(
            sa.select(qs).where(qs.c.template_id == tpl["id"]).order_by(qs.c.key.asc())
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
        _, _, _, qs, ans, _ = _q_tables(session)

        qrow = session.execute(sa.select(qs).where(qs.c.id == qid)).mappings().first()
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
            answer_id = session.execute(ins).scalar_one()
            action = "answer.create"
        else:
            upd = ans.update().where(ans.c.id == existing["id"]).values(answer_text=answer_text, updated_at=now)
            session.execute(upd)
            answer_id = existing["id"]
            action = "answer.update"

        session.commit()

        try:
            from app.core.audit import write_audit as _write_audit

            _write_audit(session=session, ctx=ctx, action=action, meta={"question_id": str(qid), "answer_id": str(answer_id)})
        except Exception:
            pass

        return {"ok": True, "answer_id": str(answer_id)}


@router.post("/answers/{answer_id}/evidence")
def attach_evidence(
    answer_id: str,
    req: AttachEvidenceRequest,
    ctx: TenantContext = Depends(get_ctx),
) -> dict:
    import sqlalchemy as sa

    aid = uuid.UUID(answer_id)
    eid = req.evidence_id
    now = datetime.utcnow()

    with SessionLocal() as session:
        md, bind, _, _, ans, ae = _q_tables(session)
        if ae is None:
            raise HTTPException(status_code=400, detail="evidence linking not enabled")

        arow = session.execute(
            sa.select(ans).where(sa.and_(ans.c.id == aid, ans.c.tenant_id == ctx.tenant_id))
        ).mappings().first()
        if not arow:
            raise HTTPException(status_code=404, detail="answer not found")

        e = sa.Table("evidence_items", md, autoload_with=bind)
        ev = session.execute(
            sa.select(e.c.id).where(sa.and_(e.c.id == eid, e.c.tenant_id == ctx.tenant_id))
        ).first()
        if not ev:
            raise HTTPException(status_code=404, detail="evidence not found")

        values = {}
        if "id" in ae.c:
            values["id"] = uuid.uuid4()
        if "tenant_id" in ae.c:
            values["tenant_id"] = ctx.tenant_id
        if "answer_id" in ae.c:
            values["answer_id"] = aid
        if "evidence_id" in ae.c:
            values["evidence_id"] = eid
        if "created_at" in ae.c:
            values["created_at"] = now
        if "updated_at" in ae.c:
            values["updated_at"] = now

        exists_q = sa.select(ae.c.id).where(
            sa.and_(
                ae.c.answer_id == aid,
                ae.c.evidence_id == eid,
                ae.c.tenant_id == ctx.tenant_id if "tenant_id" in ae.c else sa.true(),
            )
        ).limit(1)

        already = session.execute(exists_q).first() is not None

        if not already:
            session.execute(sa.insert(ae).values(**values))

        session.commit()

        already_linked = already

        try:
            from app.core.audit import write_audit as _write_audit

            _write_audit(
                session=session,
                ctx=ctx,
                action="answer.attach_evidence",
                meta={"answer_id": str(aid), "evidence_id": str(eid), "already_linked": already_linked},
            )
        except Exception:
            pass

        return {"ok": True, "answer_id": str(aid), "evidence_id": str(eid), "already_linked": already_linked}

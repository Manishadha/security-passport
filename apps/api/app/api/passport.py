import io
import json
import zipfile
from datetime import datetime
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.auth import TenantContext, get_ctx
from app.db.session import SessionLocal
from app.models.core import EvidenceItem
from app.api.evidence import get_download_url
router = APIRouter(prefix="/passport", tags=["passport"])


def _build_pack_via_db(session, ctx, template_code: str) -> dict:
    """
    Build the passport pack using DB reflection (no ORM model imports).
    This avoids breakage if model class names differ.
    """
    import sqlalchemy as sa

    md = sa.MetaData()
    bind = session.get_bind()
    insp = sa.inspect(bind)

    def pick_table(*candidates: str) -> str:
        existing = set(insp.get_table_names())
        for name in candidates:
            if name in existing:
                return name
        raise RuntimeError(f"None of the table candidates exist: {candidates}. Existing: {sorted(existing)}")

    # Try common naming variants
    t = sa.Table(
        pick_table("questionnaire_templates", "questionnaires_templates", "questionnaire_template"),
        md, autoload_with=bind,
    )
    q = sa.Table(
        pick_table("questionnaire_questions", "questionnaires_questions", "questionnaire_question"),
        md, autoload_with=bind,
    )
    a = sa.Table(
        pick_table(
            "tenant_answers",
            "questionnaire_answers",
            "questionnaire_answer",
            "questionnaire_question_answers",
            "questionnaire_responses",
        ),
        md, autoload_with=bind,
    )

    # Answer-evidence link table is optional depending on phase
    ae_name = None
    for cand in (
        "tenant_answer_evidence",
        "questionnaire_answer_evidence",
        "questionnaire_answer_evidences",
        "questionnaire_answers_evidence",
        "questionnaire_answers_evidences",
        "questionnaire_answer_evidence_links",
    ):
        if cand in insp.get_table_names():
            ae_name = cand
            break
    ae = sa.Table(ae_name, md, autoload_with=bind) if ae_name else None


    # Evidence table (we know this one from your schema)
    e = sa.Table("evidence_items", md, autoload_with=bind)

    # Fetch template
    tpl_row = session.execute(
        sa.select(t).where(sa.and_(t.c.code == template_code))
    ).mappings().first()
    if not tpl_row:
        raise ValueError(f"Unknown template: {template_code}")

    pack = {
        "template": {
            "code": tpl_row.get("code"),
            "name": tpl_row.get("name"),
            "version": tpl_row.get("version"),
            "language": tpl_row.get("language"),
        },
        "tenant_id": str(ctx.tenant_id),
        "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
        "answers": [],
        "evidence": [],
    }

    # Get question list for prompts/keys
    questions = session.execute(
        sa.select(q).where(q.c.template_id == tpl_row["id"]).order_by(q.c.key.asc())
    ).mappings().all()

    # Pull answers for this tenant/template
    # NOTE: depending on your schema, answers table may store question_id OR question_key.
    # We'll support both.
    answers_rows = session.execute(
        sa.select(a).where(
            sa.and_(
                a.c.tenant_id == ctx.tenant_id,
                sa.or_(
                    getattr(a.c, "template_id", None) == tpl_row["id"] if "template_id" in a.c else sa.true(),
                    sa.true(),
                ),
            )
        )
    ).mappings().all()

    # Index answers by question_id or key
    by_qid = {}
    by_key = {}
    for r in answers_rows:
        if "question_id" in r and r["question_id"] is not None:
            by_qid[r["question_id"]] = r
        if "question_key" in r and r["question_key"]:
            by_key[r["question_key"]] = r

    # Evidence links by answer_id (if link table exists)
    ev_ids_by_answer = {}
    if ae is not None:
        link_rows = session.execute(
            sa.select(ae).where(ae.c.tenant_id == ctx.tenant_id)
        ).mappings().all()
        for lr in link_rows:
            ev_ids_by_answer.setdefault(lr["answer_id"], []).append(lr["evidence_id"])

    # Collect evidence ids to include and build answer payloads
    all_ev_ids = set()

    for qu in questions:
        ans = None
        if "id" in qu and qu["id"] in by_qid:
            ans = by_qid[qu["id"]]
        elif qu.get("key") in by_key:
            ans = by_key[qu["key"]]

        if not ans:
            continue

        item = {
            "question_key": qu.get("key"),
            "question_prompt": qu.get("prompt"),
            "answer_text": ans.get("answer_text"),
            "updated_at": (ans.get("updated_at") or ans.get("created_at") or None),
        }

        # Attach evidence ids if possible
        ev_ids = ev_ids_by_answer.get(ans.get("id"), [])
        if ev_ids:
            ev_strs = [str(x) for x in ev_ids]
            item["evidence_ids"] = ev_strs
            all_ev_ids.update(ev_strs)

        # normalize timestamps to isoformat
        if item["updated_at"] is not None and hasattr(item["updated_at"], "isoformat"):
            item["updated_at"] = item["updated_at"].isoformat()

        pack["answers"].append(item)

    # Evidence metadata section
    if all_ev_ids:
        ev_rows = session.execute(
            sa.select(e).where(sa.and_(e.c.tenant_id == ctx.tenant_id, e.c.id.in_(list(all_ev_ids))))
        ).mappings().all()

        for er in ev_rows:
            ev_item = {
                "id": str(er["id"]),
                "title": er.get("title"),
                "description": er.get("description"),
                "original_filename": er.get("original_filename"),
                "uploaded_at": er.get("uploaded_at").isoformat() if er.get("uploaded_at") else None,
                "storage_key": er.get("storage_key"),
                "content_hash": er.get("content_hash"),
            }
            pack["evidence"].append(ev_item)

    return pack

def _render_docx_bytes(pack: Dict[str, Any]) -> bytes:
    """
    Use your existing DOCX renderer (Phase 6/7).
    """
    from app.api.questionnaires import render_docx_bytes
    return render_docx_bytes(pack)


@router.get("/{template_code}.zip")
def export_passport_zip(template_code: str, ctx: TenantContext = Depends(get_ctx)):
    with SessionLocal() as session:
        pack = _build_pack_via_db(session=session, ctx=ctx, template_code=template_code)
        docx_bytes = _render_docx_bytes(pack)

        evidence_items: List[Dict[str, Any]] = pack.get("evidence", []) or []

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("pack.json", json.dumps(pack, indent=2, ensure_ascii=False))
            z.writestr("security_passport.docx", docx_bytes)

            if evidence_items:
                z.writestr("evidence/README.txt", "Evidence files attached to answers.\n")

            with httpx.Client(timeout=30.0) as client:
                for ev in evidence_items:
                    if not ev.get("storage_key"):
                        continue

                    dl = get_download_url(ev["storage_key"])
                    url = dl["url"]

                    name = ev.get("original_filename") or f"{ev['id']}.bin"
                    safe_name = name.replace("/", "_").replace("\\", "_")
                    path_in_zip = f"evidence/{safe_name}"

                    r = client.get(url)
                    r.raise_for_status()
                    z.writestr(path_in_zip, r.content)

        buf.seek(0)
        filename = f"{template_code}_passport_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
        )

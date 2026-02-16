import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.evidence import get_download_url
from app.core.auth import TenantContext, get_ctx
from app.db.session import SessionLocal
from app.core.tenant_overrides import get_overrides


router = APIRouter(prefix="/passport", tags=["passport"])


def _safe_zip_name(name: str, fallback: str) -> str:
    base = PurePosixPath(name or "").name
    base = base.replace("..", ".")
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip()
    if not base:
        base = fallback
    return base[:120]


def _build_pack_via_db(session, ctx, template_code: str) -> dict:
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

    t = sa.Table(
        pick_table("questionnaire_templates", "questionnaires_templates", "questionnaire_template"),
        md,
        autoload_with=bind,
    )
    q = sa.Table(
        pick_table("questionnaire_questions", "questionnaires_questions", "questionnaire_question"),
        md,
        autoload_with=bind,
    )
    a = sa.Table(
        pick_table(
            "tenant_answers",
            "questionnaire_answers",
            "questionnaire_answer",
            "questionnaire_question_answers",
            "questionnaire_responses",
        ),
        md,
        autoload_with=bind,
    )

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

    e = sa.Table("evidence_items", md, autoload_with=bind)

    tpl_row = session.execute(sa.select(t).where(t.c.code == template_code)).mappings().first()
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
        "generated_at": datetime.utcnow().isoformat(),
        "answers": [],
        "evidence": [],
    }

    questions = session.execute(
        sa.select(q).where(q.c.template_id == tpl_row["id"]).order_by(q.c.key.asc())
    ).mappings().all()

    question_ids = [qu["id"] for qu in questions if qu.get("id") is not None]

    if question_ids and "question_id" in a.c:
        answers_rows = session.execute(
            sa.select(a).where(sa.and_(a.c.tenant_id == ctx.tenant_id, a.c.question_id.in_(question_ids)))
        ).mappings().all()
    else:
        answers_rows = session.execute(sa.select(a).where(a.c.tenant_id == ctx.tenant_id)).mappings().all()

    by_qid = {}
    by_key = {}
    for r in answers_rows:
        if "question_id" in r and r["question_id"] is not None:
            by_qid[r["question_id"]] = r
        if "question_key" in r and r["question_key"]:
            by_key[r["question_key"]] = r

    ev_ids_by_answer = {}
    if ae is not None:
        link_rows = session.execute(sa.select(ae).where(ae.c.tenant_id == ctx.tenant_id)).mappings().all()
        for lr in link_rows:
            ev_ids_by_answer.setdefault(lr["answer_id"], []).append(lr["evidence_id"])

    all_ev_ids = set()

    for qu in questions:
        ans = None
        if qu.get("id") is not None and qu["id"] in by_qid:
            ans = by_qid[qu["id"]]
        elif qu.get("key") in by_key:
            ans = by_key[qu["key"]]

        if not ans:
            continue

        updated_at = ans.get("updated_at") or ans.get("created_at") or None
        if updated_at is not None and hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()

        item = {
            "question_key": qu.get("key"),
            "question_prompt": qu.get("prompt"),
            "answer_text": ans.get("answer_text"),
            "updated_at": updated_at,
        }

        ev_ids = ev_ids_by_answer.get(ans.get("id"), [])
        if ev_ids:
            item["evidence_ids"] = [str(x) for x in ev_ids]
            all_ev_ids.update(ev_ids)

        pack["answers"].append(item)

    if all_ev_ids:
        ev_rows = session.execute(
            sa.select(e).where(sa.and_(e.c.tenant_id == ctx.tenant_id, e.c.id.in_(list(all_ev_ids))))
        ).mappings().all()

        for er in ev_rows:
            pack["evidence"].append(
                {
                    "id": str(er["id"]),
                    "title": er.get("title"),
                    "description": er.get("description"),
                    "original_filename": er.get("original_filename"),
                    "uploaded_at": er.get("uploaded_at").isoformat() if er.get("uploaded_at") else None,
                    "storage_key": er.get("storage_key"),
                    "content_hash": er.get("content_hash"),
                }
            )

    return pack
def _apply_passport_overrides(pack: Dict[str, Any], overrides: Dict[str, Any], include_key: str) -> Dict[str, Any]:
    include_evidence = overrides.get(include_key, True)
    if include_evidence:
        return pack

    pack = dict(pack)
    pack["evidence"] = []
    answers = []
    for a in (pack.get("answers") or []):
        a2 = dict(a)
        a2.pop("evidence_ids", None)
        answers.append(a2)
    pack["answers"] = answers
    return pack


def _render_docx_bytes(pack: Dict[str, Any]) -> bytes:
    from app.services.passport_docx import render_docx_bytes

    return render_docx_bytes(pack)


@router.get("/{template_code}.docx")
def export_passport_docx(template_code: str, ctx: TenantContext = Depends(get_ctx)):
    with SessionLocal() as session:
        overrides = get_overrides(session, ctx.tenant_id)
        pack = _build_pack_via_db(session=session, ctx=ctx, template_code=template_code)
        pack = _apply_passport_overrides(pack, overrides, "passport_docx_include_evidence")
        docx_bytes = _render_docx_bytes(pack)

    buf = io.BytesIO(docx_bytes)
    filename = f"{template_code}_passport_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



@router.get("/{template_code}.zip")
def export_passport_zip(template_code: str, ctx: TenantContext = Depends(get_ctx)):
    with SessionLocal() as session:
        overrides = get_overrides(session, ctx.tenant_id)
        pack = _build_pack_via_db(session=session, ctx=ctx, template_code=template_code)
        pack = _apply_passport_overrides(pack, overrides, "passport_zip_include_evidence")
        docx_bytes = _render_docx_bytes(pack)

        evidence_items: List[Dict[str, Any]] = pack.get("evidence", []) or []

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("pack.json", json.dumps(pack, indent=2, ensure_ascii=False))
            z.writestr("security_passport.docx", docx_bytes)

            failures: List[str] = []
            downloaded = 0

            if evidence_items:
                z.writestr("evidence/README.txt", "Evidence files attached to answers.\n")
                z.writestr("evidence/_meta.txt", f"count={len(evidence_items)}\n")

                with httpx.Client(timeout=30.0) as client:
                    for ev in evidence_items:
                        storage_key = ev.get("storage_key")
                        if not storage_key:
                            failures.append(f"{ev.get('id','')} missing_storage_key")
                            continue

                        name = _safe_zip_name(ev.get("original_filename") or "", f"{ev['id']}.bin")
                        path_in_zip = f"evidence/files/{name}"

                        try:
                            dl = get_download_url(storage_key)
                            url = dl["url"]

                            with client.stream("GET", url) as r:
                                r.raise_for_status()
                                with z.open(path_in_zip, "w") as w:
                                    for chunk in r.iter_bytes():
                                        w.write(chunk)

                            downloaded += 1
                        except Exception as ex:
                            failures.append(f"{ev.get('id','')} {name} {type(ex).__name__}")

                if failures:
                    z.writestr("evidence/_FAILED_DOWNLOADS.txt", "\n".join(failures) + "\n")

        buf.seek(0)
        filename = f"{template_code}_passport_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


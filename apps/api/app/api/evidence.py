import hashlib
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select

from app.core.auth import TenantContext, get_ctx
from app.core.audit import write_audit
from app.core.storage import s3_client
from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.core import EvidenceItem

router = APIRouter(prefix="/evidence", tags=["evidence"])

@router.post("")
def create_evidence(payload: dict, ctx: TenantContext = Depends(get_ctx)) -> dict:
    title = str(payload.get("title") or "").strip()
    description = payload.get("description")
    if not title:
        raise HTTPException(status_code=400, detail="title required")

    with SessionLocal() as session:
        item = EvidenceItem(
            tenant_id=ctx.tenant_id,
            title=title,
            description=str(description).strip() if description else None,
            created_at=datetime.utcnow(),
        )
        session.add(item)
        session.flush()

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="evidence.create",
            object_type="evidence",
            object_id=str(item.id),
            meta={"title": title},
        )
        session.commit()

        return {"id": str(item.id)}

@router.get("")
def list_evidence(ctx: TenantContext = Depends(get_ctx)) -> list[dict]:
    with SessionLocal() as session:
        rows = session.execute(
            select(EvidenceItem).where(EvidenceItem.tenant_id == ctx.tenant_id).order_by(EvidenceItem.created_at.desc())
        ).scalars().all()

        return [
            {
                "id": str(r.id),
                "title": r.title,
                "description": r.description,
                "created_at": r.created_at.isoformat(),
                "storage_key": r.storage_key,
                "original_filename": r.original_filename,
                "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,

            }
            for r in rows
        ]

@router.post("/{evidence_id}/upload")
async def upload_file(evidence_id: str, file: UploadFile = File(...), ctx: TenantContext = Depends(get_ctx)) -> dict:
    eid = uuid.UUID(evidence_id)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    sha256 = hashlib.sha256(data).hexdigest()
    storage_key = f"{ctx.tenant_id}/{eid}/{sha256}"

    s3 = s3_client()
    s3.put_object(
        Bucket=settings.s3_bucket,
        Key=storage_key,
        Body=data,
        ContentType=file.content_type or "application/octet-stream",
    )

    with SessionLocal() as session:
        item = session.execute(
            select(EvidenceItem).where(EvidenceItem.id == eid, EvidenceItem.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=404, detail="not found")

        item.storage_key = storage_key
        item.original_filename = file.filename
        item.content_type = file.content_type or "application/octet-stream"
        item.content_hash = sha256
        item.size_bytes = len(data)
        item.uploaded_at = datetime.utcnow()

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="evidence.upload",
            object_type="evidence",
            object_id=str(item.id),
            meta={"storage_key": storage_key, "sha256": sha256, "size_bytes": len(data)},
        )
        session.commit()

    return {"status": "ok", "storage_key": storage_key}

@router.get("/{evidence_id}/download")
def download_file(evidence_id: str, ctx: TenantContext = Depends(get_ctx)) -> dict:
    eid = uuid.UUID(evidence_id)

    with SessionLocal() as session:
        item = session.execute(
            select(EvidenceItem).where(EvidenceItem.id == eid, EvidenceItem.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if item is None or item.storage_key is None:
            raise HTTPException(status_code=404, detail="not found")

    s3 = s3_client()
    url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": item.storage_key,
            "ResponseContentDisposition": f'attachment; filename="{eid}.bin"',
            "ResponseContentType": item.content_type or "application/octet-stream",
        },
        ExpiresIn=300,
    )
    return {"url": url, "expires_in_seconds": 300}

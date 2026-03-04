import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.auth import TenantContext, get_ctx
from app.core.audit import write_audit
from app.core.settings import settings
from app.core.storage import s3_client
from app.db.session import SessionLocal
from app.models.core import EvidenceItem, ShareLink, ShareLinkItem, ShareLinkAccessLog



router = APIRouter(prefix="/share-links", tags=["share_links"])
public_router = APIRouter(prefix="/share", tags=["share_public"])


def _new_token() -> str:
    # 32 bytes => ~43 chars base64url
    raw = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)

def _as_aware_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        # treat naive as UTC (best-effort for legacy data)
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ShareLinkCreateBody(BaseModel):
    name: str
    expires_at: Optional[datetime] = None
    settings: Optional[Dict[str, Any]] = None
    policy_version: str = "v1"


class ShareLinkAddItemBody(BaseModel):
    evidence_id: uuid.UUID


@router.post("")
def create_share_link(body: ShareLinkCreateBody, ctx: TenantContext = Depends(get_ctx)) -> dict:
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")

    token = _new_token()
    token_hash = _hash_token(token)

    with SessionLocal() as session:
        row = ShareLink(
            tenant_id=ctx.tenant_id,
            name=name,
            token_hash=token_hash,
            settings=body.settings or {},
            policy_version=body.policy_version or "v1",
            expires_at=body.expires_at,
            created_by=ctx.user_id,
            created_at=_now(),
        )
        session.add(row)
        session.flush()

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="share_link.create",
            object_type="share_link",
            object_id=str(row.id),
            meta={"name": name},
        )
        session.commit()

        # return token ONCE
        return {
            "id": str(row.id),
            "name": row.name,
            "token": token,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }


@router.get("")
def list_share_links(ctx: TenantContext = Depends(get_ctx)) -> list[dict]:
    with SessionLocal() as session:
        rows = session.execute(
            select(ShareLink).where(ShareLink.tenant_id == ctx.tenant_id).order_by(ShareLink.created_at.desc())
        ).scalars().all()

        return [
            {
                "id": str(r.id),
                "name": r.name,
                "policy_version": r.policy_version,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


@router.post("/{share_link_id}/items")
def add_share_link_item(share_link_id: str, body: ShareLinkAddItemBody, ctx: TenantContext = Depends(get_ctx)) -> dict:
    sid = uuid.UUID(share_link_id)

    with SessionLocal() as session:
        link = session.execute(
            select(ShareLink).where(ShareLink.id == sid, ShareLink.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if link is None or link.revoked_at is not None:
            raise HTTPException(status_code=404, detail="share link not found")

        ev = session.execute(
            select(EvidenceItem).where(EvidenceItem.id == body.evidence_id, EvidenceItem.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if ev is None or ev.deleted_at is not None:
            raise HTTPException(status_code=404, detail="evidence not found")

        # must be uploaded to share
        if ev.storage_key is None:
            raise HTTPException(status_code=409, detail="evidence not uploaded")

        # upsert-ish via unique constraint
        item = ShareLinkItem(
            tenant_id=ctx.tenant_id,
            share_link_id=link.id,
            evidence_id=ev.id,
            created_at=_now(),
        )
        session.add(item)

        write_audit(
            db=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            action="share_link.item.add",
            object_type="share_link",
            object_id=str(link.id),
            meta={"evidence_id": str(ev.id)},
        )

        try:
            session.commit()
        except Exception:
            session.rollback()
            # already exists
        return {"ok": True}


@router.delete("/{share_link_id}")
def revoke_share_link(share_link_id: str, ctx: TenantContext = Depends(get_ctx)) -> dict:
    sid = uuid.UUID(share_link_id)
    with SessionLocal() as session:
        link = session.execute(
            select(ShareLink).where(ShareLink.id == sid, ShareLink.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if link is None:
            return {"ok": True}

        if link.revoked_at is None:
            link.revoked_at = _now()

            write_audit(
                db=session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                action="share_link.revoke",
                object_type="share_link",
                object_id=str(link.id),
                meta={},
            )
            session.commit()

        return {"ok": True}


def _log_access(session, tenant_id: uuid.UUID, share_link_id: uuid.UUID, action: str, request: Request, evidence_id: uuid.UUID | None):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    session.add(
        ShareLinkAccessLog(
            tenant_id=tenant_id,
            share_link_id=share_link_id,
            action=action,
            evidence_id=evidence_id,
            ip=ip,
            user_agent=(ua[:400] if ua else None),
            created_at=_now(),
        )
    )


def _resolve_link_by_token(session, token: str) -> ShareLink:
    token_hash = _hash_token(token)

    link = session.execute(
        select(ShareLink).where(ShareLink.token_hash == token_hash)
    ).scalar_one_or_none()

    # Don't leak existence details
    if link is None:
        raise HTTPException(status_code=404, detail="not found")

    revoked_at = _as_aware_utc(link.revoked_at)
    if revoked_at is not None:
        raise HTTPException(status_code=404, detail="not found")

    expires_at = _as_aware_utc(link.expires_at)
    if expires_at is not None and expires_at <= _now():
        raise HTTPException(status_code=404, detail="not found")

    return link


@public_router.get("/{token}")
def public_share_info(token: str, request: Request) -> dict:
    with SessionLocal() as session:
        link = _resolve_link_by_token(session, token)

        rows = session.execute(
            select(ShareLinkItem, EvidenceItem)
            .join(EvidenceItem, EvidenceItem.id == ShareLinkItem.evidence_id)
            .where(ShareLinkItem.share_link_id == link.id)
            .order_by(EvidenceItem.created_at.desc())
        ).all()

        items: List[dict] = []
        for sli, ev in rows:
            if ev.deleted_at is not None:
                continue
            items.append(
                {
                    "evidence_id": str(ev.id),
                    "title": ev.title,
                    "category": getattr(ev, "category", None),
                    "tags": list(getattr(ev, "tags", []) or []),
                    "original_filename": ev.original_filename,
                    "uploaded_at": ev.uploaded_at.isoformat() if ev.uploaded_at else None,
                    "size_bytes": ev.size_bytes,
                }
            )

        _log_access(session, link.tenant_id, link.id, "view", request, None)
        session.commit()

        return {
            "name": link.name,
            "policy_version": link.policy_version,
            "items": items,
        }


@public_router.get("/{token}/evidence/{evidence_id}/download")
def public_download(token: str, evidence_id: str, request: Request) -> dict:
    eid = uuid.UUID(evidence_id)
    with SessionLocal() as session:
        link = _resolve_link_by_token(session, token)

        # must be in share_link_items
        sli = session.execute(
            select(ShareLinkItem).where(ShareLinkItem.share_link_id == link.id, ShareLinkItem.evidence_id == eid)
        ).scalar_one_or_none()
        if sli is None:
            raise HTTPException(status_code=404, detail="not found")

        ev = session.execute(
            select(EvidenceItem).where(EvidenceItem.id == eid, EvidenceItem.tenant_id == link.tenant_id)
        ).scalar_one_or_none()
        if ev is None or ev.deleted_at is not None or ev.storage_key is None:
            raise HTTPException(status_code=404, detail="not found")

        s3 = s3_client()
        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": settings.s3_bucket,
                "Key": ev.storage_key,
                "ResponseContentDisposition": f'attachment; filename="{ev.original_filename or (str(eid) + ".bin")}"',
                "ResponseContentType": ev.content_type or "application/octet-stream",
            },
            ExpiresIn=300,
        )

        _log_access(session, link.tenant_id, link.id, "download", request, ev.id)
        session.commit()

        return {"url": url, "expires_in_seconds": 300}
Architecture Guardrails

1) Multi-tenant isolation
- All tenant-owned tables include tenant_id.
- All reads and writes require an explicit tenant context.
- Tests must exist for cross-tenant access prevention on every major resource.

2) Async boundary
- Any potentially heavy operation must be executed as a background job.
- API endpoints must create jobs and return job/export status.

3) Evidence storage
- Files are stored only in object storage.
- Evidence items reference storage_key and content_hash.
- Objects are treated as immutable; new upload creates a new storage_key.

4) Share links
- Share links are policy objects with a policy_version and settings_json.
- Share supports ALL_EVIDENCE and SELECTED_ITEMS using a join table.
- All share views and downloads are logged.

5) Entitlements
- Subscription and plan checks are centralized in one entitlements module.
- No endpoint contains hard-coded plan logic.

6) Audit logging
- Audit events are append-only with structured metadata.
- Audit inserts must be cheap and indexed by tenant_id and created_at.

7) No hidden coupling
- Infrastructure is accessed via interfaces (storage, queue, billing).
- Business logic lives in services, not in route handlers.

8) ORM reserved names
- Do not use 'metadata' as a SQLAlchemy attribute name. Use 'meta' and map to column 'metadata'.
printf "\n8) ORM reserved names\n- Do not use 'metadata' as a SQLAlchemy attribute name. Use 'meta' and map to column 'metadata'.\n" >> docs/ARCH_RULES.md

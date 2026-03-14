"""Sync API endpoints."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, HTTPException, Header, Request

from exocortex.models import SyncResult, SyncStatusResponse, SyncState

router = APIRouter()


def _get_state():
    from exocortex.main import app_state
    return app_state


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status():
    """Get current sync status."""
    state = _get_state()
    local_sha = await state.git.get_head_sha()
    remote_sha = await state.git.get_remote_sha()
    pending = await state.git.get_status()
    last_sha = await state.redis.get_last_sync_sha()

    return SyncStatusResponse(
        local_sha=local_sha,
        remote_sha=remote_sha,
        pending_changes=pending,
        sync_state=SyncState.idle,
        auto_sync_enabled=state.config.auto_push,
    )


@router.post("/sync/pull", response_model=SyncResult)
async def sync_pull():
    """Pull changes from remote."""
    state = _get_state()
    await state.git.fetch()
    success, changed = await state.git.pull_ff()

    if not success:
        success, conflicts = await state.git.pull_rebase()
        if not success:
            return SyncResult(status="conflict", conflicts=conflicts)

    # Reindex changed files
    from exocortex.core.index_pipeline import IndexEvent
    for f in changed:
        if f.endswith(".md"):
            await state.pipeline.process_event(IndexEvent(action="upsert", path=f))

    sha = await state.git.get_head_sha()
    await state.redis.set_last_sync_sha(sha)

    return SyncResult(status="ok", sha=sha, files_changed=changed)


@router.post("/sync/push", response_model=SyncResult)
async def sync_push():
    """Commit pending changes and push."""
    state = _get_state()
    pending = await state.git.get_status()

    if not pending:
        sha = await state.git.get_head_sha()
        return SyncResult(status="ok", sha=sha)

    md_files = [f for f in pending if f.endswith(".md")]
    if md_files:
        sha = await state.git.add_and_commit(pending, "[exocortex] Sync local changes")
    else:
        sha = await state.git.get_head_sha()

    success = await state.git.push()
    if not success:
        return SyncResult(status="error", sha=sha)

    await state.redis.set_last_sync_sha(sha)
    return SyncResult(status="ok", sha=sha, files_changed=pending)


@router.post("/sync/webhook")
async def webhook(request: Request, x_hub_signature_256: str | None = Header(None)):
    """GitHub webhook endpoint for push events."""
    state = _get_state()
    body = await request.body()

    # Verify signature if webhook_secret configured
    if state.config.webhook_secret:
        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="Missing signature")
        expected = "sha256=" + hmac.new(
            state.config.webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Trigger pull
    await state.git.fetch()
    success, changed = await state.git.pull_ff()

    # Reindex
    from exocortex.core.index_pipeline import IndexEvent
    for f in changed:
        if f.endswith(".md"):
            await state.pipeline.process_event(IndexEvent(action="upsert", path=f))

    sha = await state.git.get_head_sha()
    await state.redis.set_last_sync_sha(sha)

    return {"status": "ok", "files_changed": len(changed)}

"""Background sync daemon: watches for file changes and periodically syncs with remote."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from exocortex.config import load_config
from exocortex.core.index_pipeline import IndexEvent

logger = logging.getLogger(__name__)


class NoteChangeHandler(FileSystemEventHandler):
    """Watchdog handler that queues index events for changed markdown files."""

    def __init__(self, repo_path: Path, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self.repo_path = repo_path
        self.queue = queue
        self.loop = loop

    def _is_markdown(self, path: str) -> bool:
        return path.endswith(".md") and "/.git/" not in path

    def _rel_path(self, path: str) -> str:
        return str(Path(path).relative_to(self.repo_path))

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory and self._is_markdown(event.src_path):
            self.loop.call_soon_threadsafe(
                self.queue.put_nowait,
                IndexEvent(action="upsert", path=self._rel_path(event.src_path)),
            )

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory and self._is_markdown(event.src_path):
            self.loop.call_soon_threadsafe(
                self.queue.put_nowait,
                IndexEvent(action="upsert", path=self._rel_path(event.src_path)),
            )

    def on_deleted(self, event: FileSystemEvent):
        if not event.is_directory and self._is_markdown(event.src_path):
            self.loop.call_soon_threadsafe(
                self.queue.put_nowait,
                IndexEvent(action="delete", path=self._rel_path(event.src_path)),
            )

    def on_moved(self, event: FileSystemEvent):
        if not event.is_directory:
            if self._is_markdown(event.src_path):
                self.loop.call_soon_threadsafe(
                    self.queue.put_nowait,
                    IndexEvent(action="delete", path=self._rel_path(event.src_path)),
                )
            if self._is_markdown(event.dest_path):
                self.loop.call_soon_threadsafe(
                    self.queue.put_nowait,
                    IndexEvent(action="upsert", path=self._rel_path(event.dest_path)),
                )


async def process_queue(queue: asyncio.Queue):
    """Process index events from the queue, debouncing rapid changes."""
    import httpx

    client = httpx.AsyncClient(timeout=30.0)
    pending: dict[str, IndexEvent] = {}
    debounce_seconds = 2.0

    while True:
        try:
            # Drain all available events
            while True:
                try:
                    event = queue.get_nowait()
                    pending[event.path] = event
                except asyncio.QueueEmpty:
                    break

            if pending:
                # Wait for debounce
                await asyncio.sleep(debounce_seconds)

                # Drain again after debounce
                while True:
                    try:
                        event = queue.get_nowait()
                        pending[event.path] = event
                    except asyncio.QueueEmpty:
                        break

                # Process events via the API
                for path, event in pending.items():
                    try:
                        if event.action == "delete":
                            logger.info("[sync] File deleted: %s", path)
                        else:
                            logger.info("[sync] File changed: %s", path)

                        # Call the internal API to process the event
                        resp = await client.post(
                            "http://127.0.0.1:8000/api/internal/index-event",
                            json={"action": event.action, "path": path},
                        )
                        if resp.status_code != 200:
                            logger.warning("[sync] Index event failed for %s: %s", path, resp.text)
                    except Exception as e:
                        logger.error("[sync] Failed to process %s: %s", path, e)

                pending.clear()

            await asyncio.sleep(1)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[sync] Queue processor error: %s", e)
            await asyncio.sleep(5)


async def periodic_sync(config):
    """Periodically sync with remote repository."""
    import httpx

    client = httpx.AsyncClient(timeout=60.0)
    interval = config.sync_interval_minutes * 60

    while True:
        await asyncio.sleep(interval)
        try:
            logger.info("[sync] Periodic sync starting...")

            # Pull
            resp = await client.post("http://127.0.0.1:8000/api/sync/pull")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("files_changed"):
                    logger.info("[sync] Pulled %d changes", len(data["files_changed"]))

            # Push pending changes
            resp = await client.post("http://127.0.0.1:8000/api/sync/push")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("files_changed"):
                    logger.info("[sync] Pushed %d changes", len(data["files_changed"]))

        except Exception as e:
            logger.error("[sync] Periodic sync failed: %s", e)


async def main():
    """Main sync daemon entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config = load_config()
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[IndexEvent] = asyncio.Queue()

    # Start file watcher
    handler = NoteChangeHandler(config.repo_path, queue, loop)
    observer = Observer()
    observer.schedule(handler, str(config.repo_path), recursive=True)
    observer.start()
    logger.info("[sync] File watcher started on %s", config.repo_path)

    # Check if full reindex needed
    flag = config.data_path / ".needs_full_reindex"
    if flag.exists():
        import httpx
        logger.info("[sync] Full reindex flag detected, triggering reindex...")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post("http://127.0.0.1:8000/api/reindex?engine=all")
        except Exception as e:
            logger.warning("[sync] Could not trigger reindex: %s", e)

    # Run tasks
    try:
        await asyncio.gather(
            process_queue(queue),
            periodic_sync(config),
        )
    except asyncio.CancelledError:
        pass
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    asyncio.run(main())

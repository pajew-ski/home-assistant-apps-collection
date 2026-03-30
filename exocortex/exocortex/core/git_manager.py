"""Git operations: clone, pull, push, commit, history, diff."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GitManager:
    """Manages Git operations on the local working copy."""

    def __init__(self, repo_path: Path, branch: str = "main", auto_push: bool = True):
        self.repo_path = repo_path
        self.branch = branch
        self.auto_push = auto_push

    def _run(self, *args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
        """Run a git command synchronously."""
        cmd = ["git", "-C", str(self.repo_path)] + list(args)
        return subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=check,
            timeout=120,
        )

    async def _arun(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command asynchronously."""
        cmd = ["git", "-C", str(self.repo_path)] + list(args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        result = subprocess.CompletedProcess(
            cmd, proc.returncode or 0,
            stdout=stdout.decode() if stdout else "",
            stderr=stderr.decode() if stderr else "",
        )
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
        return result

    @property
    def is_repo(self) -> bool:
        return (self.repo_path / ".git").is_dir()

    async def get_head_sha(self) -> str:
        result = await self._arun("rev-parse", "HEAD", check=False)
        return result.stdout.strip() if result.returncode == 0 else ""

    async def get_remote_sha(self) -> str:
        await self._arun("fetch", "origin", self.branch, check=False)
        result = await self._arun("rev-parse", f"origin/{self.branch}", check=False)
        return result.stdout.strip() if result.returncode == 0 else ""

    async def get_status(self) -> list[str]:
        """Return list of modified/untracked files."""
        result = await self._arun("status", "--porcelain", check=False)
        if not result.stdout.strip():
            return []
        return [line[3:] for line in result.stdout.strip().split("\n") if line.strip()]

    async def fetch(self) -> bool:
        result = await self._arun("fetch", "origin", check=False)
        return result.returncode == 0

    async def pull_ff(self) -> tuple[bool, list[str]]:
        """Fast-forward merge from remote. Returns (success, changed_files)."""
        before_sha = await self.get_head_sha()
        result = await self._arun("merge", "--ff-only", f"origin/{self.branch}", check=False)

        if result.returncode != 0:
            logger.warning("Fast-forward merge failed: %s", result.stderr)
            return False, []

        after_sha = await self.get_head_sha()
        if before_sha == after_sha:
            return True, []

        # Get changed files
        diff_result = await self._arun("diff", "--name-only", before_sha, after_sha, check=False)
        changed = [f for f in diff_result.stdout.strip().split("\n") if f.strip()]
        return True, changed

    async def pull_rebase(self) -> tuple[bool, list[str]]:
        """Rebase onto remote. Returns (success, conflict_files)."""
        result = await self._arun("rebase", f"origin/{self.branch}", check=False)

        if result.returncode != 0:
            # Check for conflicts
            conflict_result = await self._arun(
                "diff", "--name-only", "--diff-filter=U", check=False
            )
            conflicts = [f for f in conflict_result.stdout.strip().split("\n") if f.strip()]

            # Abort rebase
            await self._arun("rebase", "--abort", check=False)
            return False, conflicts

        return True, []

    async def add_and_commit(
        self,
        files: list[str],
        message: str,
        author: str = "Exocortex <exocortex@homeassistant.local>",
    ) -> str:
        """Stage files and commit. Returns the new SHA."""
        for f in files:
            await self._arun("add", f)

        result = await self._arun(
            "commit",
            f"--author={author}",
            "-m", message,
            check=False,
        )

        if result.returncode != 0:
            if "nothing to commit" in result.stdout + result.stderr:
                return await self.get_head_sha()
            raise subprocess.CalledProcessError(result.returncode, "git commit", result.stdout, result.stderr)

        return await self.get_head_sha()

    async def push(self, max_retries: int = 3) -> bool:
        """Push to remote with retry logic."""
        for attempt in range(max_retries):
            result = await self._arun("push", "origin", self.branch, check=False)
            if result.returncode == 0:
                return True

            if "rejected" in (result.stderr or ""):
                # Try pull --rebase then push again
                logger.info("Push rejected, pulling with rebase...")
                await self._arun("pull", "--rebase", "origin", self.branch, check=False)
                continue

            # Network error — exponential backoff
            wait = 30 * (2 ** attempt)
            logger.warning("Push failed (attempt %d), retrying in %ds: %s", attempt + 1, wait, result.stderr)
            await asyncio.sleep(wait)

        return False

    async def get_file_history(self, path: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get git log for a specific file."""
        result = await self._arun(
            "log", f"-{limit}", "--format=%H|%s|%an|%aI", "--numstat", "--", path,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        commits: list[dict[str, Any]] = []
        lines = result.stdout.strip().split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if "|" in line and not line[0].isdigit():
                parts = line.split("|", 3)
                if len(parts) >= 4:
                    commit = {
                        "sha": parts[0],
                        "message": parts[1],
                        "author": parts[2],
                        "date": parts[3],
                        "additions": 0,
                        "deletions": 0,
                    }
                    # Next line might be numstat
                    if i + 1 < len(lines) and lines[i + 1].strip() and lines[i + 1][0].isdigit():
                        stat_parts = lines[i + 1].strip().split("\t")
                        if len(stat_parts) >= 2:
                            try:
                                commit["additions"] = int(stat_parts[0])
                                commit["deletions"] = int(stat_parts[1])
                            except ValueError:
                                pass
                        i += 1
                    commits.append(commit)
            i += 1

        return commits

    async def get_diff(self, path: str, sha: str) -> str:
        """Get diff of a file at a specific commit."""
        result = await self._arun("diff", f"{sha}~1..{sha}", "--", path, check=False)
        return result.stdout if result.returncode == 0 else ""

    async def get_file_at_revision(self, path: str, sha: str) -> str:
        """Get file content at a specific revision."""
        result = await self._arun("show", f"{sha}:{path}", check=False)
        return result.stdout if result.returncode == 0 else ""

    async def delete_file(self, path: str, message: str) -> str:
        """Delete a file and commit."""
        await self._arun("rm", path)
        return await self.add_and_commit([], message)

    async def get_changed_files_since(self, sha: str) -> list[str]:
        """Get list of files changed since a given SHA."""
        result = await self._arun("diff", "--name-only", sha, "HEAD", check=False)
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return [f for f in result.stdout.strip().split("\n") if f.strip()]

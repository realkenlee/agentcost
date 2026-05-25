"""Auto-detect git and CI context — cached per process."""
from __future__ import annotations
import functools
import os
import subprocess


@functools.lru_cache(maxsize=1)
def get_context() -> dict[str, str]:
    """Return best available context: CI env vars first, then local git."""
    # GitHub Actions
    if os.environ.get("GITHUB_ACTIONS"):
        ctx: dict[str, str] = {"ci": "github"}
        ctx["repo"]     = os.environ.get("GITHUB_REPOSITORY", "")
        ctx["user"]     = os.environ.get("GITHUB_ACTOR", "")
        ctx["workflow"] = os.environ.get("GITHUB_WORKFLOW", "")
        ctx["sha"]      = os.environ.get("GITHUB_SHA", "")[:8]
        ref = os.environ.get("GITHUB_REF", "")
        if "/pull/" in ref:
            ctx["pr"] = ref.split("/pull/")[1].split("/")[0]
        ctx["branch"] = (
            os.environ.get("GITHUB_HEAD_REF")
            or os.environ.get("GITHUB_REF_NAME", "")
        )
        return {k: v for k, v in ctx.items() if v}

    # GitLab CI
    if os.environ.get("GITLAB_CI"):
        ctx = {"ci": "gitlab"}
        ctx["repo"]   = os.environ.get("CI_PROJECT_PATH", "")
        ctx["user"]   = os.environ.get("GITLAB_USER_LOGIN", "")
        ctx["branch"] = os.environ.get("CI_COMMIT_BRANCH", "")
        ctx["pr"]     = os.environ.get("CI_MERGE_REQUEST_IID", "")
        ctx["sha"]    = os.environ.get("CI_COMMIT_SHORT_SHA", "")
        return {k: v for k, v in ctx.items() if v}

    # Local git
    ctx = {}
    try:
        ctx["branch"] = _git("rev-parse", "--abbrev-ref", "HEAD")
        ctx["sha"]    = _git("rev-parse", "--short", "HEAD")
        ctx["user"]   = _git("config", "user.email")
        remote        = _git("remote", "get-url", "origin")
        ctx["repo"]   = _parse_repo(remote)
    except Exception:
        pass
    return {k: v for k, v in ctx.items() if v}


def _git(*args: str) -> str:
    r = subprocess.run(
        ["git", *args], capture_output=True, text=True, timeout=3
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


def _parse_repo(remote: str) -> str:
    for prefix in ("https://github.com/", "git@github.com:", "https://gitlab.com/"):
        if prefix in remote:
            return remote.split(prefix, 1)[1].removesuffix(".git")
    return remote

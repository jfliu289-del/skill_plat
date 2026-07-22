"""Safely synchronize configured Git sources into a local cache."""

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlsplit

from .models import SourceSpec


_PRODUCTION_REPOSITORY_URL = re.compile(
    r"https://github[.]com/"
    r"(?P<owner>[A-Za-z0-9][A-Za-z0-9-]*)/"
    r"(?P<repo>[A-Za-z0-9][A-Za-z0-9_.-]*)"
)
_SAFE_CACHE_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]+")
_SUPPORTED_MODES = {"direct", "index", "archive", "reference"}
_TEST_SOURCE_ID = re.compile(r"test/(?P<repository>[A-Za-z0-9][A-Za-z0-9_.-]*)")


class SourceSecurityError(ValueError):
    """Raised when a source URL or checkout path violates the trust boundary."""


class SourceSyncError(RuntimeError):
    """Raised when Git cannot synchronize a validated source."""


@dataclass(frozen=True)
class ResolvedSource:
    """A source resolved to an immutable local Git commit."""

    source: SourceSpec
    checkout: Path
    commit: str


def sync_source(
    spec: SourceSpec, cache_root: Path, locked_commit: Optional[str] = None
) -> ResolvedSource:
    """Synchronize *spec* without running source-controlled hooks or submodules."""

    owner, repository = _validate_source(spec)
    _validate_locked_commit(locked_commit)
    include_paths = _archive_paths(spec) if spec.mode == "archive" else []

    cache_root.mkdir(parents=True, exist_ok=True)
    resolved_cache_root = cache_root.resolve()
    checkout = cache_root / _cache_name(owner, repository)
    resolved_checkout = checkout.resolve(strict=False)
    if resolved_checkout.parent != resolved_cache_root or checkout.is_symlink():
        raise SourceSecurityError("source cache path escapes the cache root")

    if checkout.exists():
        _update_checkout(spec, checkout, include_paths, locked_commit)
    else:
        _clone_checkout(spec, checkout, include_paths, locked_commit)

    commit = _run_git(["-C", str(checkout), "rev-parse", "HEAD"]).stdout.strip()
    if re.fullmatch(r"[0-9a-fA-F]{40,64}", commit) is None:
        raise SourceSyncError("Git returned an invalid commit identifier")
    requested_commit = locked_commit or (
        spec.ref if _is_exact_commit(spec.ref) else None
    )
    if requested_commit is not None and commit.lower() != requested_commit:
        raise SourceSyncError("Git synchronization did not resolve the requested commit")
    return ResolvedSource(source=spec, checkout=checkout, commit=commit.lower())


def _validate_source(spec: SourceSpec) -> Tuple[str, str]:
    if spec.mode not in _SUPPORTED_MODES:
        raise SourceSecurityError(f"unsupported source mode: {spec.mode}")
    _validate_git_ref(spec.ref)

    production_match = _PRODUCTION_REPOSITORY_URL.fullmatch(spec.url)
    if production_match is not None:
        owner = production_match.group("owner")
        repository = production_match.group("repo")
        if spec.id != f"{owner}/{repository}":
            raise SourceSecurityError("source id must exactly match its GitHub repository")
        return owner, repository

    parsed = urlsplit(spec.url)
    test_match = _TEST_SOURCE_ID.fullmatch(spec.id)
    if (
        test_match is not None
        and parsed.scheme == "file"
        and parsed.netloc in {"", "localhost"}
        and not parsed.query
        and not parsed.fragment
    ):
        local_path = Path(unquote(parsed.path))
        if not local_path.is_absolute():
            raise SourceSecurityError("test file URL must contain an absolute path")
        return "test", test_match.group("repository")

    raise SourceSecurityError("production sources must be exact HTTPS GitHub repository URLs")


def _validate_git_ref(ref: Optional[str]) -> None:
    if ref is None:
        return
    forbidden = set(" ~^:?*[\\")
    components = ref.split("/") if isinstance(ref, str) else []
    has_forbidden_character = isinstance(ref, str) and any(
        character in forbidden
        or ord(character) < 32
        or ord(character) == 127
        for character in ref
    )
    has_invalid_component = any(
        not component
        or component.startswith(".")
        or component.endswith(".lock")
        for component in components
    )
    if (
        not isinstance(ref, str)
        or not ref
        or ref.startswith("-")
        or ref.startswith("/")
        or ref.endswith(("/", "."))
        or ref == "@"
        or ".." in ref
        or "@{" in ref
        or "//" in ref
        or has_forbidden_character
        or has_invalid_component
    ):
        raise SourceSecurityError(f"unsafe Git ref: {ref!r}")


def _validate_locked_commit(commit: Optional[str]) -> None:
    if commit is not None and re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise SourceSecurityError(
            "locked commit must be a lowercase 40-character SHA"
        )


def _is_exact_commit(ref: Optional[str]) -> bool:
    return isinstance(ref, str) and re.fullmatch(r"[0-9a-f]{40}", ref) is not None


def _cache_name(owner: str, repository: str) -> str:
    safe_owner = _SAFE_CACHE_COMPONENT.sub("-", owner).strip(".")
    safe_repository = _SAFE_CACHE_COMPONENT.sub("-", repository).strip(".")
    if not safe_owner or not safe_repository:
        raise SourceSecurityError("source does not have a safe cache name")
    return f"{safe_owner}--{safe_repository}"


def _archive_paths(spec: SourceSpec) -> List[str]:
    if not spec.include_paths:
        raise SourceSecurityError("archive source requires selected Skill paths")
    return sorted({_validated_relative_path(path) for path in spec.include_paths})


def _validated_relative_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or "\x00" in value
        or "\n" in value
        or "\r" in value
    ):
        raise SourceSecurityError(f"unsafe source path: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value == "."
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise SourceSecurityError(f"unsafe source path: {value!r}")
    return value


def _clone_checkout(
    spec: SourceSpec,
    checkout: Path,
    include_paths: List[str],
    locked_commit: Optional[str],
) -> None:
    clone_arguments = ["clone"]
    if spec.mode == "archive":
        clone_arguments.extend(["--filter=blob:none", "--no-checkout"])
    clone_arguments.extend(["--depth", "1", "--no-recurse-submodules"])
    if spec.ref is not None and not _is_exact_commit(spec.ref):
        clone_arguments.extend(["--branch", spec.ref])
    clone_arguments.extend(["--", spec.url, str(checkout)])
    _run_git(clone_arguments)

    if spec.mode == "archive":
        _configure_sparse_checkout(checkout, include_paths)
    target = "HEAD"
    requested_commit = locked_commit or (
        spec.ref if _is_exact_commit(spec.ref) else None
    )
    if requested_commit is not None:
        _run_git(
            [
                "-C",
                str(checkout),
                "fetch",
                "--depth",
                "1",
                "--no-recurse-submodules",
                "--",
                "origin",
                requested_commit,
            ]
        )
        target = "FETCH_HEAD"
    _run_git(["-C", str(checkout), "checkout", "--detach", "--force", target])


def _update_checkout(
    spec: SourceSpec,
    checkout: Path,
    include_paths: List[str],
    locked_commit: Optional[str],
) -> None:
    git_metadata = _validated_git_metadata(checkout)

    configured_url = _run_git(
        ["-C", str(checkout), "config", "--get", "remote.origin.url"]
    ).stdout.strip()
    if configured_url != spec.url:
        raise SourceSecurityError("existing source cache has an unexpected origin URL")

    requested_ref = locked_commit or (spec.ref if spec.ref is not None else "HEAD")
    _run_git(
        [
            "-C",
            str(checkout),
            "fetch",
            "--depth",
            "1",
            "--no-recurse-submodules",
            "--",
            "origin",
            requested_ref,
        ]
    )
    if spec.mode == "archive":
        _configure_sparse_checkout(checkout, include_paths)
    elif (git_metadata / "info" / "sparse-checkout").is_file():
        _run_git(["-C", str(checkout), "sparse-checkout", "disable"])
    _run_git(
        ["-C", str(checkout), "checkout", "--detach", "--force", "FETCH_HEAD"]
    )
    _run_git(["-C", str(checkout), "clean", "-ffdx"])


def _validated_git_metadata(checkout: Path) -> Path:
    git_metadata = checkout / ".git"
    if git_metadata.is_symlink() or not git_metadata.is_dir():
        raise SourceSecurityError(
            "source cache requires an internal .git directory; linked worktrees are unsupported"
        )
    try:
        git_metadata.resolve().relative_to(checkout.resolve())
    except ValueError as error:
        raise SourceSecurityError("Git metadata escapes the source checkout") from error
    return git_metadata


def _configure_sparse_checkout(checkout: Path, include_paths: List[str]) -> None:
    _run_git(["-C", str(checkout), "sparse-checkout", "init", "--cone"])
    _run_git(
        [
            "-C",
            str(checkout),
            "sparse-checkout",
            "set",
            "--cone",
            "--",
            *include_paths,
        ]
    )


def _run_git(arguments: List[str]) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    for name in list(environment):
        if name.startswith("GIT_CONFIG_") or name in {
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_COMMON_DIR",
            "GIT_DIR",
            "GIT_INDEX_FILE",
            "GIT_NAMESPACE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_PREFIX",
            "GIT_PROXY_COMMAND",
            "GIT_SSH",
            "GIT_SSH_COMMAND",
            "GIT_WORK_TREE",
        }:
            environment.pop(name, None)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    command = ["git", "-c", f"core.hooksPath={os.devnull}", *arguments]
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            shell=False,
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", None) or str(error)
        raise SourceSyncError(f"Git source synchronization failed: {detail.strip()}") from error

"""Deterministic, containment-safe Skill and index discovery."""

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple
from urllib.parse import unquote, urlsplit

from .models import (
    RegistryClaim,
    RegistryDiscovery,
    RegistryIndexEntry,
)


_INDEX_FILE_SUFFIXES = {"", ".md", ".markdown", ".txt"}
_HTTPS_URL = re.compile(r"https://[^\s<>\[\]()\"'`]+")
_MARKDOWN_LINK = re.compile(
    r"(?<!!)\[(?P<label>[^\]\r\n]+)\]\((?P<url>https://[^\s<>()]+)\)"
)
_GITHUB_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
_GITHUB_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_CLAWHUB_COMPONENT = re.compile(r"[a-z0-9][a-z0-9_.-]*")
_CLAWHUB_INDEX_SOURCE_ID = "VoltAgent/awesome-openclaw-skills"


class DiscoverySecurityError(ValueError):
    """Raised when a discovery root or relative path escapes its repository."""


@dataclass
class DiscoveredTarget:
    """A GitHub repository and the paths an index linked within it."""

    url: str
    include_paths: List[str] = field(default_factory=list)
    provenance: List[str] = field(default_factory=list)


def discover_skill_roots(
    repo_root: Path,
    include_paths: List[str],
    exclude_paths: List[str],
) -> List[Path]:
    """Find directories containing an exact, regular ``SKILL.md`` file."""

    if not repo_root.is_dir() or repo_root.is_symlink():
        raise DiscoverySecurityError("repository root must be a real directory")
    resolved_root = repo_root.resolve()
    includes = sorted(
        {_validated_relative_path(path, allow_current=True) for path in include_paths}
    )
    excludes = {
        _validated_relative_path(path, allow_current=True) for path in exclude_paths
    }
    excludes.add(".git")

    roots: Set[Path] = set()
    for include in includes:
        start = repo_root if include == "." else repo_root / include
        _require_containment(start, resolved_root)
        if _is_excluded(include, excludes) or not start.is_dir() or start.is_symlink():
            continue
        for current, directory_names, file_names in os.walk(
            start, topdown=True, followlinks=False
        ):
            current_path = Path(current)
            current_relative = _relative_to_repository(current_path, repo_root)
            directory_names[:] = sorted(
                name
                for name in directory_names
                if name != ".git"
                and not (current_path / name).is_symlink()
                and not _is_excluded(
                    _join_relative(current_relative, name), excludes
                )
            )
            if "SKILL.md" not in file_names:
                continue
            candidate = current_path / "SKILL.md"
            if candidate.is_symlink() or not candidate.is_file():
                continue
            _require_containment(candidate, resolved_root)
            roots.add(repo_root / PurePosixPath(current_relative))

    return sorted(roots, key=lambda path: path.relative_to(repo_root).as_posix())


def discover_github_targets(index_root: Path) -> List[DiscoveredTarget]:
    """Extract and group repository and tree links from a checked-out index."""

    grouped_paths: Dict[str, Set[str]] = {}
    grouped_provenance: Dict[str, Set[str]] = {}
    for index_path, url in _index_urls(index_root):
        parsed = _parse_github_url(url)
        if parsed is None:
            continue
        repository_url, include_path = parsed
        paths = grouped_paths.setdefault(repository_url, set())
        if include_path == ".":
            paths.clear()
            paths.add(".")
        elif "." not in paths:
            paths.add(include_path)
        grouped_provenance.setdefault(repository_url, set()).add(index_path)

    return [
        DiscoveredTarget(
            url=url,
            include_paths=sorted(grouped_paths[url]),
            provenance=sorted(grouped_provenance[url]),
        )
        for url in sorted(grouped_paths)
    ]


def parse_github_tree_url(url: str) -> Optional[Tuple[str, str]]:
    """Return ``(repository_url, tree_path)`` for a safe GitHub tree URL."""

    parsed = _parse_github_url(url)
    if parsed is None or parsed[1] == ".":
        return None
    return parsed


def discover_openclaw_archive_paths(index_root: Path) -> List[str]:
    """Return legacy archive paths without modifying the checked-out index."""

    discovery = discover_clawhub_claims(index_root)
    return sorted(
        {
            f"skills/{claim.claimed_owner}/{claim.claimed_slug}"
            for claim in discovery.claims
            if claim.claimed_owner is not None
        }
    )


def discover_clawhub_claims(index_root: Path) -> RegistryDiscovery:
    """Read a frozen index into immutable, deterministic ClawHub claims."""

    grouped: Dict[
        Tuple[str, Optional[str], Optional[str]], Set[RegistryIndexEntry]
    ] = {}
    unresolved: Dict[str, Dict[str, object]] = {}
    for path, index_path in _index_files(index_root):
        text = path.read_text(encoding="utf-8", errors="replace")
        markdown_url_spans: List[Tuple[int, int]] = []
        for match in _MARKDOWN_LINK.finditer(text):
            label = match.group("label")
            url = match.group("url")
            markdown_url_spans.append(match.span("url"))
            if not _is_clawhub_candidate(url):
                continue
            parsed = _parse_clawhub_claim(label, url)
            if parsed is None:
                _add_unresolved(
                    unresolved,
                    {
                        "index_path": index_path,
                        "label": label,
                        "reason": "malformed-clawhub-link",
                        "source_id": _CLAWHUB_INDEX_SOURCE_ID,
                        "url": url,
                    },
                )
                continue
            claimed_slug, claimed_owner, legacy_id = parsed
            key = (claimed_slug, claimed_owner, legacy_id)
            grouped.setdefault(key, set()).add(
                RegistryIndexEntry(index_path, label, url)
            )

        for match in _HTTPS_URL.finditer(text):
            if any(
                start <= match.start() and match.end() <= end
                for start, end in markdown_url_spans
            ):
                continue
            url = match.group(0).rstrip(".,;:!?")
            if _is_clawhub_candidate(url):
                _add_unresolved(
                    unresolved,
                    {
                        "index_path": index_path,
                        "reason": "missing-markdown-label",
                        "source_id": _CLAWHUB_INDEX_SOURCE_ID,
                        "url": url,
                    },
                )

    claims = []
    for key in sorted(
        grouped,
        key=lambda item: (item[0], item[1] or "", item[2] or ""),
    ):
        claimed_slug, claimed_owner, legacy_id = key
        claims.append(
            RegistryClaim(
                claimed_slug=claimed_slug,
                claimed_owner=claimed_owner,
                legacy_id=legacy_id,
                index_entries=tuple(sorted(grouped[key])),
            )
        )
    return RegistryDiscovery(
        claims=tuple(claims),
        unresolved=tuple(unresolved[key] for key in sorted(unresolved)),
    )


def registry_claim_id(claim: RegistryClaim) -> str:
    """Hash exactly the immutable, audited fields of a registry claim."""

    payload = {
        "claimed_owner": claim.claimed_owner,
        "claimed_slug": claim.claimed_slug,
        "index_entries": [
            {
                "index_path": entry.index_path,
                "label": entry.label,
                "url": entry.url,
            }
            for entry in sorted(claim.index_entries)
        ],
        "legacy_id": claim.legacy_id,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _add_unresolved(
    unresolved: Dict[str, Dict[str, object]], item: Dict[str, object]
) -> None:
    canonical_item = dict(sorted(item.items()))
    key = json.dumps(
        canonical_item,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    unresolved[key] = canonical_item


def _is_clawhub_candidate(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.netloc in {
        "clawskills.sh",
        "clawhub.ai",
    }


def _parse_clawhub_claim(
    label: str, url: str
) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    if _CLAWHUB_COMPONENT.fullmatch(label) is None:
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"clawskills.sh", "clawhub.ai"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    decoded_path = unquote(parsed.path)
    if (
        not decoded_path.startswith("/")
        or "\\" in decoded_path
        or "\x00" in decoded_path
    ):
        return None
    relative_path = decoded_path[1:]
    if relative_path.endswith("/"):
        relative_path = relative_path[:-1]
    parts = relative_path.split("/") if relative_path else []
    if not parts or any(
        not part
        or part in {".", ".."}
        or _CLAWHUB_COMPONENT.fullmatch(part) is None
        for part in parts
    ):
        return None

    if parsed.netloc == "clawskills.sh":
        if len(parts) != 2 or parts[0] != "skills":
            return None
        return label, None, parts[1]

    if len(parts) == 2:
        owner, slug = parts
    elif len(parts) == 3 and parts[1] == "skills":
        owner, _, slug = parts
    else:
        return None
    if label != slug:
        return None
    return slug, owner, None


def _parse_github_url(url: str) -> Optional[Tuple[str, str]]:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
    ):
        return None
    decoded_path = unquote(parsed.path)
    if "\\" in decoded_path or "\x00" in decoded_path:
        return None
    normalized_path = decoded_path.removeprefix("/")
    if normalized_path.endswith("/"):
        normalized_path = normalized_path[:-1]
    parts = normalized_path.split("/")
    if len(parts) < 2 or _GITHUB_OWNER.fullmatch(parts[0]) is None:
        return None

    repository = parts[1]
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not repository or _GITHUB_REPOSITORY.fullmatch(repository) is None:
        return None
    repository_url = f"https://github.com/{parts[0]}/{repository}"

    if len(parts) == 2:
        return repository_url, "."
    if (
        len(parts) < 5
        or parts[2] != "tree"
        or parts[3] in {"", ".", ".."}
    ):
        return None
    tree_path = "/".join(parts[4:])
    try:
        tree_path = _validated_relative_path(tree_path, allow_current=False)
    except DiscoverySecurityError:
        return None
    return repository_url, tree_path


def _index_urls(index_root: Path) -> Iterator[Tuple[str, str]]:
    for path, relative_path in _index_files(index_root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _HTTPS_URL.finditer(text):
            url = match.group(0).rstrip(".,;:!?")
            yield relative_path, url


def _index_files(index_root: Path) -> Iterator[Tuple[Path, str]]:
    if not index_root.exists() or index_root.is_symlink():
        raise DiscoverySecurityError("index root must exist and must not be a symlink")
    if index_root.is_file():
        if index_root.suffix.lower() in _INDEX_FILE_SUFFIXES:
            yield index_root, index_root.name
        return
    if not index_root.is_dir():
        raise DiscoverySecurityError("index root must be a file or directory")

    resolved_root = index_root.resolve()
    for current, directory_names, file_names in os.walk(
        index_root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name != ".git" and not (current_path / name).is_symlink()
        )
        for name in sorted(file_names):
            path = current_path / name
            if (
                path.is_symlink()
                or path.suffix.lower() not in _INDEX_FILE_SUFFIXES
                or name == "unresolved.json"
                or not path.is_file()
            ):
                continue
            _require_containment(path, resolved_root)
            yield path, path.relative_to(index_root).as_posix()


def _validated_relative_path(value: str, allow_current: bool) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or "\x00" in value
        or "\n" in value
        or "\r" in value
    ):
        raise DiscoverySecurityError(f"unsafe discovery path: {value!r}")
    if allow_current and value == ".":
        return value
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise DiscoverySecurityError(f"unsafe discovery path: {value!r}")
    return value


def _require_containment(path: Path, resolved_root: Path) -> None:
    try:
        path.resolve().relative_to(resolved_root)
    except ValueError as error:
        raise DiscoverySecurityError(f"path escapes discovery root: {path}") from error


def _relative_to_repository(path: Path, repo_root: Path) -> str:
    relative = path.relative_to(repo_root).as_posix()
    return relative if relative else "."


def _join_relative(parent: str, child: str) -> str:
    return child if parent == "." else f"{parent}/{child}"


def _is_excluded(path: str, excludes: Iterable[str]) -> bool:
    if path == ".":
        return "." in excludes
    return any(
        exclude == "." or path == exclude or path.startswith(f"{exclude}/")
        for exclude in excludes
    )

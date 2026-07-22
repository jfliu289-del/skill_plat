"""Reproducible source graph synchronization and atomic catalog publication."""

from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from .classifier import classify
from .config import _source_path_list
from .discovery import (
    discover_github_targets,
    discover_openclaw_archive_paths,
    discover_skill_roots,
)
from .frontmatter import parse_skill
from .git_sources import ResolvedSource, sync_source
from .materialize import (
    SIDECAR_NAME,
    catalog_path,
    cluster_duplicates,
    materialize,
)
from .models import Classification, ImportResult, SkillRecord, SourceSpec, Taxonomy
from .safe_io import atomic_write_text
from .validate import detect_path_collisions, validate_catalog


Synchronizer = Callable[..., ResolvedSource]

_GENERATED_REPORTS = {
    "catalog.jsonl",
    "duplicates.json",
    "generated-files.json",
    "sources.lock.json",
    "summary.json",
    "unresolved.json",
    "validation.json",
}


@dataclass
class SyncedSource:
    resolved: ResolvedSource
    index_provenance: List[str] = field(default_factory=list)
    configured: bool = True


@dataclass
class SyncOutcome:
    sources: List[SyncedSource] = field(default_factory=list)
    lock_entries: List[Dict[str, object]] = field(default_factory=list)
    unresolved: List[Dict[str, object]] = field(default_factory=list)
    configured_direct_failures: int = 0

    def lock_payload(self) -> Dict[str, object]:
        return {
            "schema_version": "1.0",
            "sources": sorted(
                self.lock_entries,
                key=lambda item: (str(item.get("id", "")), str(item.get("url", ""))),
            ),
        }


@dataclass
class BuildOutcome:
    published: bool
    summary: Dict[str, int]
    validation: Dict[str, object]
    unresolved: List[Dict[str, object]] = field(default_factory=list)
    error: Optional[str] = None
    blocking_import_failures: int = 0
    nonblocking_import_failures: int = 0

    @property
    def import_failures(self) -> int:
        return self.blocking_import_failures + self.nonblocking_import_failures


class PublicationRecoveryError(RuntimeError):
    """Publication failed and old generated data requires manual recovery."""

    def __init__(self, recovery_path: Path, cause: BaseException):
        self.recovery_path = recovery_path
        super().__init__(
            "catalog publication rollback failed; old generated data is retained at "
            f"{recovery_path}: {cause}"
        )


@dataclass
class _Candidate:
    synced: SyncedSource
    record: SkillRecord
    classification: Classification


def sync_source_graph(
    configured_sources: Sequence[SourceSpec],
    cache_root: Path,
    locked_path: Optional[Path] = None,
    synchronizer: Synchronizer = sync_source,
) -> SyncOutcome:
    """Resolve configured and index-derived sources without running upstream code."""

    locked = _read_locked_sources(locked_path) if locked_path is not None else None
    outcome = SyncOutcome()
    configured = [replace(item) for item in configured_sources]
    consumed_locked: set = set()
    if locked is not None:
        for item in configured:
            key = (item.id, item.url)
            _restore_locked_source_fields(
                item, locked.get(key), expected_configured=True
            )
            consumed_locked.add(key)
    provenance_by_url: Dict[str, set] = {item.url: set() for item in configured}
    resolved_by_url: Dict[str, SyncedSource] = {}
    failed_urls = set()

    indexes = [item for item in configured if item.mode == "index"]
    references = [item for item in configured if item.mode == "reference"]
    import_sources = [item for item in configured if item.mode in {"direct", "archive"}]

    resolved_indexes: Dict[str, ResolvedSource] = {}
    for spec in indexes:
        resolved = _try_sync(
            spec,
            cache_root,
            locked,
            synchronizer,
            outcome,
            configured=True,
            provenance=[],
        )
        if resolved is not None:
            resolved_indexes[spec.id] = resolved

    for spec in references:
        _try_sync(
            spec,
            cache_root,
            locked,
            synchronizer,
            outcome,
            configured=True,
            provenance=[],
        )

    target_paths: Dict[str, set] = {}
    for index_id, resolved in sorted(resolved_indexes.items()):
        try:
            targets = discover_github_targets(resolved.checkout)
        except (OSError, ValueError) as error:
            outcome.unresolved.append(
                _unresolved(index_id, "index-discovery-failure", detail=type(error).__name__)
            )
            continue
        for target in targets:
            paths = target_paths.setdefault(target.url, set())
            if "." in target.include_paths:
                paths.clear()
                paths.add(".")
            elif "." not in paths:
                paths.update(target.include_paths)
            provenance_by_url.setdefault(target.url, set()).update(
                f"{index_id}:{path}" for path in target.provenance
            )

    for archive in [item for item in import_sources if item.mode == "archive"]:
        if not archive.index_source_id:
            continue
        index = resolved_indexes.get(archive.index_source_id)
        if index is None:
            outcome.unresolved.append(
                _unresolved(
                    archive.id,
                    "archive-index-unavailable",
                    index_source_id=archive.index_source_id,
                )
            )
            continue
        try:
            paths = discover_openclaw_archive_paths(index.checkout)
            archive.include_paths = sorted(set(archive.include_paths) | set(paths))
            provenance_by_url.setdefault(archive.url, set()).add(
                f"{archive.index_source_id}:openclaw-registry-links"
            )
            unresolved_file = index.checkout / "unresolved.json"
            if unresolved_file.is_file():
                payload = json.loads(unresolved_file.read_text(encoding="utf-8"))
                for item in payload.get("unresolved", []):
                    if isinstance(item, dict):
                        outcome.unresolved.append(
                            {
                                **item,
                                "source_id": archive.index_source_id,
                            }
                        )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            outcome.unresolved.append(
                _unresolved(archive.id, "archive-index-discovery-failure", detail=type(error).__name__)
            )

    configured_by_url = {item.url: item for item in configured}
    derived: List[SourceSpec] = []
    for url, paths in sorted(target_paths.items()):
        if url in configured_by_url:
            configured_spec = configured_by_url[url]
            if configured_spec.mode == "archive" and "." not in paths:
                configured_spec.include_paths = sorted(
                    set(configured_spec.include_paths) | set(paths)
                )
            continue
        source_id = _github_source_id(url)
        include_paths = sorted(paths) or ["."]
        mode = "direct" if "." in include_paths else "archive"
        derived.append(
            SourceSpec(
                id=source_id,
                url=url,
                mode=mode,
                include_paths=["."] if mode == "direct" else include_paths,
                exclude_paths=[".git"],
                redistribution_review=True,
                registry_archive_mirror=(url == "https://github.com/openclaw/skills"),
            )
        )
        if locked is not None:
            _restore_locked_source_fields(
                derived[-1],
                locked.get((derived[-1].id, derived[-1].url)),
                expected_configured=False,
            )
            consumed_locked.add((derived[-1].id, derived[-1].url))

    if locked is not None:
        unconsumed = sorted(set(locked) - consumed_locked)
        if unconsumed:
            formatted = ", ".join(f"{source_id} ({url})" for source_id, url in unconsumed)
            raise ValueError(
                f"source lock/config mismatch: unconsumed source entries: {formatted}"
            )

    for spec, is_configured in [
        *((item, True) for item in import_sources),
        *((item, False) for item in derived),
    ]:
        provenance = sorted(provenance_by_url.get(spec.url, set()))
        if spec.mode == "archive" and not spec.include_paths:
            failure = _unresolved(
                spec.id, "archive-has-no-resolved-skill-paths"
            )
            outcome.unresolved.append(failure)
            outcome.lock_entries.append(
                _lock_entry(
                    spec,
                    None,
                    "unresolved",
                    provenance,
                    is_configured,
                    failure=failure,
                )
            )
            continue
        if spec.url in resolved_by_url or spec.url in failed_urls:
            continue
        resolved = _try_sync(
            spec,
            cache_root,
            locked,
            synchronizer,
            outcome,
            configured=is_configured,
            provenance=provenance,
        )
        if resolved is None:
            failed_urls.add(spec.url)
            continue
        synced = SyncedSource(
            resolved=resolved,
            index_provenance=provenance,
            configured=is_configured,
        )
        resolved_by_url[spec.url] = synced
        outcome.sources.append(synced)

    outcome.sources.sort(
        key=lambda item: (item.resolved.source.url, item.resolved.source.id)
    )
    for entry in outcome.lock_entries:
        entry["index_provenance"] = sorted(
            provenance_by_url.get(str(entry["url"]), set())
        )
    outcome.unresolved = _stable_unresolved(outcome.unresolved)
    return outcome


def write_sync_reports(root: Path, outcome: SyncOutcome) -> None:
    """Atomically write the source lock and unresolved report for ``sync``."""

    _validate_managed_containers(Path(root), names=("reports",))
    reports = Path(root) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    _write_json(reports / "sources.lock.json", outcome.lock_payload())
    _write_json(reports / "unresolved.json", {"unresolved": outcome.unresolved})


def build_catalog(root: Path, taxonomy: Taxonomy, sync: SyncOutcome) -> BuildOutcome:
    """Build in a sibling staging tree and publish only after validation."""

    root = Path(root)
    _validate_managed_containers(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    unresolved = list(sync.unresolved)
    candidates: List[_Candidate] = []
    parse_failures = 0
    blocking_import_failures = 0
    nonblocking_import_failures = 0

    for synced in sync.sources:
        spec = synced.resolved.source
        if spec.mode not in {"direct", "archive"}:
            continue
        try:
            skill_roots = discover_skill_roots(
                synced.resolved.checkout,
                spec.include_paths,
                spec.exclude_paths,
            )
        except (OSError, ValueError) as error:
            unresolved.append(
                _unresolved(spec.id, "skill-discovery-failure", detail=type(error).__name__)
            )
            parse_failures += 1
            if _is_blocking_import_source(synced):
                blocking_import_failures += 1
            else:
                nonblocking_import_failures += 1
            continue
        for skill_root in skill_roots:
            source_path = skill_root.relative_to(synced.resolved.checkout).as_posix() or "."
            try:
                parsed = parse_skill(skill_root / "SKILL.md", synced.resolved.checkout)
                classification = classify(parsed, taxonomy, spec)
                record = SkillRecord(
                    source=spec,
                    repository=spec.url,
                    commit=synced.resolved.commit,
                    source_path=source_path,
                    skill_root=skill_root,
                    name=parsed.name,
                    description=parsed.description,
                    license=None,
                    license_evidence=[],
                    skill_md_hash=parsed.skill_md_hash,
                    redistribution_review=True,
                    registry_archive_mirror=spec.registry_archive_mirror,
                )
                # Resolve routing before any output path is written.
                catalog_path(record, classification, taxonomy)
                candidates.append(_Candidate(synced, record, classification))
            except (OSError, ValueError) as error:
                unresolved.append(
                    _unresolved(
                        spec.id,
                        "parse-failure",
                        source_path=source_path,
                        detail=type(error).__name__,
                    )
                )
                parse_failures += 1
                if _is_blocking_import_source(synced):
                    blocking_import_failures += 1
                else:
                    nonblocking_import_failures += 1

    candidates.sort(key=lambda item: (item.record.repository, item.record.source_path))
    projected_paths = _projected_output_paths(candidates, taxonomy)
    collisions = detect_path_collisions(projected_paths)
    if collisions:
        for collision in collisions:
            unresolved.append(
                {
                    "paths": collision.paths,
                    "reason": "path-collision",
                    "source_id": "catalog",
                }
            )
        return BuildOutcome(
            published=False,
            summary=_summary([], unresolved, parse_failures),
            validation={
                "central_record_count": 0,
                "failure_count": len(collisions),
                "failures": [
                    {
                        "code": "path-collision",
                        "message": "portable path collision",
                        "path": item.paths[0],
                    }
                    for item in collisions
                ],
                "skill_count": 0,
                "valid": False,
            },
            unresolved=_stable_unresolved(unresolved),
            error="portable path collision detected before materialization",
            blocking_import_failures=blocking_import_failures + len(collisions),
            nonblocking_import_failures=nonblocking_import_failures,
        )

    user_conflicts = _managed_root_user_content(root)
    if user_conflicts:
        return BuildOutcome(
            published=False,
            summary=_summary([], unresolved, parse_failures),
            validation={
                "central_record_count": 0,
                "failure_count": len(user_conflicts),
                "failures": [
                    {
                        "code": "managed-root-user-content",
                        "message": "untracked user content exists inside a generated Skill root",
                        "path": path,
                    }
                    for path in user_conflicts
                ],
                "skill_count": 0,
                "valid": False,
            },
            unresolved=_stable_unresolved(unresolved),
            error="user content inside a managed Skill root was preserved; build not published",
            blocking_import_failures=blocking_import_failures + len(user_conflicts),
            nonblocking_import_failures=nonblocking_import_failures,
        )

    staging_parent = Path(
        tempfile.mkdtemp(prefix=f".{root.name}-staging-", dir=str(root.parent))
    )
    staging = staging_parent / "catalog"
    results: List[ImportResult] = []
    preserve_staging = False
    try:
        _prepare_staging(root, staging)
        existing_paths = _relative_tree_paths(staging)
        combined_collisions = detect_path_collisions(existing_paths + projected_paths)
        if combined_collisions:
            return BuildOutcome(
                published=False,
                summary=_summary([], unresolved, parse_failures),
                validation={
                    "central_record_count": 0,
                    "failure_count": len(combined_collisions),
                    "failures": [
                        {
                            "code": "path-collision",
                            "message": "portable path collision with preserved user content",
                            "path": item.paths[0],
                        }
                        for item in combined_collisions
                    ],
                    "skill_count": 0,
                    "valid": False,
                },
                unresolved=_stable_unresolved(unresolved),
                error="path collision with preserved user content",
                blocking_import_failures=(
                    blocking_import_failures + len(combined_collisions)
                ),
                nonblocking_import_failures=nonblocking_import_failures,
            )

        for candidate in candidates:
            try:
                results.append(
                    materialize(
                        candidate.record,
                        staging,
                        candidate.classification,
                        taxonomy,
                    )
                )
            except (OSError, ValueError) as error:
                unresolved.append(
                    _unresolved(
                        candidate.record.source.id,
                        "materialization-failure",
                        source_path=candidate.record.source_path,
                        detail=type(error).__name__,
                    )
                )

                if _is_blocking_import_source(candidate.synced):
                    blocking_import_failures += 1
                else:
                    nonblocking_import_failures += 1

        stable_unresolved = _stable_unresolved(unresolved)
        summary = _summary(results, stable_unresolved, parse_failures, staging)
        _write_build_reports(staging, sync, results, stable_unresolved, summary)
        validation_report = validate_catalog(staging, taxonomy)
        validation_payload = validation_report.as_dict()
        _write_json(staging / "reports" / "validation.json", validation_payload)
        generated = {
            "generated_license_paths": [],
            "generated_paths": _generated_result_paths(staging, results),
            "generated_skill_roots": sorted(
                result.relative_path.as_posix() for result in results
            ),
        }
        _write_json(staging / "reports" / "generated-files.json", generated)
        if validation_report.failures:
            return BuildOutcome(
                published=False,
                summary=summary,
                validation=validation_payload,
                unresolved=stable_unresolved,
                error="staging catalog failed structural validation",
                blocking_import_failures=blocking_import_failures,
                nonblocking_import_failures=nonblocking_import_failures,
            )
        try:
            _publish_generated_tree(staging, root)
        except PublicationRecoveryError:
            preserve_staging = True
            raise
        return BuildOutcome(
            published=True,
            summary=summary,
            validation=validation_payload,
            unresolved=stable_unresolved,
            blocking_import_failures=blocking_import_failures,
            nonblocking_import_failures=nonblocking_import_failures,
        )
    finally:
        if not preserve_staging:
            shutil.rmtree(staging_parent, ignore_errors=True)


def read_summary(root: Path) -> Dict[str, int]:
    path = Path(root) / "reports" / "summary.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "duplicate",
        "imported",
        "inaccessible",
        "low_confidence",
        "parse_failure",
        "unknown_license",
        "unsafe_symlink",
    }
    if not isinstance(payload, dict) or set(payload) != expected or any(
        type(value) is not int or value < 0 for value in payload.values()
    ):
        raise ValueError("summary report has an invalid structure")
    return payload


def _is_blocking_import_source(synced: SyncedSource) -> bool:
    return synced.configured and synced.resolved.source.mode == "direct"


def _try_sync(
    spec: SourceSpec,
    cache_root: Path,
    locked: Optional[Dict[Tuple[str, str], Dict[str, object]]],
    synchronizer: Synchronizer,
    outcome: SyncOutcome,
    configured: bool,
    provenance: List[str],
) -> Optional[ResolvedSource]:
    locked_commit = None
    if locked is not None:
        locked_entry = locked.get((spec.id, spec.url))
        if locked_entry is None:
            failure = _unresolved(spec.id, "missing-resolved-lock-entry")
            outcome.unresolved.append(failure)
            outcome.lock_entries.append(
                _lock_entry(
                    spec,
                    None,
                    "unresolved",
                    provenance,
                    configured,
                    failure=failure,
                )
            )
            if configured and spec.mode == "direct":
                outcome.configured_direct_failures += 1
            return None
        locked_status = locked_entry.get("status")
        if locked_status != "resolved":
            failure = _locked_failure(locked_entry, spec.id)
            outcome.unresolved.append(failure)
            outcome.lock_entries.append(
                _lock_entry(
                    spec,
                    None,
                    str(locked_status),
                    provenance,
                    configured,
                    failure=failure,
                )
            )
            if configured and spec.mode == "direct":
                outcome.configured_direct_failures += 1
            return None
        locked_commit = locked_entry.get("commit")
        if not isinstance(locked_commit, str):
            failure = _unresolved(spec.id, "invalid-lock-commit")
            outcome.unresolved.append(failure)
            outcome.lock_entries.append(
                _lock_entry(
                    spec,
                    None,
                    "unresolved",
                    provenance,
                    configured,
                    failure=failure,
                )
            )
            if configured and spec.mode == "direct":
                outcome.configured_direct_failures += 1
            return None
    try:
        resolved = synchronizer(spec, cache_root, locked_commit=locked_commit)
    except (OSError, ValueError, RuntimeError) as error:
        failure = _unresolved(
            spec.id, "inaccessible", detail=type(error).__name__
        )
        outcome.unresolved.append(failure)
        outcome.lock_entries.append(
            _lock_entry(
                spec,
                None,
                "inaccessible",
                provenance,
                configured,
                failure=failure,
            )
        )
        if configured and spec.mode == "direct":
            outcome.configured_direct_failures += 1
        return None
    outcome.lock_entries.append(
        _lock_entry(spec, resolved.commit, "resolved", provenance, configured)
    )
    if spec.mode in {"index", "reference"}:
        outcome.sources.append(
            SyncedSource(resolved=resolved, index_provenance=provenance, configured=configured)
        )
    return resolved


def _lock_entry(
    spec: SourceSpec,
    commit: Optional[str],
    status: str,
    provenance: Sequence[str],
    configured: bool,
    failure: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    return {
        "commit": commit,
        "configured": configured,
        "default_categories": sorted(set(spec.default_categories)),
        "exclude_paths": sorted(set(spec.exclude_paths)),
        "failure": failure,
        "id": spec.id,
        "include_paths": sorted(set(spec.include_paths)),
        "index_provenance": sorted(set(provenance)),
        "index_source_id": spec.index_source_id,
        "mode": spec.mode,
        "redistribution_review": spec.redistribution_review,
        "registry_archive_mirror": spec.registry_archive_mirror,
        "status": status,
        "url": spec.url,
    }


def _read_locked_sources(path: Path) -> Dict[Tuple[str, str], Dict[str, object]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "1.0"
        or not isinstance(payload.get("sources"), list)
    ):
        raise ValueError("source lock must contain a sources array")
    result = {}
    for item in payload["sources"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("url"), str):
            raise ValueError("source lock entries require id and url strings")
        key = (item["id"], item["url"])
        if key in result:
            raise ValueError("source lock entries must be unique")
        status = item.get("status")
        commit = item.get("commit")
        if status not in {"resolved", "inaccessible", "unresolved"}:
            raise ValueError("source lock entry has an invalid status")
        if status == "resolved" and (
            not isinstance(commit, str)
            or re.fullmatch(r"[0-9a-f]{40}", commit) is None
        ):
            raise ValueError(
                "resolved source lock commit must be a lowercase 40-character SHA"
            )
        if status != "resolved" and commit is not None:
            raise ValueError("unresolved source lock entries cannot claim a commit")
        if status == "resolved":
            failure = item.get("failure")
            if failure is not None:
                raise ValueError("resolved source lock entries cannot claim a failure")
        else:
            _locked_failure(item, item["id"])
        result[key] = item
    return result


def _locked_failure(
    entry: Dict[str, object], expected_source_id: str
) -> Dict[str, object]:
    failure = entry.get("failure")
    if not isinstance(failure, dict):
        raise ValueError(
            "non-resolved source lock entries require failure metadata"
        )
    reason = failure.get("reason")
    source_id = failure.get("source_id")
    if not isinstance(reason, str) or not reason:
        raise ValueError("source lock failure requires a non-empty reason")
    if source_id != expected_source_id:
        raise ValueError("source lock failure source_id does not match its entry")
    return dict(failure)


def _restore_locked_source_fields(
    spec: SourceSpec,
    entry: Optional[Dict[str, object]],
    expected_configured: bool,
) -> None:
    if entry is None:
        raise ValueError(
            f"source lock/config mismatch: missing entry for {spec.id}"
        )
    mode = entry.get("mode")
    if mode not in {"direct", "index", "archive", "reference"}:
        raise ValueError("source lock entry has an invalid mode")
    if mode != spec.mode:
        raise ValueError(
            f"source lock/config mode mismatch for {spec.id}: {mode} != {spec.mode}"
        )
    if entry.get("configured") is not expected_configured:
        raise ValueError(
            f"source lock/config role mismatch for {spec.id}"
        )
    include_paths = _locked_string_list(entry, "include_paths")
    exclude_paths = _locked_string_list(entry, "exclude_paths")
    default_categories = _locked_string_list(entry, "default_categories")
    redistribution_review = entry.get("redistribution_review")
    registry_archive_mirror = entry.get("registry_archive_mirror")
    index_source_id = entry.get("index_source_id")
    if type(redistribution_review) is not bool or type(registry_archive_mirror) is not bool:
        raise ValueError("source lock review and mirror fields must be booleans")
    if index_source_id is not None and (
        not isinstance(index_source_id, str) or not index_source_id
    ):
        raise ValueError("source lock index_source_id must be a string or null")
    spec.include_paths = include_paths
    spec.exclude_paths = exclude_paths
    spec.default_categories = default_categories
    spec.redistribution_review = redistribution_review
    spec.registry_archive_mirror = registry_archive_mirror
    if index_source_id != spec.index_source_id:
        raise ValueError(
            f"source lock/config index role mismatch for {spec.id}"
        )


def _locked_string_list(entry: Dict[str, object], name: str) -> List[str]:
    value = entry.get(name)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"source lock {name} must be an array of strings")
    return _source_path_list(
        {name: value},
        name,
        [],
        allow_current=(name == "include_paths"),
    )


def _github_source_id(url: str) -> str:
    parsed = urlsplit(url)
    parts = parsed.path.strip("/").split("/")
    if parsed.scheme != "https" or parsed.netloc != "github.com" or len(parts) != 2:
        raise ValueError(f"not a canonical GitHub repository URL: {url}")
    return f"{parts[0]}/{parts[1]}"


def _unresolved(source_id: str, reason: str, **extra: object) -> Dict[str, object]:
    return {"reason": reason, "source_id": source_id, **extra}


def _stable_unresolved(items: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    keyed = {
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")): item
        for item in items
    }
    return [keyed[key] for key in sorted(keyed)]


def _projected_output_paths(candidates: Sequence[_Candidate], taxonomy: Taxonomy) -> List[str]:
    paths = []
    for candidate in candidates:
        base = catalog_path(candidate.record, candidate.classification, taxonomy)
        paths.extend(_parent_paths(base))
        paths.append((base / SIDECAR_NAME).as_posix())
        source_root = candidate.record.skill_root
        for current, directory_names, file_names in os.walk(
            source_root, topdown=True, followlinks=False
        ):
            current_path = Path(current)
            directory_names[:] = sorted(
                name for name in directory_names if name != ".git"
            )
            relative_parent = current_path.relative_to(source_root)
            for name in sorted(directory_names + file_names):
                if name == ".git" or (
                    relative_parent == Path(".") and name == SIDECAR_NAME
                ):
                    continue
                paths.append((base / relative_parent / name).as_posix())
    return paths


def _parent_paths(path: Path) -> List[str]:
    result = []
    current = Path()
    for part in path.parts:
        current = current / part
        result.append(current.as_posix())
    return result


def _prepare_staging(root: Path, staging: Path) -> None:
    staging.mkdir(parents=True)
    for name in ("skills", "licenses", "reports"):
        source = root / name
        target = staging / name
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, target, symlinks=True)
        else:
            target.mkdir()
    manifest_path = staging / "reports" / "generated-files.json"
    generated_skill_roots: List[str] = []
    generated_license_paths: List[str] = []
    if manifest_path.is_file() and not manifest_path.is_symlink():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            generated_skill_roots = _safe_manifest_paths(
                manifest.get("generated_skill_roots", []), "skills"
            )
            generated_license_paths = _safe_manifest_paths(
                manifest.get("generated_license_paths", []), "licenses"
            )
        except (OSError, ValueError, json.JSONDecodeError):
            generated_skill_roots = []
            generated_license_paths = []
    for relative in generated_skill_roots + generated_license_paths:
        _remove_staged_generated_path(staging, relative)
    for name in _GENERATED_REPORTS:
        path = staging / "reports" / name
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.exists():
            shutil.rmtree(path)


def _validate_managed_containers(
    root: Path, names: Sequence[str] = ("skills", "licenses", "reports")
) -> None:
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise ValueError("catalog root must be a real directory")
    for name in names:
        path = root / name
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError(
                f"managed container {name} must be a real directory"
            )


def _managed_root_user_content(root: Path) -> List[str]:
    manifest_path = root / "reports" / "generated-files.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        roots = _safe_manifest_paths(
            manifest.get("generated_skill_roots", []), "skills"
        )
        generated = set(
            _safe_manifest_paths(manifest.get("generated_paths", []), "skills")
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return ["reports/generated-files.json"]
    if not generated:
        return []
    unexpected = []
    for relative_root in roots:
        skill_root = root / PurePosixPath(relative_root)
        if not skill_root.is_dir() or skill_root.is_symlink():
            continue
        for path in skill_root.rglob("*"):
            relative = path.relative_to(root).as_posix()
            if relative not in generated:
                unexpected.append(relative)
    return sorted(set(unexpected))


def _generated_result_paths(
    staging: Path, results: Sequence[ImportResult]
) -> List[str]:
    paths = []
    for result in results:
        root = staging / result.relative_path
        paths.append(result.relative_path.as_posix())
        paths.extend(
            path.relative_to(staging).as_posix() for path in root.rglob("*")
        )
    return sorted(set(paths))


def _safe_manifest_paths(values: object, prefix: str) -> List[str]:
    if not isinstance(values, list):
        raise ValueError("generated path manifest fields must be arrays")
    result = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("generated path manifest entries must be strings")
        path = PurePosixPath(value)
        if path.is_absolute() or not path.parts or path.parts[0] != prefix or any(
            part in {"", ".", ".."} for part in path.parts
        ):
            raise ValueError("unsafe generated path manifest entry")
        result.append(value)
    return sorted(set(result))


def _remove_staged_generated_path(staging: Path, relative: str) -> None:
    target = staging / PurePosixPath(relative)
    try:
        target.resolve(strict=False).relative_to(staging.resolve())
    except ValueError as error:
        raise ValueError("generated path escapes staging") from error
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)


def _relative_tree_paths(root: Path) -> List[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def _write_build_reports(
    staging: Path,
    sync: SyncOutcome,
    results: Sequence[ImportResult],
    unresolved: Sequence[Dict[str, object]],
    summary: Dict[str, int],
) -> None:
    reports = staging / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    _write_json(reports / "sources.lock.json", sync.lock_payload())
    _write_json(reports / "duplicates.json", {"duplicates": cluster_duplicates(results)})
    _write_json(reports / "unresolved.json", {"unresolved": list(unresolved)})
    _write_json(reports / "summary.json", summary)
    records = []
    for result in results:
        sidecar_path = staging / result.sidecar_path
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        records.append({"catalog_path": result.relative_path.as_posix(), **sidecar})
    serialized = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for item in sorted(records, key=lambda item: item["catalog_path"])
    )
    _write_text(reports / "catalog.jsonl", serialized)


def _summary(
    results: Sequence[ImportResult],
    unresolved: Sequence[Dict[str, object]],
    parse_failures: int,
    catalog_root: Optional[Path] = None,
) -> Dict[str, int]:
    duplicates = cluster_duplicates(results)
    low_confidence = 0
    if catalog_root is not None:
        for result in results:
            sidecar = json.loads(
                (catalog_root / result.sidecar_path).read_text(encoding="utf-8")
            )
            if sidecar["classification"]["needs_review"]:
                low_confidence += 1
    return {
        "duplicate": sum(len(paths) for paths in duplicates.values()),
        "imported": len(results),
        "inaccessible": sum(item.get("reason") == "inaccessible" for item in unresolved),
        "low_confidence": low_confidence,
        "parse_failure": parse_failures,
        "unknown_license": sum(result.record.license is None for result in results),
        "unsafe_symlink": sum(
            1
            for result in results
            for relative in result.excluded_paths
            if (result.record.skill_root / PurePosixPath(relative)).is_symlink()
        ),
    }


def _publish_generated_tree(staging: Path, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    backup = staging.parent / "backup"
    backup.mkdir()
    published = []
    moved_old = []
    try:
        for name in ("skills", "licenses", "reports"):
            destination = root / name
            old = backup / name
            if destination.exists() or destination.is_symlink():
                os.replace(destination, old)
                moved_old.append(name)
            os.replace(staging / name, destination)
            published.append(name)
    except OSError as publish_error:
        try:
            for name in reversed(published):
                destination = root / name
                failed_new = staging / f"failed-{name}"
                if destination.exists() or destination.is_symlink():
                    os.replace(destination, failed_new)
            for name in reversed(moved_old):
                old = backup / name
                if old.exists() or old.is_symlink():
                    os.replace(old, root / name)
        except OSError as recovery_error:
            raise PublicationRecoveryError(backup, recovery_error) from publish_error
        raise


def _write_json(path: Path, payload: object) -> None:
    _write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _write_text(path: Path, text: str) -> None:
    atomic_write_text(path, text)

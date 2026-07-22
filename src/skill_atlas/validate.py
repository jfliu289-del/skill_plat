"""Read-only validation for a materialized Skill Atlas catalog."""

import hashlib
import json
from collections import defaultdict
import os
from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import unicodedata

from .materialize import SIDECAR_NAME, catalog_path, hash_materialized_skill
from .models import (
    Classification,
    PathCollision,
    SkillRecord,
    SourceSpec,
    Taxonomy,
    ValidationFailure,
    ValidationReport,
)


_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY = re.compile(
    r"^https://github[.]com/[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+$"
)
_RISK = re.compile(r"^R[0-4]$")

_ROOT_REQUIRED = {
    "schema_version",
    "taxonomy_version",
    "classifier_version",
    "provenance",
    "classification",
    "integrity",
}
_PROVENANCE_REQUIRED = {
    "repository",
    "commit",
    "source_path",
    "license",
    "redistribution_review",
    "registry_archive_mirror",
}
_PROVENANCE_ALLOWED = _PROVENANCE_REQUIRED | {"license_evidence"}
_CLASSIFICATION_REQUIRED = {
    "primary_category",
    "secondary_categories",
    "tasks",
    "stages",
    "artifacts",
    "domains",
    "audiences",
    "risk_level",
    "confidence",
    "needs_review",
    "reasons",
}
_INTEGRITY_REQUIRED = {"content_hash", "skill_md_hash", "excluded_paths"}


def portable_path_key(path: str) -> str:
    """Normalize one POSIX catalog path for case-insensitive macOS portability."""

    return unicodedata.normalize("NFC", path).casefold()


def detect_path_collisions(paths: Iterable[str]) -> List[PathCollision]:
    """Return stable groups of distinct paths that have one portable key."""

    grouped: Dict[str, set] = defaultdict(set)
    for value in paths:
        if not isinstance(value, str):
            raise TypeError("catalog paths must be strings")
        grouped[portable_path_key(value)].add(value)
    return [
        PathCollision(normalized_path=key, paths=sorted(values))
        for key, values in sorted(grouped.items())
        if len(values) > 1
    ]


def validate_catalog(root: Path, taxonomy: Taxonomy) -> ValidationReport:
    """Validate sidecars, bundle hashes, central records, and duplicate clusters."""

    root = Path(root)
    failures: List[ValidationFailure] = []
    skills_root = root / "skills"
    skill_roots = _discover_materialized_skills(skills_root, failures, root)

    filesystem_paths = _all_relative_paths(root)
    for collision in detect_path_collisions(filesystem_paths):
        failures.append(
            ValidationFailure(
                "path-collision",
                collision.paths[0],
                "portable path collision: " + ", ".join(collision.paths),
            )
        )

    sidecars: Dict[str, Dict[str, object]] = {}
    for skill_root in skill_roots:
        relative_skill = skill_root.relative_to(root).as_posix()
        sidecar_path = skill_root / SIDECAR_NAME
        if sidecar_path.is_symlink() or not sidecar_path.is_file():
            failures.append(
                ValidationFailure(
                    "missing-sidecar",
                    relative_skill,
                    f"Skill root must contain one regular {SIDECAR_NAME}",
                )
            )
            continue
        sidecar_relative = sidecar_path.relative_to(root).as_posix()
        payload = _read_json_object(sidecar_path, sidecar_relative, failures)
        if payload is None:
            continue
        sidecars[relative_skill] = payload
        _validate_sidecar(payload, sidecar_relative, taxonomy, failures)
        _validate_route(payload, skill_root, relative_skill, taxonomy, failures)
        _validate_hashes(payload, skill_root, relative_skill, failures)

    central_records = _validate_central_catalog(root, sidecars, failures)
    _validate_duplicates(root, sidecars, failures)
    return ValidationReport(
        failures=sorted(failures),
        skill_count=len(skill_roots),
        central_record_count=central_records,
    )


def _discover_materialized_skills(
    skills_root: Path, failures: List[ValidationFailure], catalog_root: Path
) -> List[Path]:
    if skills_root.is_symlink() or not skills_root.is_dir():
        failures.append(
            ValidationFailure("missing-skills-root", "skills", "skills root is missing")
        )
        return []
    skill_documents = []
    symlinks = []
    for current, directory_names, file_names in os.walk(
        skills_root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        retained_directories = []
        for name in sorted(directory_names):
            child = current_path / name
            if child.is_symlink():
                symlinks.append(child)
            else:
                retained_directories.append(name)
        directory_names[:] = retained_directories
        for name in sorted(file_names):
            path = current_path / name
            if path.is_symlink():
                symlinks.append(path)
            if name == "SKILL.md":
                skill_documents.append(path)

    roots = []
    non_root_documents = []
    for path in sorted(skill_documents, key=lambda item: item.as_posix()):
        relative = path.relative_to(catalog_root).as_posix()
        parent_parts = path.parent.relative_to(catalog_root).parts
        if path.is_symlink() or not path.is_file():
            failures.append(
                ValidationFailure(
                    "invalid-skill-md", relative, "SKILL.md must be a regular file"
                )
            )
            continue
        if len(parent_parts) == 7 and parent_parts[0] == "skills":
            roots.append(path.parent)
        else:
            non_root_documents.append(path)

    for path in non_root_documents:
        if not any(_is_lexically_within(path, root) for root in roots):
            failures.append(
                ValidationFailure(
                    "unexpected-skill-md",
                    path.relative_to(catalog_root).as_posix(),
                    "SKILL.md is outside every fixed catalog leaf",
                )
            )
    for path in sorted(symlinks, key=lambda item: item.as_posix()):
        if not any(_is_lexically_within(path, root) for root in roots):
            failures.append(
                ValidationFailure(
                    "unexpected-symlink",
                    path.relative_to(catalog_root).as_posix(),
                    "symlink is outside every fixed catalog Skill leaf",
                )
            )
    return roots


def _is_lexically_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _all_relative_paths(root: Path) -> List[str]:
    if root.is_symlink() or not root.is_dir():
        return []
    paths = []
    for path in root.rglob("*"):
        try:
            paths.append(path.relative_to(root).as_posix())
        except ValueError:
            continue
    return sorted(set(paths))


def _read_json_object(
    path: Path, relative: str, failures: List[ValidationFailure]
) -> Optional[Dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        failures.append(
            ValidationFailure("invalid-json", relative, f"cannot read JSON object: {error}")
        )
        return None
    if not isinstance(payload, dict):
        failures.append(
            ValidationFailure("schema-type", relative, "JSON document must be an object")
        )
        return None
    return payload


def _validate_sidecar(
    payload: Dict[str, object],
    path: str,
    taxonomy: Taxonomy,
    failures: List[ValidationFailure],
) -> None:
    _object_shape(payload, _ROOT_REQUIRED, _ROOT_REQUIRED, path, failures)
    _nonempty_string(payload, "schema_version", path, failures)
    _nonempty_string(payload, "classifier_version", path, failures)
    taxonomy_version = _nonempty_string(payload, "taxonomy_version", path, failures)
    if taxonomy_version is not None and taxonomy_version != taxonomy.version:
        _failure(failures, "taxonomy-version-mismatch", path, "taxonomy_version does not match configured taxonomy")

    provenance = _object(payload, "provenance", path, failures)
    if provenance is not None:
        ppath = f"{path}#/provenance"
        _object_shape(provenance, _PROVENANCE_REQUIRED, _PROVENANCE_ALLOWED, ppath, failures)
        repository = _nonempty_string(provenance, "repository", ppath, failures)
        if repository is not None and _REPOSITORY.fullmatch(repository) is None:
            _failure(failures, "schema-format", f"{ppath}/repository", "repository must be an exact HTTPS GitHub repository URL")
        commit = _nonempty_string(provenance, "commit", ppath, failures)
        if commit is not None and _COMMIT.fullmatch(commit) is None:
            _failure(failures, "schema-format", f"{ppath}/commit", "commit must be a lowercase 40-character SHA")
        _nonempty_string(provenance, "source_path", ppath, failures)
        license_value = provenance.get("license")
        if license_value is not None and (not isinstance(license_value, str) or not license_value):
            _failure(failures, "schema-type", f"{ppath}/license", "license must be a non-empty string or null")
        evidence = _string_array(provenance, "license_evidence", ppath, failures, required=False)
        review = _boolean(provenance, "redistribution_review", ppath, failures)
        mirror = _boolean(provenance, "registry_archive_mirror", ppath, failures)
        if review is False and (license_value is None or not evidence):
            _failure(failures, "schema-condition", ppath, "redistribution_review=false requires a known license and evidence")
        if repository == "https://github.com/openclaw/skills" and mirror is not True:
            _failure(failures, "schema-condition", ppath, "OpenClaw archive records must be marked as mirrors")

    classification = _object(payload, "classification", path, failures)
    if classification is not None:
        cpath = f"{path}#/classification"
        _object_shape(classification, _CLASSIFICATION_REQUIRED, _CLASSIFICATION_REQUIRED, cpath, failures)
        primary = _nonempty_string(classification, "primary_category", cpath, failures)
        if primary is not None and primary not in taxonomy.categories:
            _failure(failures, "unknown-category", f"{cpath}/primary_category", f"unknown category: {primary}")
        secondary = _string_array(classification, "secondary_categories", cpath, failures)
        for value in secondary or []:
            if value not in taxonomy.categories:
                _failure(failures, "unknown-category", f"{cpath}/secondary_categories", f"unknown category: {value}")
        if primary is not None and primary in (secondary or []):
            _failure(failures, "schema-condition", cpath, "primary category cannot also be secondary")
        for name in ("tasks", "stages", "artifacts", "domains", "audiences"):
            values = _string_array(classification, name, cpath, failures)
            vocabulary = set(getattr(taxonomy, name))
            singular = name[:-1] if name.endswith("s") else name
            for value in values or []:
                if value not in vocabulary:
                    _failure(failures, f"unknown-{singular}", f"{cpath}/{name}", f"unknown controlled {singular}: {value}")
        risk = _nonempty_string(classification, "risk_level", cpath, failures)
        if risk is not None and _RISK.fullmatch(risk) is None:
            _failure(failures, "schema-format", f"{cpath}/risk_level", "risk_level must be R0 through R4")
        confidence = classification.get("confidence")
        if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
            _failure(failures, "schema-type", f"{cpath}/confidence", "confidence must be a number from 0 to 1")
        _boolean(classification, "needs_review", cpath, failures)
        _string_array(classification, "reasons", cpath, failures)

    integrity = _object(payload, "integrity", path, failures)
    if integrity is not None:
        ipath = f"{path}#/integrity"
        _object_shape(integrity, _INTEGRITY_REQUIRED, _INTEGRITY_REQUIRED, ipath, failures)
        for name in ("content_hash", "skill_md_hash"):
            value = _nonempty_string(integrity, name, ipath, failures)
            if value is not None and _SHA256.fullmatch(value) is None:
                _failure(failures, "schema-format", f"{ipath}/{name}", f"{name} must be a lowercase SHA-256")
        _string_array(integrity, "excluded_paths", ipath, failures)


def _object_shape(
    value: Dict[str, object],
    required: set,
    allowed: set,
    path: str,
    failures: List[ValidationFailure],
) -> None:
    for name in sorted(required - set(value)):
        _failure(failures, "schema-required", path, f"missing required property: {name}")
    for name in sorted(set(value) - allowed):
        _failure(failures, "schema-additional-property", f"{path}#/{name}" if "#" not in path else f"{path}/{name}", f"additional property is forbidden: {name}")


def _object(value: Dict[str, object], name: str, path: str, failures: List[ValidationFailure]) -> Optional[Dict[str, object]]:
    item = value.get(name)
    if not isinstance(item, dict):
        if name in value:
            _failure(failures, "schema-type", f"{path}#/{name}", f"{name} must be an object")
        return None
    return item


def _nonempty_string(value: Dict[str, object], name: str, path: str, failures: List[ValidationFailure]) -> Optional[str]:
    item = value.get(name)
    if not isinstance(item, str) or not item:
        if name in value:
            _failure(failures, "schema-type", f"{path}/{name}", f"{name} must be a non-empty string")
        return None
    return item


def _boolean(value: Dict[str, object], name: str, path: str, failures: List[ValidationFailure]) -> Optional[bool]:
    item = value.get(name)
    if type(item) is not bool:
        if name in value:
            _failure(failures, "schema-type", f"{path}/{name}", f"{name} must be a boolean")
        return None
    return item


def _string_array(
    value: Dict[str, object],
    name: str,
    path: str,
    failures: List[ValidationFailure],
    required: bool = True,
) -> Optional[List[str]]:
    item = value.get(name)
    if item is None and not required:
        return []
    if not isinstance(item, list) or any(not isinstance(entry, str) or not entry for entry in item):
        if name in value or required:
            _failure(failures, "schema-type", f"{path}/{name}", f"{name} must be an array of non-empty strings")
        return None
    if len(item) != len(set(item)):
        _failure(failures, "schema-unique", f"{path}/{name}", f"{name} values must be unique")
    return item


def _validate_route(
    payload: Dict[str, object],
    skill_root: Path,
    relative_skill: str,
    taxonomy: Taxonomy,
    failures: List[ValidationFailure],
) -> None:
    parts = Path(relative_skill).parts
    classification = payload.get("classification")
    if len(parts) < 3 or not isinstance(classification, dict):
        return
    category_id = classification.get("primary_category")
    category = taxonomy.categories.get(category_id) if isinstance(category_id, str) else None
    if category is None:
        return
    group = next((item for item in taxonomy.groups.values() if category_id in {entry.id for entry in item.categories}), None)
    expected_group = f"{group.id}-{group.slug}" if group else ""
    expected_category = f"{category.id}-{category.slug}"
    if parts[0] != "skills" or parts[1] != expected_group:
        _failure(failures, "group-path-mismatch", relative_skill, f"expected taxonomy group path {expected_group}")
    if parts[2] != expected_category:
        _failure(failures, "category-path-mismatch", relative_skill, f"expected taxonomy category path {expected_category}")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        return
    repository = provenance.get("repository")
    source_path = provenance.get("source_path")
    commit = provenance.get("commit")
    if not all(isinstance(value, str) for value in (repository, source_path, commit)):
        return
    try:
        repository_parts = repository.removeprefix("https://github.com/").split("/")
        if len(repository_parts) != 2:
            raise ValueError("invalid repository")
        source = SourceSpec(
            id=f"{repository_parts[0]}/{repository_parts[1]}",
            url=repository,
            mode="direct",
            registry_archive_mirror=bool(
                provenance.get("registry_archive_mirror", False)
            ),
        )
        record = SkillRecord(
            source=source,
            repository=repository,
            commit=commit,
            source_path=source_path,
            skill_root=skill_root,
            name=skill_root.name,
            registry_archive_mirror=bool(
                provenance.get("registry_archive_mirror", False)
            ),
        )
        expected = catalog_path(
            record,
            Classification(primary_category=category_id),
            taxonomy,
        ).as_posix()
    except (TypeError, ValueError) as error:
        _failure(
            failures,
            "catalog-path-mismatch",
            relative_skill,
            f"cannot reconstruct catalog path from provenance: {error}",
        )
        return
    if expected != relative_skill:
        _failure(
            failures,
            "catalog-path-mismatch",
            relative_skill,
            f"provenance reconstructs to {expected}",
        )


def _validate_hashes(payload: Dict[str, object], skill_root: Path, relative_skill: str, failures: List[ValidationFailure]) -> None:
    integrity = payload.get("integrity")
    if not isinstance(integrity, dict):
        return
    expected_skill = integrity.get("skill_md_hash")
    if isinstance(expected_skill, str):
        actual_skill = hashlib.sha256((skill_root / "SKILL.md").read_bytes()).hexdigest()
        if actual_skill != expected_skill:
            _failure(failures, "skill-md-hash-mismatch", f"{relative_skill}/SKILL.md", "SKILL.md bytes do not match the sidecar hash")
    expected_content = integrity.get("content_hash")
    if isinstance(expected_content, str):
        try:
            actual_content = hash_materialized_skill(skill_root)
        except (OSError, ValueError) as error:
            _failure(failures, "content-hash-error", relative_skill, f"cannot hash complete Skill bundle: {error}")
        else:
            if actual_content != expected_content:
                _failure(failures, "content-hash-mismatch", relative_skill, "complete Skill bundle does not match the sidecar hash")


def _validate_central_catalog(root: Path, sidecars: Dict[str, Dict[str, object]], failures: List[ValidationFailure]) -> int:
    path = root / "reports" / "catalog.jsonl"
    relative = "reports/catalog.jsonl"
    if path.is_symlink() or not path.is_file():
        _failure(failures, "missing-central-catalog", relative, "central catalog.jsonl is missing")
        return 0
    records: Dict[str, Dict[str, object]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        _failure(failures, "invalid-central-catalog", relative, f"cannot read central catalog: {error}")
        return 0
    for index, line in enumerate(lines, start=1):
        record_path = f"{relative}:{index}"
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            _failure(failures, "invalid-central-record", record_path, f"invalid JSON: {error}")
            continue
        if not isinstance(item, dict) or not isinstance(item.get("catalog_path"), str):
            _failure(failures, "invalid-central-record", record_path, "record must contain string catalog_path")
            continue
        catalog_path = item["catalog_path"]
        if catalog_path in records:
            _failure(failures, "duplicate-central-path", record_path, f"duplicate catalog_path: {catalog_path}")
            continue
        records[catalog_path] = item
    missing = sorted(set(sidecars) - set(records))
    extra = sorted(set(records) - set(sidecars))
    for value in missing:
        _failure(failures, "central-path-mismatch", relative, f"missing central record for {value}")
    for value in extra:
        _failure(failures, "central-path-mismatch", relative, f"central record has no Skill root: {value}")
    for value in sorted(set(sidecars) & set(records)):
        central = dict(records[value])
        central.pop("catalog_path", None)
        if central != sidecars[value]:
            _failure(failures, "central-record-mismatch", value, "central record does not match root sidecar")
    return len(records)


def _validate_duplicates(root: Path, sidecars: Dict[str, Dict[str, object]], failures: List[ValidationFailure]) -> None:
    path = root / "reports" / "duplicates.json"
    relative = "reports/duplicates.json"
    payload = _read_json_object(path, relative, failures) if path.is_file() and not path.is_symlink() else None
    if payload is None:
        if not path.is_file() or path.is_symlink():
            _failure(failures, "missing-duplicates-report", relative, "duplicates.json is missing")
        return
    actual = payload.get("duplicates")
    if not isinstance(actual, dict):
        _failure(failures, "invalid-duplicates-report", relative, "duplicates must be an object")
        return
    grouped: Dict[str, List[str]] = defaultdict(list)
    for catalog_path, sidecar in sidecars.items():
        integrity = sidecar.get("integrity")
        if isinstance(integrity, dict) and isinstance(integrity.get("content_hash"), str):
            grouped[integrity["content_hash"]].append(catalog_path)
    expected = {key: sorted(values) for key, values in sorted(grouped.items()) if len(values) > 1}
    normalized_actual = {
        key: sorted(values)
        for key, values in sorted(actual.items())
        if isinstance(key, str) and isinstance(values, list) and all(isinstance(value, str) for value in values)
    }
    if normalized_actual != actual or actual != expected:
        _failure(failures, "duplicate-cluster-mismatch", relative, "duplicate clusters do not match sidecar content hashes")


def _failure(failures: List[ValidationFailure], code: str, path: str, message: str) -> None:
    failures.append(ValidationFailure(code=code, path=path, message=message))

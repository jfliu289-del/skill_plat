"""Safely materialize complete upstream Skill bundles into the catalog."""

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlsplit

from .models import Classification, ImportResult, SkillRecord, Taxonomy


SCHEMA_VERSION = "1.0"
CLASSIFIER_VERSION = "1.0"
SIDECAR_NAME = "skill-atlas.json"
_HASH_FORMAT = b"skill-atlas-content-v1\0"
_COMMIT = re.compile(r"[0-9a-f]{40}")
_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_GROUP_ID = re.compile(r"[A-F]")
_CATEGORY_ID = re.compile(r"C(?:0[0-9]|1[0-9])")
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_RISK = re.compile(r"R[0-4]")


class MaterializationError(ValueError):
    """Raised when a Skill cannot be represented without losing integrity."""


class MaterializationSecurityError(MaterializationError):
    """Raised when a source or destination path violates a safety boundary."""


@dataclass(frozen=True)
class _SourceEntry:
    source: Path
    relative: str
    kind: str
    mode: int
    link_target: Optional[str] = None
    copy_symlink: bool = False


def catalog_path(
    record: SkillRecord,
    classification: Classification,
    taxonomy: Taxonomy,
) -> Path:
    """Return a validated, deterministic catalog path for one Skill."""

    owner, repository = _repository_parts(record)
    source_parts = _source_path_parts(record.source_path)
    if source_parts:
        original_directory = source_parts[-1]
        if original_directory != record.skill_root.name:
            raise MaterializationSecurityError(
                "source_path directory does not match the Skill root"
            )
        parent_key = _source_parent_key(source_parts[:-1])
    else:
        original_directory = "_repository-root"
        parent_key = "_root-skill"

    category = taxonomy.categories.get(classification.primary_category)
    if category is None or category.id != classification.primary_category:
        raise MaterializationError(
            f"unknown primary category: {classification.primary_category}"
        )
    matching_groups = [
        (group_key, group)
        for group_key, group in taxonomy.groups.items()
        if sum(item.id == category.id for item in group.categories) == 1
    ]
    if len(matching_groups) != 1:
        raise MaterializationError(
            f"category {category.id} must belong to exactly one taxonomy group"
        )
    group_key, group = matching_groups[0]
    if group_key != group.id:
        raise MaterializationSecurityError("taxonomy group key does not match its id")
    _safe_taxonomy_component(group.id, group.slug, is_group=True)
    _safe_taxonomy_component(category.id, category.slug, is_group=False)

    path = Path(
        "skills",
        f"{group.id}-{group.slug}",
        f"{category.id}-{category.slug}",
        owner,
        repository,
        parent_key,
        original_directory,
    )
    _require_safe_relative_path(path)
    return path


def materialize(
    record: SkillRecord,
    destination_root: Path,
    classification: Classification,
    taxonomy: Taxonomy,
) -> ImportResult:
    """Copy one complete Skill and create its fixed metadata sidecar."""

    relative_path = catalog_path(record, classification, taxonomy)
    normalized_classification = _normalized_classification(
        classification, taxonomy
    )
    normalized_provenance = _normalized_provenance(record)
    source_root = _validated_source_root(record.skill_root)
    source_root_mode = stat.S_IMODE(source_root.lstat().st_mode)
    entries, initial_exclusions = _collect_source_entries(source_root)

    skill_entry = next(
        (entry for entry in entries if entry.relative == "SKILL.md"), None
    )
    if skill_entry is None or skill_entry.kind != "file":
        raise MaterializationError("Skill root must contain a regular SKILL.md")
    actual_skill_hash = _hash_regular_file(skill_entry.source)
    if record.skill_md_hash is not None and record.skill_md_hash != actual_skill_hash:
        raise MaterializationError("recorded SKILL.md hash does not match source bytes")

    destination_root = Path(destination_root)
    _prepare_destination_root(destination_root)
    destination_resolved = destination_root.resolve()
    target = destination_root / relative_path
    _require_destination_containment(target, destination_resolved)
    _make_safe_parent_directories(
        destination_root, relative_path.parent, destination_resolved
    )
    _require_destination_containment(target, destination_resolved)
    reserved = False
    complete = False
    try:
        try:
            target.mkdir(mode=0o700)
        except FileExistsError as error:
            raise MaterializationError(
                f"catalog target already exists: {relative_path}"
            ) from error
        reserved = True
        excluded_paths = _copy_entries(
            entries, target, initial_exclusions
        )
        copied_skill_hash = _hash_regular_file(target / "SKILL.md")
        if copied_skill_hash != actual_skill_hash:
            raise MaterializationError("copied SKILL.md bytes failed integrity check")
        content_hash = hash_materialized_skill(target)

        sidecar = {
            "schema_version": SCHEMA_VERSION,
            "taxonomy_version": taxonomy.version,
            "classifier_version": CLASSIFIER_VERSION,
            "provenance": normalized_provenance,
            "classification": normalized_classification,
            "integrity": {
                "content_hash": content_hash,
                "skill_md_hash": actual_skill_hash,
                "excluded_paths": excluded_paths,
            },
        }
        _write_sidecar(target / SIDECAR_NAME, sidecar)
        os.chmod(target, source_root_mode)
        complete = True
    finally:
        if reserved and not complete:
            _remove_reserved_target(target)

    return ImportResult(
        record=record,
        relative_path=relative_path,
        content_hash=content_hash,
        skill_md_hash=actual_skill_hash,
        excluded_paths=excluded_paths,
        sidecar_path=relative_path / SIDECAR_NAME,
    )


def cluster_duplicates(results: Iterable[ImportResult]) -> Dict[str, List[str]]:
    """Group hashes with at least two distinct catalog variants."""

    grouped: Dict[str, Set[str]] = {}
    for result in results:
        grouped.setdefault(result.content_hash, set()).add(
            result.relative_path.as_posix()
        )
    return {
        content_hash: sorted(paths)
        for content_hash, paths in sorted(grouped.items())
        if len(paths) > 1
    }


def hash_materialized_skill(skill_root: Path) -> str:
    """Recompute the retained upstream bundle hash from a materialized Skill."""

    root = _validated_source_root(skill_root)
    entries = _collect_materialized_entries(root)
    digest = hashlib.sha256()
    digest.update(_HASH_FORMAT)
    for entry in entries:
        _hash_field(digest, entry.relative.encode("utf-8"))
        _hash_field(digest, entry.kind.encode("ascii"))
        _hash_field(digest, f"{entry.mode:04o}".encode("ascii"))
        if entry.kind == "file":
            _hash_regular_entry(entry, digest)
        elif entry.kind == "symlink":
            try:
                current_target = os.readlink(entry.source)
            except OSError as error:
                raise MaterializationSecurityError(
                    f"cannot read materialized symlink: {entry.relative}"
                ) from error
            if current_target != entry.link_target:
                raise MaterializationSecurityError(
                    f"materialized symlink changed while hashing: {entry.relative}"
                )
            _hash_field(digest, os.fsencode(current_target))
        else:
            _hash_field(digest, b"")
    return digest.hexdigest()


def _repository_parts(record: SkillRecord) -> Tuple[str, str]:
    parsed = urlsplit(record.repository)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise MaterializationSecurityError("repository must be an HTTPS GitHub URL")
    parts = parsed.path.removeprefix("/").split("/")
    if (
        len(parts) != 2
        or _OWNER.fullmatch(parts[0]) is None
        or _REPOSITORY.fullmatch(parts[1]) is None
    ):
        raise MaterializationSecurityError("repository URL has unsafe components")
    if record.repository != record.source.url:
        raise MaterializationSecurityError("record repository does not match its source")
    return parts[0], parts[1]


def _source_path_parts(value: str) -> Tuple[str, ...]:
    if value == ".":
        return ()
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or "\x00" in value
        or "\n" in value
        or "\r" in value
    ):
        raise MaterializationSecurityError(f"unsafe source path: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise MaterializationSecurityError(f"unsafe source path: {value!r}")
    return tuple(_safe_component(part, "source path") for part in path.parts)


def _source_parent_key(parts: Sequence[str]) -> str:
    if not parts:
        return "_root"
    if (
        len(parts) == 1
        and parts[0] not in {"_root", "_root-skill"}
        and not parts[0].startswith("_encoded-")
    ):
        return parts[0]
    encoded = base64.urlsafe_b64encode("/".join(parts).encode("utf-8")).decode(
        "ascii"
    ).rstrip("=")
    kind = "s" if len(parts) == 1 else "m"
    return f"_encoded-{kind}-{encoded}"


def _safe_component(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise MaterializationSecurityError(f"unsafe {label} component: {value!r}")
    return value


def _safe_taxonomy_component(identifier: str, slug: str, is_group: bool) -> None:
    identifier_pattern = _GROUP_ID if is_group else _CATEGORY_ID
    if identifier_pattern.fullmatch(identifier) is None or _SLUG.fullmatch(slug) is None:
        raise MaterializationSecurityError("unsafe taxonomy route component")


def _require_safe_relative_path(path: Path) -> None:
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise MaterializationSecurityError(f"unsafe catalog path: {path}")
    for part in path.parts:
        _safe_component(part, "catalog path")


def _normalized_classification(
    classification: Classification, taxonomy: Taxonomy
) -> Dict[str, object]:
    if classification.primary_category not in taxonomy.categories:
        raise MaterializationError("classification primary category is not controlled")
    secondary = _normalized_values(
        classification.secondary_categories, "secondary category"
    )
    if classification.primary_category in secondary:
        raise MaterializationError("primary category cannot also be secondary")
    if any(value not in taxonomy.categories for value in secondary):
        raise MaterializationError("classification contains an unknown secondary category")

    controlled = {}
    for name in ("tasks", "stages", "artifacts", "domains", "audiences"):
        values = _normalized_values(getattr(classification, name), name)
        if any(value not in getattr(taxonomy, name) for value in values):
            raise MaterializationError(f"classification contains an unknown {name} tag")
        controlled[name] = values
    if _RISK.fullmatch(classification.risk_level) is None:
        raise MaterializationError("classification risk level must be R0 through R4")
    if (
        type(classification.confidence) not in (int, float)
        or not 0 <= classification.confidence <= 1
    ):
        raise MaterializationError("classification confidence must be between 0 and 1")
    if type(classification.needs_review) is not bool:
        raise MaterializationError("classification needs_review must be a boolean")

    return {
        "primary_category": classification.primary_category,
        "secondary_categories": secondary,
        **controlled,
        "risk_level": classification.risk_level,
        "confidence": classification.confidence,
        "needs_review": classification.needs_review,
        "reasons": _normalized_values(classification.reasons, "reason"),
    }


def _normalized_values(values: Iterable[str], label: str) -> List[str]:
    result = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise MaterializationError(f"{label} values must be non-empty strings")
        result.append(value)
    return sorted(set(result))


def _normalized_provenance(record: SkillRecord) -> Dict[str, object]:
    _repository_parts(record)
    _source_path_parts(record.source_path)
    if _COMMIT.fullmatch(record.commit) is None:
        raise MaterializationError("source commit must be a lowercase 40-character SHA")
    if record.license is not None and (
        not isinstance(record.license, str) or not record.license
    ):
        raise MaterializationError("license must be a non-empty string or null")
    license_evidence = _normalized_values(record.license_evidence, "license evidence")
    if type(record.redistribution_review) is not bool:
        raise MaterializationError("redistribution_review must be a boolean")
    if not record.redistribution_review and (
        record.license is None or not license_evidence
    ):
        raise MaterializationError(
            "redistribution without review requires license evidence"
        )
    if type(record.registry_archive_mirror) is not bool:
        raise MaterializationError("registry_archive_mirror must be a boolean")
    if record.repository == "https://github.com/openclaw/skills" and not (
        record.registry_archive_mirror
    ):
        raise MaterializationError("OpenClaw archive records must retain mirror status")
    return {
        "repository": record.repository,
        "commit": record.commit,
        "source_path": record.source_path,
        "license": record.license,
        "license_evidence": license_evidence,
        "redistribution_review": record.redistribution_review,
        "registry_archive_mirror": record.registry_archive_mirror,
    }


def _validated_source_root(path: Path) -> Path:
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise MaterializationSecurityError("Skill root must be a real directory")
    resolved = path.resolve()
    skill_md = path / "SKILL.md"
    if skill_md.is_symlink() or not skill_md.is_file():
        raise MaterializationError("Skill root must contain a regular SKILL.md")
    try:
        skill_md.resolve().relative_to(resolved)
    except ValueError as error:
        raise MaterializationSecurityError("SKILL.md escapes the Skill root") from error
    return resolved


def _collect_source_entries(root: Path) -> Tuple[List[_SourceEntry], Set[str]]:
    entries: List[_SourceEntry] = []
    excluded: Set[str] = set()

    def visit(directory: Path, parent: PurePosixPath) -> None:
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            raise MaterializationError(f"cannot enumerate Skill directory: {directory}") from error
        for child in children:
            relative_path = parent / child.name
            relative = relative_path.as_posix()
            if not parent.parts and child.name == SIDECAR_NAME:
                raise MaterializationError(
                    f"upstream Skill already contains {SIDECAR_NAME}: {relative}"
                )
            if child.name == ".git":
                excluded.add(relative)
                continue
            try:
                _safe_component(child.name, "upstream entry")
            except MaterializationSecurityError:
                excluded.add(relative)
                continue
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError as error:
                raise MaterializationError(f"cannot inspect Skill entry: {relative}") from error
            mode = stat.S_IMODE(metadata.st_mode)
            source = Path(child.path)
            if stat.S_ISDIR(metadata.st_mode):
                entries.append(_SourceEntry(source, relative, "directory", mode))
                visit(source, relative_path)
            elif stat.S_ISREG(metadata.st_mode):
                entries.append(_SourceEntry(source, relative, "file", mode))
            elif stat.S_ISLNK(metadata.st_mode):
                try:
                    link_target = os.readlink(source)
                except OSError as error:
                    raise MaterializationError(
                        f"cannot read Skill symlink: {relative}"
                    ) from error
                entries.append(
                    _SourceEntry(
                        source,
                        relative,
                        "symlink",
                        mode,
                        link_target=link_target,
                        copy_symlink=_is_safe_source_symlink(source, link_target, root),
                    )
                )
            else:
                entries.append(
                    _SourceEntry(
                        source,
                        relative,
                        _special_kind(metadata.st_mode),
                        mode,
                    )
                )

    visit(root, PurePosixPath())
    return sorted(entries, key=lambda entry: entry.relative), excluded


def _collect_materialized_entries(root: Path) -> List[_SourceEntry]:
    entries: List[_SourceEntry] = []

    def visit(directory: Path, parent: PurePosixPath) -> None:
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            raise MaterializationError(
                f"cannot enumerate materialized Skill directory: {directory}"
            ) from error
        for child in children:
            relative_path = parent / child.name
            relative = relative_path.as_posix()
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError as error:
                raise MaterializationError(
                    f"cannot inspect materialized Skill entry: {relative}"
                ) from error
            if not parent.parts and child.name == SIDECAR_NAME:
                if not stat.S_ISREG(metadata.st_mode):
                    raise MaterializationSecurityError(
                        "generated root sidecar must be a regular file"
                    )
                continue
            if child.name == ".git":
                raise MaterializationSecurityError(
                    f"materialized Skill contains Git internals: {relative}"
                )
            _safe_component(child.name, "materialized entry")
            mode = stat.S_IMODE(metadata.st_mode)
            source = Path(child.path)
            if stat.S_ISDIR(metadata.st_mode):
                entries.append(_SourceEntry(source, relative, "directory", mode))
                visit(source, relative_path)
            elif stat.S_ISREG(metadata.st_mode):
                entries.append(_SourceEntry(source, relative, "file", mode))
            elif stat.S_ISLNK(metadata.st_mode):
                try:
                    link_target = os.readlink(source)
                except OSError as error:
                    raise MaterializationSecurityError(
                        f"cannot read materialized symlink: {relative}"
                    ) from error
                if not _is_safe_source_symlink(source, link_target, root):
                    raise MaterializationSecurityError(
                        f"materialized Skill contains an unsafe symlink: {relative}"
                    )
                entries.append(
                    _SourceEntry(
                        source,
                        relative,
                        "symlink",
                        mode,
                        link_target=link_target,
                        copy_symlink=True,
                    )
                )
            else:
                raise MaterializationSecurityError(
                    f"materialized Skill contains a special entry: {relative}"
                )

    visit(root, PurePosixPath())
    return sorted(entries, key=lambda entry: entry.relative)


def _is_safe_source_symlink(path: Path, target: str, root: Path) -> bool:
    if (
        not target
        or os.path.isabs(target)
        or "\\" in target
        or "\x00" in target
        or "\n" in target
        or "\r" in target
    ):
        return False
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _special_kind(mode: int) -> str:
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode):
        return "character-device"
    if stat.S_ISBLK(mode):
        return "block-device"
    return "special"


def _copy_entries(
    entries: Sequence[_SourceEntry],
    target: Path,
    initial_exclusions: Set[str],
) -> List[str]:
    excluded = set(initial_exclusions)
    directories: List[Tuple[Path, int]] = []
    symlinks: List[Tuple[str, Path]] = []
    target_root = target.resolve()

    for entry in entries:
        destination = target / PurePosixPath(entry.relative)
        _require_destination_containment(destination, target_root)

        if entry.kind == "directory":
            destination.mkdir()
            directories.append((destination, entry.mode))
        elif entry.kind == "file":
            _copy_regular(entry, destination)
        elif entry.kind == "symlink":
            if entry.copy_symlink:
                os.symlink(entry.link_target, destination)
                symlinks.append((entry.relative, destination))
            else:
                excluded.add(entry.relative)
        else:
            excluded.add(entry.relative)

    for directory, mode in reversed(directories):
        os.chmod(directory, mode)

    changed = True
    while changed:
        changed = False
        for relative, link in symlinks:
            if relative in excluded or not link.is_symlink():
                continue
            try:
                resolved = link.resolve(strict=True)
                resolved.relative_to(target_root)
            except (OSError, RuntimeError, ValueError):
                link.unlink()
                excluded.add(relative)
                changed = True

    return sorted(excluded)


def _copy_regular(entry: _SourceEntry, destination: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(entry.source, flags)
    except OSError as error:
        raise MaterializationSecurityError(
            f"cannot safely open regular Skill file: {entry.relative}"
        ) from error

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MaterializationSecurityError(
                f"Skill file changed type while copying: {entry.relative}"
            )
        if stat.S_IMODE(metadata.st_mode) != entry.mode:
            raise MaterializationSecurityError(
                f"Skill file changed mode while copying: {entry.relative}"
            )
        copied = 0
        with os.fdopen(descriptor, "rb", closefd=False) as source, destination.open(
            "xb"
        ) as output:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                copied += len(chunk)
        if copied != metadata.st_size:
            raise MaterializationError(
                f"Skill file changed size while copying: {entry.relative}"
            )
        os.chmod(destination, stat.S_IMODE(metadata.st_mode))
    finally:
        os.close(descriptor)


def _hash_regular_entry(entry: _SourceEntry, digest: "hashlib._Hash") -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(entry.source, flags)
    except OSError as error:
        raise MaterializationSecurityError(
            f"cannot safely hash materialized file: {entry.relative}"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != entry.mode
        ):
            raise MaterializationSecurityError(
                f"materialized file changed while hashing: {entry.relative}"
            )
        _hash_length(digest, metadata.st_size)
        hashed = 0
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                hashed += len(chunk)
        if hashed != metadata.st_size:
            raise MaterializationError(
                f"materialized file changed size while hashing: {entry.relative}"
            )
    finally:
        os.close(descriptor)


def _hash_regular_file(path: Path) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise MaterializationSecurityError(f"cannot safely hash regular file: {path}") from error
    digest = hashlib.sha256()
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MaterializationSecurityError(f"expected regular file: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _hash_field(digest: "hashlib._Hash", value: bytes) -> None:
    _hash_length(digest, len(value))
    digest.update(value)


def _hash_length(digest: "hashlib._Hash", length: int) -> None:
    digest.update(length.to_bytes(8, byteorder="big", signed=False))


def _prepare_destination_root(root: Path) -> None:
    if _lexists(root):
        if root.is_symlink() or not root.is_dir():
            raise MaterializationSecurityError(
                "destination root must be a real directory"
            )
        return
    root.mkdir(parents=True)
    if root.is_symlink() or not root.is_dir():
        raise MaterializationSecurityError("destination root could not be secured")


def _make_safe_parent_directories(
    root: Path, relative_parent: Path, resolved_root: Path
) -> None:
    current = root
    for component in relative_parent.parts:
        _safe_component(component, "destination")
        current = current / component
        if _lexists(current):
            if current.is_symlink() or not current.is_dir():
                raise MaterializationSecurityError(
                    f"destination parent is not a real directory: {current}"
                )
        else:
            current.mkdir()
        _require_destination_containment(current, resolved_root)


def _require_destination_containment(path: Path, resolved_root: Path) -> None:
    try:
        path.resolve(strict=False).relative_to(resolved_root)
    except ValueError as error:
        raise MaterializationSecurityError(
            f"destination path escapes catalog root: {path}"
        ) from error


def _write_sidecar(path: Path, payload: object) -> None:
    serialized = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    with path.open("xb") as handle:
        handle.write(serialized)
    os.chmod(path, 0o644)


def _remove_reserved_target(path: Path) -> None:
    """Remove only the target directory exclusively reserved by this import."""

    if not _lexists(path):
        return
    if path.is_symlink() or not path.is_dir():
        raise MaterializationSecurityError(
            "reserved catalog target changed type before cleanup"
        )
    os.chmod(path, 0o700)
    for current, directory_names, _ in os.walk(
        path, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        os.chmod(current_path, 0o700)
        for name in directory_names:
            child = current_path / name
            if not child.is_symlink():
                os.chmod(child, 0o700)
    shutil.rmtree(path)


def _lexists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True

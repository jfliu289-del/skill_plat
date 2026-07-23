"""Read Skill frontmatter without changing upstream files."""

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .models import ParsedSkill


HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


class SkillParseError(ValueError):
    """Raised when a SKILL.md file lacks valid required metadata."""


def parse_skill(path: Path, source_root: Optional[Path] = None) -> ParsedSkill:
    """Parse one SKILL.md from a single, read-only byte snapshot."""

    source_path = _stable_source_path(path, source_root)
    raw_bytes = path.read_bytes()
    lines = raw_bytes.splitlines(keepends=True)
    if not lines or lines[0].rstrip(b"\r\n") != b"---":
        raise SkillParseError(f"missing opening frontmatter delimiter: {path}")

    closing_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.rstrip(b"\r\n") == b"---"
        ),
        None,
    )
    if closing_index is None:
        raise SkillParseError(f"missing closing frontmatter delimiter: {path}")

    metadata_text = b"".join(lines[1:closing_index]).decode(
        "utf-8", errors="replace"
    )
    try:
        metadata = yaml.safe_load(metadata_text)
    except yaml.YAMLError as error:
        raise SkillParseError(f"invalid YAML frontmatter: {path}") from error
    if not isinstance(metadata, dict):
        raise SkillParseError(f"frontmatter must be a mapping: {path}")

    name = _required_metadata_string(metadata, "name", path)
    description = _required_metadata_string(metadata, "description", path)
    text = raw_bytes.decode("utf-8", errors="replace")
    body = b"".join(lines[closing_index + 1 :]).decode(
        "utf-8", errors="replace"
    )

    return ParsedSkill(
        path=path,
        name=name,
        description=description,
        text=text,
        headings=tuple(match.group(1).strip() for match in HEADING.finditer(body)),
        source_path=source_path,
        raw_bytes=raw_bytes,
        skill_md_hash=hashlib.sha256(raw_bytes).hexdigest(),
    )


def _required_metadata_string(
    metadata: Dict[str, Any], name: str, path: Path
) -> str:
    value = metadata.get(name)
    if not isinstance(value, str) or not value.strip():
        raise SkillParseError(f"{name} must be a non-empty string: {path}")
    return value.strip()


def _stable_source_path(path: Path, source_root: Optional[Path]) -> str:
    if source_root is None:
        return "."
    try:
        relative_directory = path.resolve().parent.relative_to(source_root.resolve())
    except ValueError as error:
        raise SkillParseError(f"Skill path is outside source root: {path}") from error
    return relative_directory.as_posix()

"""Shared data models for catalog ingestion."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Category:
    id: str
    slug: str
    name: str
    name_zh: str
    keywords: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CategoryGroup:
    id: str
    slug: str
    name: str
    name_zh: str
    categories: Tuple[Category, ...]


@dataclass(frozen=True)
class Taxonomy:
    version: str
    groups: Dict[str, CategoryGroup]
    categories: Dict[str, Category]


@dataclass
class SourceSpec:
    id: str
    url: str
    mode: str
    ref: Optional[str] = None
    include_paths: List[str] = field(default_factory=lambda: ["."])
    exclude_paths: List[str] = field(default_factory=lambda: [".git"])
    default_categories: List[str] = field(default_factory=list)
    inventory_skill_count_hint: Optional[int] = None
    redistribution_review: bool = True
    registry_archive_mirror: bool = False
    index_source_id: Optional[str] = None

    @classmethod
    def for_test(cls, url: str) -> "SourceSpec":
        return cls(id="test/source", url=url, mode="direct")


@dataclass
class SkillRecord:
    source: SourceSpec
    repository: str
    commit: str
    source_path: str
    skill_root: Path
    name: str
    description: str = ""
    license: Optional[str] = None
    license_evidence: List[str] = field(default_factory=list)
    skill_md_hash: Optional[str] = None
    redistribution_review: bool = True
    registry_archive_mirror: Optional[bool] = None

    def __post_init__(self) -> None:
        if self.registry_archive_mirror is None:
            self.registry_archive_mirror = self.source.registry_archive_mirror


@dataclass
class Classification:
    primary_category: str
    secondary_categories: List[str] = field(default_factory=list)
    tasks: List[str] = field(default_factory=list)
    stages: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    audiences: List[str] = field(default_factory=list)
    risk_level: str = "R0"
    confidence: float = 0.0
    needs_review: bool = True
    reasons: List[str] = field(default_factory=list)


@dataclass
class ImportResult:
    record: SkillRecord
    relative_path: Path
    content_hash: str
    skill_md_hash: str
    excluded_paths: List[str] = field(default_factory=list)
    sidecar_path: Optional[Path] = None

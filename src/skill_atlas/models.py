"""Shared data models for catalog ingestion."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


@dataclass(frozen=True)
class Category:
    id: str
    slug: str
    name: str
    name_zh: str
    keywords: Tuple[str, ...] = ()
    exact_phrases: Tuple[str, ...] = ()
    tokens: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CategoryGroup:
    id: str
    slug: str
    name: str
    name_zh: str
    categories: Tuple[Category, ...]


@dataclass(frozen=True)
class ClassificationScoring:
    exact_phrase_weight: float
    token_weight: float
    source_default_weight: float
    weak_text_threshold: float
    strong_evidence_score: float
    secondary_score_ratio: float
    confidence_threshold: float
    ambiguity_threshold: float
    fallback_category: str


@dataclass(frozen=True)
class CrossTagRule:
    id: str
    exact_phrases: Tuple[str, ...] = ()
    tokens: Tuple[str, ...] = ()
    tasks: Tuple[str, ...] = ()
    stages: Tuple[str, ...] = ()
    artifacts: Tuple[str, ...] = ()
    domains: Tuple[str, ...] = ()
    audiences: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskCue:
    level: str
    exact_phrases: Tuple[str, ...] = ()
    tokens: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Taxonomy:
    version: str
    groups: Dict[str, CategoryGroup]
    categories: Dict[str, Category]
    tasks: Tuple[str, ...]
    stages: Tuple[str, ...]
    artifacts: Tuple[str, ...]
    domains: Tuple[str, ...]
    audiences: Tuple[str, ...]
    scoring: ClassificationScoring
    cross_tag_rules: Tuple[CrossTagRule, ...]
    risk_cues: Tuple[RiskCue, ...]


@dataclass(frozen=True)
class ParsedSkill:
    path: Path
    name: str
    description: str
    text: str
    headings: Tuple[str, ...]
    source_path: str
    raw_bytes: bytes = field(repr=False)
    skill_md_hash: str


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


@dataclass(frozen=True)
class RegistrySpec:
    id: str
    base_url: str
    index_source_id: str
    non_suspicious_only: bool
    request_timeout_seconds: float
    max_workers: int
    max_attempts: int
    max_download_bytes: int
    max_github_archive_bytes: int
    max_uncompressed_bytes: int
    max_github_uncompressed_bytes: int
    max_files: int
    max_compression_ratio: int


@dataclass(frozen=True, order=True)
class RegistryIndexEntry:
    index_path: str
    label: str
    url: str


@dataclass(frozen=True)
class RegistryClaim:
    claimed_slug: str
    claimed_owner: Optional[str]
    legacy_id: Optional[str]
    index_entries: Tuple[RegistryIndexEntry, ...]


@dataclass(frozen=True)
class RegistryDiscovery:
    claims: Tuple[RegistryClaim, ...]
    unresolved: Tuple[Dict[str, object], ...]


@dataclass(frozen=True, order=True)
class RegistryFile:
    """One immutable file declared by a ClawHub version manifest."""

    path: str
    size: int
    sha256: str
    content_type: Optional[str]


@dataclass(frozen=True)
class RegistryResolution:
    """An exact, currently public and clean ClawHub version."""

    claim_id: str
    claim: RegistryClaim
    owner_handle: str
    owner_id: Optional[str]
    slug: str
    version: str
    published_at: int
    canonical_url: str
    version_metadata_sha256: str
    files: Tuple[RegistryFile, ...]
    security: Dict[str, object]


@dataclass(frozen=True)
class ResolvedRegistryLockEntry:
    """Stable registry lock data, completed with artifact fields by Task 8."""

    claim_id: str
    status: str
    claim: RegistryClaim
    owner_handle: str
    owner_id: Optional[str]
    slug: str
    version: str
    published_at: int
    canonical_url: str
    version_metadata_sha256: str
    files: Tuple[RegistryFile, ...]
    security: Dict[str, object]
    artifact_kind: Optional[str] = None
    archive_sha256: Optional[str] = None
    registry_meta_sha256: Optional[str] = None
    github_handoff: Optional[Dict[str, object]] = None

    @classmethod
    def from_resolution(
        cls, resolution: "RegistryResolution"
    ) -> "ResolvedRegistryLockEntry":
        return cls(
            claim_id=resolution.claim_id,
            status="resolved",
            claim=resolution.claim,
            owner_handle=resolution.owner_handle,
            owner_id=resolution.owner_id,
            slug=resolution.slug,
            version=resolution.version,
            published_at=resolution.published_at,
            canonical_url=resolution.canonical_url,
            version_metadata_sha256=resolution.version_metadata_sha256,
            files=resolution.files,
            security=resolution.security,
        )


@dataclass(frozen=True)
class UnresolvedRegistryLockEntry:
    """Stable failure record for one immutable registry claim."""

    claim_id: str
    status: str
    claim: RegistryClaim
    failure: Dict[str, object]


RegistryLockEntry = Union[
    ResolvedRegistryLockEntry,
    UnresolvedRegistryLockEntry,
]


@dataclass(frozen=True)
class RegistryResolveResult:
    resolution: Optional[RegistryResolution]
    unresolved_lock_entry: Optional[UnresolvedRegistryLockEntry]
    failure: Optional[Dict[str, object]]
    blocking: bool


@dataclass(frozen=True)
class RegistryGateResult:
    allowed: bool
    failure: Optional[Dict[str, object]]
    blocking: bool
    security: Optional[Dict[str, object]] = None


@dataclass(frozen=True)
class RegistryResolutionResult:
    resolutions: Tuple[RegistryResolution, ...]
    unresolved_lock_entries: Tuple[UnresolvedRegistryLockEntry, ...]
    unresolved: Tuple[Dict[str, object], ...]
    blocking_failures: int
    stats: Dict[str, int]


@dataclass(frozen=True)
class GitSkillOrigin:
    repository: str
    commit: str
    source_path: str
    source_id: str
    default_categories: Tuple[str, ...]
    registry_archive_mirror: bool


@dataclass(frozen=True)
class RegistrySkillOrigin:
    provenance: "RegistryProvenance"
    source_id: str = "clawhub"


SkillOrigin = Union[GitSkillOrigin, RegistrySkillOrigin]


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
        if self.source.registry_archive_mirror:
            self.registry_archive_mirror = True
        elif self.registry_archive_mirror is None:
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


@dataclass(frozen=True, order=True)
class ValidationFailure:
    """One deterministic, machine-readable catalog validation finding."""

    code: str
    path: str
    message: str


@dataclass
class ValidationReport:
    """Complete structural validation result for a materialized catalog."""

    failures: List[ValidationFailure] = field(default_factory=list)
    skill_count: int = 0
    central_record_count: int = 0

    @property
    def valid(self) -> bool:
        return not self.failures

    def as_dict(self) -> Dict[str, object]:
        return {
            "central_record_count": self.central_record_count,
            "failure_count": len(self.failures),
            "failures": [
                {"code": item.code, "message": item.message, "path": item.path}
                for item in self.failures
            ],
            "skill_count": self.skill_count,
            "valid": self.valid,
        }


@dataclass(frozen=True)
class PathCollision:
    """Paths that collide after portable Unicode/case normalization."""

    normalized_path: str
    paths: List[str]

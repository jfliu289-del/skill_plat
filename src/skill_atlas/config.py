"""Load versioned taxonomy and source manifests."""

import json
import math
import re
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Dict, List

from .models import (
    Category,
    CategoryGroup,
    ClassificationScoring,
    CrossTagRule,
    RiskCue,
    RegistrySpec,
    SourceSpec,
    Taxonomy,
)


SOURCE_MODES = {"direct", "index", "archive", "reference"}
REGISTRY_FIELDS = {
    "schema_version",
    "id",
    "base_url",
    "index_source_id",
    "non_suspicious_only",
    "request_timeout_seconds",
    "max_workers",
    "max_attempts",
    "max_download_bytes",
    "max_github_archive_bytes",
    "max_uncompressed_bytes",
    "max_github_uncompressed_bytes",
    "max_files",
    "max_compression_ratio",
}
GITHUB_REPOSITORY_URL = re.compile(
    r"https://github[.]com/(?P<repository>[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+)"
)


def _read_object(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return data


def load_taxonomy(path: Path) -> Taxonomy:
    data = _read_object(path)
    category_data = data.get("categories", {})
    group_data = data.get("groups", {})
    if not isinstance(category_data, dict) or not isinstance(group_data, dict):
        raise ValueError("taxonomy categories and groups must be objects")

    categories = {}
    for category_id, item in category_data.items():
        if not isinstance(item, dict):
            raise ValueError(f"taxonomy category {category_id} must be an object")
        categories[category_id] = Category(
            id=category_id,
            slug=_required_string(item, "slug"),
            name=_required_string(item, "name"),
            name_zh=_required_string(item, "name_zh"),
            keywords=_unique_string_tuple(item, "keywords", required=False),
            exact_phrases=_unique_string_tuple(item, "exact_phrases"),
            tokens=_unique_string_tuple(item, "tokens"),
        )

    groups = {}
    routed = []
    for group_id, item in group_data.items():
        if not isinstance(item, dict):
            raise ValueError(f"taxonomy group {group_id} must be an object")
        category_ids = _string_list(item, "categories", [])
        try:
            group_categories = tuple(categories[category_id] for category_id in category_ids)
        except KeyError as error:
            raise ValueError(f"unknown category routed by group {group_id}: {error.args[0]}") from error
        routed.extend(category_ids)
        groups[group_id] = CategoryGroup(
            id=group_id,
            slug=_required_string(item, "slug"),
            name=_required_string(item, "name"),
            name_zh=_required_string(item, "name_zh"),
            categories=group_categories,
        )

    if len(routed) != len(set(routed)):
        raise ValueError("a category may be routed by only one group")
    if set(routed) != set(categories):
        raise ValueError("every category must be routed by exactly one group")

    vocabulary_data = data.get("controlled_vocabularies")
    if not isinstance(vocabulary_data, dict):
        raise ValueError("controlled_vocabularies must be an object")
    vocabularies = {
        name: _unique_string_tuple(vocabulary_data, name)
        for name in ("tasks", "stages", "artifacts", "domains", "audiences")
    }

    scoring_data = data.get("scoring")
    if not isinstance(scoring_data, dict):
        raise ValueError("scoring must be an object")
    scoring = ClassificationScoring(
        exact_phrase_weight=_positive_number(scoring_data, "exact_phrase_weight"),
        token_weight=_positive_number(scoring_data, "token_weight"),
        source_default_weight=_positive_number(scoring_data, "source_default_weight"),
        weak_text_threshold=_positive_number(scoring_data, "weak_text_threshold"),
        strong_evidence_score=_positive_number(scoring_data, "strong_evidence_score"),
        secondary_score_ratio=_unit_number(scoring_data, "secondary_score_ratio"),
        confidence_threshold=_unit_number(scoring_data, "confidence_threshold"),
        ambiguity_threshold=_unit_number(scoring_data, "ambiguity_threshold"),
        fallback_category=_required_string(scoring_data, "fallback_category"),
    )
    if scoring.fallback_category not in categories:
        raise ValueError("scoring.fallback_category must name a taxonomy category")

    cross_tag_rules = _load_cross_tag_rules(data, vocabularies)
    risk_cues = _load_risk_cues(data)

    return Taxonomy(
        version=data["taxonomy_version"],
        groups=groups,
        categories=categories,
        scoring=scoring,
        cross_tag_rules=cross_tag_rules,
        risk_cues=risk_cues,
        **vocabularies,
    )


def _load_cross_tag_rules(
    data: Dict[str, Any], vocabularies: Dict[str, tuple]
) -> tuple:
    raw_rules = data.get("cross_tag_rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError("cross_tag_rules must be a non-empty list")

    rules = []
    for item in raw_rules:
        if not isinstance(item, dict):
            raise ValueError("each cross-tag rule must be an object")
        exact_phrases = _unique_string_tuple(item, "exact_phrases", required=False)
        tokens = _unique_string_tuple(item, "tokens", required=False)
        if not exact_phrases and not tokens:
            raise ValueError("each cross-tag rule must define phrases or tokens")
        tags = {
            name: _unique_string_tuple(item, name, required=False)
            for name in ("tasks", "stages", "artifacts", "domains", "audiences")
        }
        for name, values in tags.items():
            unknown = set(values) - set(vocabularies[name])
            if unknown:
                raise ValueError(
                    f"cross-tag rule contains unknown {name}: {sorted(unknown)}"
                )
        rules.append(
            CrossTagRule(
                id=_required_string(item, "id"),
                exact_phrases=exact_phrases,
                tokens=tokens,
                **tags,
            )
        )
    ids = [rule.id for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("cross-tag rule ids must be unique")
    return tuple(rules)


def _load_risk_cues(data: Dict[str, Any]) -> tuple:
    raw_cues = data.get("risk_cues")
    if not isinstance(raw_cues, list) or not raw_cues:
        raise ValueError("risk_cues must be a non-empty list")

    cues = []
    for item in raw_cues:
        if not isinstance(item, dict):
            raise ValueError("each risk cue must be an object")
        level = _required_string(item, "level")
        if level not in {"R1", "R2", "R3", "R4"}:
            raise ValueError(f"unsupported risk level: {level}")
        exact_phrases = _unique_string_tuple(item, "exact_phrases", required=False)
        tokens = _unique_string_tuple(item, "tokens", required=False)
        if not exact_phrases and not tokens:
            raise ValueError("each risk cue must define phrases or tokens")
        cues.append(
            RiskCue(level=level, exact_phrases=exact_phrases, tokens=tokens)
        )
    return tuple(cues)


def load_sources(path: Path) -> List[SourceSpec]:
    data = _read_object(path)
    raw_sources = data.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("sources must be a list")

    source_defaults = data.get("source_defaults", {})
    if not isinstance(source_defaults, dict):
        raise ValueError("source_defaults must be an object")
    default_archive_mirror = source_defaults.get("registry_archive_mirror", False)
    if type(default_archive_mirror) is not bool:
        raise ValueError("source_defaults.registry_archive_mirror must be a boolean")

    sources = []
    for item in raw_sources:
        if not isinstance(item, dict):
            raise ValueError("each source must be an object")

        source_id = _required_string(item, "id")
        url = _required_string(item, "url")
        mode = _required_string(item, "mode")
        ref = _optional_string(item, "ref")
        index_source_id = _optional_string(item, "index_source_id")
        include_paths = _source_path_list(
            item, "include_paths", ["."], allow_current=True
        )
        exclude_paths = _source_path_list(
            item, "exclude_paths", [".git"], allow_current=False
        )
        default_categories = _string_list(item, "default_categories", [])

        inventory_hint = item.get("inventory_skill_count_hint")
        if inventory_hint is not None and (
            type(inventory_hint) is not int or inventory_hint < 0
        ):
            raise ValueError("inventory_skill_count_hint must be a non-negative integer or null")

        redistribution_review = item.get("redistribution_review", True)
        if type(redistribution_review) is not bool:
            raise ValueError("redistribution_review must be a boolean")

        registry_archive_mirror = item.get(
            "registry_archive_mirror", default_archive_mirror
        )
        if type(registry_archive_mirror) is not bool:
            raise ValueError("registry_archive_mirror must be a boolean")

        sources.append(
            SourceSpec(
                id=source_id,
                url=url,
                mode=mode,
                ref=ref,
                include_paths=include_paths,
                exclude_paths=exclude_paths,
                default_categories=default_categories,
                inventory_skill_count_hint=inventory_hint,
                redistribution_review=redistribution_review,
                registry_archive_mirror=registry_archive_mirror,
                index_source_id=index_source_id,
            )
        )

    ids = [source.id for source in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("source ids must be unique")
    for source in sources:
        match = GITHUB_REPOSITORY_URL.fullmatch(source.url)
        if match is None or match.group("repository") != source.id:
            raise ValueError(f"source {source.id} is not an HTTPS GitHub repository")
        if source.mode not in SOURCE_MODES:
            raise ValueError(f"source {source.id} has unsupported mode {source.mode}")
        if source.registry_archive_mirror and source.mode != "archive":
            raise ValueError("registry archive mirrors must use archive mode")
    return sources


def load_registry(path: Path) -> RegistrySpec:
    data = _read_object(path)
    actual_fields = set(data)
    if actual_fields != REGISTRY_FIELDS:
        missing = sorted(REGISTRY_FIELDS - actual_fields)
        unknown = sorted(actual_fields - REGISTRY_FIELDS)
        raise ValueError(
            f"registry fields must match exactly; missing={missing}, unknown={unknown}"
        )
    if data["schema_version"] != "1.0":
        raise ValueError("registry schema_version must be 1.0")
    if data["id"] != "clawhub":
        raise ValueError("registry id must be clawhub")
    if data["base_url"] != "https://clawhub.ai":
        raise ValueError("registry base_url must be the official ClawHub URL")
    index_source_id = _required_string(data, "index_source_id")
    if data["non_suspicious_only"] is not True:
        raise ValueError("registry must enable non_suspicious_only")

    return RegistrySpec(
        id="clawhub",
        base_url="https://clawhub.ai",
        index_source_id=index_source_id,
        non_suspicious_only=True,
        request_timeout_seconds=_positive_finite_number(
            data, "request_timeout_seconds"
        ),
        max_workers=_bounded_positive_integer(data, "max_workers", 64),
        max_attempts=_bounded_positive_integer(data, "max_attempts", 10),
        max_download_bytes=_positive_integer(data, "max_download_bytes"),
        max_github_archive_bytes=_positive_integer(
            data, "max_github_archive_bytes"
        ),
        max_uncompressed_bytes=_positive_integer(
            data, "max_uncompressed_bytes"
        ),
        max_github_uncompressed_bytes=_positive_integer(
            data, "max_github_uncompressed_bytes"
        ),
        max_files=_positive_integer(data, "max_files"),
        max_compression_ratio=_positive_integer(
            data, "max_compression_ratio"
        ),
    )


def _required_string(item: Dict[str, Any], name: str) -> str:
    value = item.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_string(item: Dict[str, Any], name: str) -> Any:
    value = item.get(name)
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f"{name} must be a non-empty string or null")
    return value


def _string_list(item: Dict[str, Any], name: str, default: List[str]) -> List[str]:
    value = item.get(name, default)
    if not isinstance(value, list) or any(
        not isinstance(entry, str) or not entry for entry in value
    ):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return list(value)


def _source_path_list(
    item: Dict[str, Any],
    name: str,
    default: List[str],
    allow_current: bool,
) -> List[str]:
    values = _string_list(item, name, default)
    for value in values:
        if allow_current and value == ".":
            continue
        path = PurePosixPath(value)
        if (
            value != value.strip()
            or "\\" in value
            or "\x00" in value
            or "\n" in value
            or "\r" in value
            or path.is_absolute()
            or path.as_posix() != value
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError(f"{name} contains an unsafe noncanonical path: {value!r}")
    return values


def _unique_string_tuple(
    item: Dict[str, Any], name: str, required: bool = True
) -> tuple:
    value = item.get(name)
    if value is None and not required:
        return ()
    if not isinstance(value, list) or any(
        not isinstance(entry, str) or not entry.strip() for entry in value
    ):
        raise ValueError(f"{name} must be a list of non-empty strings")
    normalized = tuple(entry.strip().lower() for entry in value)
    if required and not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} entries must be unique")
    return normalized


def _positive_number(item: Dict[str, Any], name: str) -> float:
    value = item.get(name)
    if type(value) not in (int, float) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return float(value)


def _positive_finite_number(item: Dict[str, Any], name: str) -> float:
    value = item.get(name)
    if type(value) not in (int, float) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    try:
        numeric_value = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must be a positive finite number") from error
    if not math.isfinite(numeric_value):
        raise ValueError(f"{name} must be a positive finite number")
    return numeric_value


def _positive_integer(item: Dict[str, Any], name: str) -> int:
    value = item.get(name)
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _bounded_positive_integer(
    item: Dict[str, Any], name: str, maximum: int
) -> int:
    value = _positive_integer(item, name)
    if value > maximum:
        raise ValueError(f"{name} must be no greater than {maximum}")
    return value


def _unit_number(item: Dict[str, Any], name: str) -> float:
    value = _positive_number(item, name)
    if value > 1:
        raise ValueError(f"{name} must be no greater than 1")
    return value

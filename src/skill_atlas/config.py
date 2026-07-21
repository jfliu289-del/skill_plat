"""Load versioned taxonomy and source manifests."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from .models import Category, CategoryGroup, SourceSpec, Taxonomy


SOURCE_MODES = {"direct", "index", "archive", "reference"}
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

    categories = {
        category_id: Category(
            id=category_id,
            slug=item["slug"],
            name=item["name"],
            name_zh=item["name_zh"],
            keywords=tuple(item.get("keywords", [])),
        )
        for category_id, item in category_data.items()
    }

    groups = {}
    routed = []
    for group_id, item in group_data.items():
        category_ids = item["categories"]
        try:
            group_categories = tuple(categories[category_id] for category_id in category_ids)
        except KeyError as error:
            raise ValueError(f"unknown category routed by group {group_id}: {error.args[0]}") from error
        routed.extend(category_ids)
        groups[group_id] = CategoryGroup(
            id=group_id,
            slug=item["slug"],
            name=item["name"],
            name_zh=item["name_zh"],
            categories=group_categories,
        )

    if len(routed) != len(set(routed)):
        raise ValueError("a category may be routed by only one group")
    if set(routed) != set(categories):
        raise ValueError("every category must be routed by exactly one group")

    return Taxonomy(
        version=data["taxonomy_version"],
        groups=groups,
        categories=categories,
    )


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
        include_paths = _string_list(item, "include_paths", ["."])
        exclude_paths = _string_list(item, "exclude_paths", [".git"])
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

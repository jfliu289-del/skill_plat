"""Load versioned taxonomy and source manifests."""

import json
from pathlib import Path
from typing import Any, Dict, List

from .models import Category, CategoryGroup, SourceSpec, Taxonomy


SOURCE_MODES = {"direct", "index", "archive", "reference"}


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

    sources = [
        SourceSpec(
            id=item["id"],
            url=item["url"],
            mode=item["mode"],
            ref=item.get("ref"),
            include_paths=list(item.get("include_paths", ["."])),
            exclude_paths=list(item.get("exclude_paths", [".git"])),
            default_categories=list(item.get("default_categories", [])),
            inventory_skill_count_hint=item.get("inventory_skill_count_hint"),
            redistribution_review=item.get("redistribution_review", True),
            index_source_id=item.get("index_source_id"),
        )
        for item in raw_sources
    ]

    ids = [source.id for source in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("source ids must be unique")
    for source in sources:
        if not source.url.startswith("https://github.com/"):
            raise ValueError(f"source {source.id} is not an HTTPS GitHub repository")
        if source.mode not in SOURCE_MODES:
            raise ValueError(f"source {source.id} has unsupported mode {source.mode}")
    return sources

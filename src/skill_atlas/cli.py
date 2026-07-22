"""Command-line interface for deterministic Skill Atlas ingestion."""

import argparse
import json
from pathlib import Path
import sys
from typing import Callable, List, Optional, Sequence

from .config import load_sources, load_taxonomy
from .git_sources import sync_source
from .models import SourceSpec
from .safe_io import atomic_write_text
from .pipeline import (
    build_catalog,
    read_summary,
    sync_source_graph,
    write_sync_reports,
)
from .validate import validate_catalog


SourceLoader = Callable[[Path], List[SourceSpec]]


def main(
    argv: Optional[Sequence[str]] = None,
    source_loader: SourceLoader = load_sources,
    synchronizer=sync_source,
) -> int:
    """Run one CLI command and return its process exit status."""

    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        root = arguments.root.resolve()
        if arguments.command == "report":
            summary = read_summary(root)
            _print_json(summary)
            return 0

        sources_path, taxonomy_path = _config_paths(
            arguments.config, arguments.taxonomy
        )
        taxonomy = load_taxonomy(taxonomy_path)
        if arguments.command == "validate":
            report = validate_catalog(root, taxonomy)
            payload = report.as_dict()
            if arguments.report is not None:
                report_path = (
                    root / "reports" / "validation.json"
                    if arguments.report == Path("__USE_ROOT_REPORT__")
                    else arguments.report
                )
                _write_json_atomically(report_path, payload)
            _print_json(payload)
            if report.failures:
                print(
                    f"validation failed with {len(report.failures)} finding(s)",
                    file=sys.stderr,
                )
                return 1
            return 0

        sources = source_loader(sources_path)
        if arguments.command == "sync":
            outcome = sync_source_graph(
                sources,
                arguments.cache,
                locked_path=_locked_path(arguments.locked, root),
                synchronizer=synchronizer,
            )
            write_sync_reports(root, outcome)
            _print_json(
                {
                    "configured_direct_failures": outcome.configured_direct_failures,
                    "resolved": sum(
                        item.get("status") == "resolved"
                        for item in outcome.lock_entries
                    ),
                    "unresolved": len(outcome.unresolved),
                }
            )
            if outcome.configured_direct_failures:
                print("one or more configured direct sources are inaccessible", file=sys.stderr)
                return 1
            return 0

        locked_path = _locked_path(arguments.locked, root)
        if arguments.command == "build" and locked_path is None:
            locked_path = root / "reports" / "sources.lock.json"
            if not locked_path.is_file():
                print(
                    "build requires --locked or an existing reports/sources.lock.json",
                    file=sys.stderr,
                )
                return 2
        outcome = sync_source_graph(
            sources,
            arguments.cache,
            locked_path=locked_path,
            synchronizer=synchronizer,
        )
        built = build_catalog(root, taxonomy, outcome)
        _print_json(built.summary)
        failed = (
            not built.published
            or outcome.configured_direct_failures > 0
            or built.blocking_import_failures > 0
            or bool(built.validation.get("failures"))
        )
        if not built.published:
            print(built.error or "catalog was not published", file=sys.stderr)
        if outcome.configured_direct_failures:
            print("one or more configured direct sources are inaccessible", file=sys.stderr)
        if built.blocking_import_failures:
            print(
                f"{built.blocking_import_failures} blocking Skill import failure(s) were recorded",
                file=sys.stderr,
            )
        return 1 if failed else 0
    except (OSError, UnicodeError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"skill-atlas: {error}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m skill_atlas")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("sync", "build", "validate", "report", "all"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--config", type=Path, default=Path("config"))
        subparser.add_argument(
            "--taxonomy", type=Path, default=None
        )
        subparser.add_argument("--root", type=Path, default=Path("."))
        subparser.add_argument(
            "--cache", type=Path, default=Path(".cache/upstreams")
        )
        subparser.add_argument(
            "--locked",
            type=Path,
            nargs="?",
            const=Path("__USE_ROOT_LOCK__"),
            help="rebuild only the immutable commits in this sources.lock.json",
        )
        if command == "validate":
            subparser.add_argument(
                "--report",
                type=Path,
                nargs="?",
                const=Path("__USE_ROOT_REPORT__"),
                help="write the stable validation JSON to this path",
            )
        if command == "report":
            subparser.add_argument(
                "--summary", action="store_true", help="print exact summary counts"
            )
    return parser


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _write_json_atomically(path: Path, payload: object) -> None:
    atomic_write_text(
        Path(path),
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _locked_path(value: Optional[Path], root: Path) -> Optional[Path]:
    if value == Path("__USE_ROOT_LOCK__"):
        return root / "reports" / "sources.lock.json"
    return value


def _config_paths(
    config: Path, explicit_taxonomy: Optional[Path]
) -> tuple:
    config = Path(config)
    if config.is_dir():
        sources = config / "sources.json"
        default_taxonomy = config / "taxonomy.json"
    else:
        sources = config
        default_taxonomy = config.parent / "taxonomy.json"
    return sources, explicit_taxonomy or default_taxonomy

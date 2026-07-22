import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import skill_atlas.pipeline as pipeline_module
from skill_atlas.cli import main
from skill_atlas.git_sources import ResolvedSource, sync_source
from skill_atlas.materialize import hash_materialized_skill
from skill_atlas.models import SourceSpec


ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(repository: Path, message: str) -> str:
    _git("add", ".", cwd=repository)
    _git(
        "-c", "user.name=Skill Atlas Tests",
        "-c", "user.email=skill-atlas@example.invalid",
        "commit", "-m", message, cwd=repository,
    )
    return _git("rev-parse", "HEAD", cwd=repository)


def _initialize_repository(path: Path) -> None:
    path.mkdir()
    _git("init", cwd=path)


def _make_skill(repository: Path, relative: str, name: str) -> None:
    skill = repository / relative
    (skill / "assets").mkdir(parents=True)
    (skill / "scripts").mkdir()
    (skill / ".hidden").write_bytes(b"hidden\x00resource")
    (skill / "assets" / "template.bin").write_bytes(b"\x00\x01binary")
    (skill / "scripts" / "run.py").write_text("print('never executed')\n")
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Review and test code.\n---\n# {name}\n",
        encoding="utf-8",
    )


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.tempdir = Path(self.temporary_directory.name)
        self.output = self.tempdir / "catalog"
        self.cache = self.tempdir / "cache"
        self.config = self.tempdir / "sources.json"
        self.config.write_text("{}\n")

        self.direct = self.tempdir / "direct"
        _initialize_repository(self.direct)
        _make_skill(self.direct, "skills/one", "one")
        _make_skill(self.direct, "skills/two", "two")
        _make_skill(self.direct, "packs/three", "three")
        self.initial_commit = _commit(self.direct, "three complete Skills")

        self.index = self.tempdir / "index"
        _initialize_repository(self.index)
        _make_skill(self.index, "fixtures/must-not-import", "index-fixture")
        (self.index / "README.md").write_text("Index only.\n")
        _commit(self.index, "index")

        self.reference = self.tempdir / "reference"
        _initialize_repository(self.reference)
        _make_skill(self.reference, "tests/malicious-fixture", "reference-fixture")
        _commit(self.reference, "reference fixtures")

        self.sources = [
            SourceSpec(
                id="test/direct", url="https://github.com/test/direct", mode="direct",
                redistribution_review=True,
            ),
            SourceSpec(
                id="test/index", url="https://github.com/test/index", mode="index",
                redistribution_review=True,
            ),
            SourceSpec(
                id="test/reference", url="https://github.com/test/reference", mode="reference",
                redistribution_review=True,
            ),
        ]
        self.local_repositories = {
            "test/direct": self.direct,
            "test/index": self.index,
            "test/reference": self.reference,
        }

    def tearDown(self):
        self.temporary_directory.cleanup()

    def run_cli(self, command: str, *extra: str, sources=None, synchronizer=None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        arguments = [
            command,
            "--config", str(self.config),
            "--taxonomy", str(ROOT / "config/taxonomy.json"),
            "--root", str(self.output),
            "--cache", str(self.cache),
            *extra,
        ]
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                arguments,
                source_loader=lambda _: list(self.sources if sources is None else sources),
                synchronizer=synchronizer or self.local_synchronizer,
            )
        return code, stdout.getvalue(), stderr.getvalue()

    def local_synchronizer(self, spec, cache_root, locked_commit=None):
        local = self.local_repositories.get(
            spec.id, self.tempdir / "missing-repositories" / spec.id
        )
        local_spec = SourceSpec(
            id=spec.id,
            url=local.as_uri(),
            mode=spec.mode,
            ref=spec.ref,
            include_paths=list(spec.include_paths),
            exclude_paths=list(spec.exclude_paths),
            default_categories=list(spec.default_categories),
            redistribution_review=spec.redistribution_review,
            registry_archive_mirror=spec.registry_archive_mirror,
            index_source_id=spec.index_source_id,
        )
        resolved = sync_source(local_spec, cache_root, locked_commit=locked_commit)
        return ResolvedSource(source=spec, checkout=resolved.checkout, commit=resolved.commit)

    def test_all_builds_catalog_lock_and_reports_atomically(self):
        code, stdout, stderr = self.run_cli("all")

        self.assertEqual(0, code, stderr)
        self.assertEqual("", stderr)
        self.assertEqual(3, len(list((self.output / "skills").rglob("SKILL.md"))))
        self.assertEqual(3, len(list((self.output / "skills").rglob("skill-atlas.json"))))
        copied_root = next(
            path.parent for path in (self.output / "skills").rglob("SKILL.md")
            if path.parent.name == "one"
        )
        self.assertEqual(b"\x00\x01binary", (copied_root / "assets/template.bin").read_bytes())
        self.assertEqual(b"hidden\x00resource", (copied_root / ".hidden").read_bytes())
        self.assertTrue((copied_root / "scripts/run.py").is_file())
        self.assertFalse(any("index-fixture" in path.read_text(errors="ignore") for path in (self.output / "skills").rglob("SKILL.md")))
        self.assertFalse(any("reference-fixture" in path.read_text(errors="ignore") for path in (self.output / "skills").rglob("SKILL.md")))

        reports = self.output / "reports"
        for name in (
            "sources.lock.json", "catalog.jsonl", "duplicates.json",
            "unresolved.json", "validation.json", "summary.json",
        ):
            self.assertTrue((reports / name).is_file(), name)
        validation = json.loads((reports / "validation.json").read_text())
        self.assertEqual([], validation["failures"])
        lock = json.loads((reports / "sources.lock.json").read_text())
        self.assertFalse(any("checkout" in entry for entry in lock["sources"]))
        self.assertIn('"imported": 3', stdout)

    def test_locked_all_rebuilds_the_pinned_commit(self):
        code, _, stderr = self.run_cli("all")
        self.assertEqual(0, code, stderr)
        lock_path = self.output / "reports/sources.lock.json"
        reports_before = {
            path.name: path.read_bytes()
            for path in (self.output / "reports").iterdir()
            if path.is_file()
        }
        _make_skill(self.direct, "skills/four", "four")
        advanced = _commit(self.direct, "advance source")
        self.assertNotEqual(self.initial_commit, advanced)
        self.sources[0].include_paths = ["skills/one"]

        code, _, stderr = self.run_cli("all", "--locked")

        self.assertEqual(0, code, stderr)
        self.assertEqual(3, len(list((self.output / "skills").rglob("SKILL.md"))))
        lock = json.loads((self.output / "reports/sources.lock.json").read_text())
        direct = next(item for item in lock["sources"] if item["id"] == "test/direct")
        self.assertEqual(self.initial_commit, direct["commit"])
        self.assertEqual(
            reports_before,
            {
                path.name: path.read_bytes()
                for path in (self.output / "reports").iterdir()
                if path.is_file()
            },
        )

    def test_direct_source_failure_isolated_but_all_returns_nonzero(self):
        missing = SourceSpec(
            id="test/missing",
            url="https://github.com/test/missing",
            mode="direct",
        )

        code, _, stderr = self.run_cli("all", sources=[self.sources[0], missing])

        self.assertEqual(1, code)
        self.assertIn("configured direct source", stderr)
        self.assertEqual(3, len(list((self.output / "skills").rglob("SKILL.md"))))
        unresolved = json.loads((self.output / "reports/unresolved.json").read_text())
        self.assertTrue(any(item["source_id"] == "test/missing" for item in unresolved["unresolved"]))

    def test_locked_rebuild_preserves_nonresolved_source_reports_byte_for_byte(self):
        missing_reference = SourceSpec(
            id="test/missing-reference",
            url="https://github.com/test/missing-reference",
            mode="reference",
        )
        selected_sources = [self.sources[0], missing_reference]

        code, _, stderr = self.run_cli("all", sources=selected_sources)

        self.assertEqual(0, code, stderr)
        report_names = (
            "sources.lock.json",
            "unresolved.json",
            "summary.json",
        )
        before = {
            name: (self.output / "reports" / name).read_bytes()
            for name in report_names
        }
        first_lock = json.loads(before["sources.lock.json"])
        missing_entry = next(
            item
            for item in first_lock["sources"]
            if item["id"] == missing_reference.id
        )
        self.assertEqual("inaccessible", missing_entry["status"])
        self.assertEqual("inaccessible", missing_entry["failure"]["reason"])
        self.assertEqual(
            missing_reference.id, missing_entry["failure"]["source_id"]
        )

        locked_sync_calls = []

        def locked_synchronizer(spec, cache_root, locked_commit=None):
            locked_sync_calls.append(spec.id)
            return self.local_synchronizer(
                spec, cache_root, locked_commit=locked_commit
            )

        code, _, stderr = self.run_cli(
            "all",
            "--locked",
            sources=selected_sources,
            synchronizer=locked_synchronizer,
        )

        self.assertEqual(0, code, stderr)
        self.assertEqual(
            before,
            {
                name: (self.output / "reports" / name).read_bytes()
                for name in report_names
            },
        )
        self.assertNotIn(missing_reference.id, locked_sync_calls)

    def test_collision_fails_before_publish_and_preserves_old_catalog_bytes(self):
        code, _, stderr = self.run_cli("all")
        self.assertEqual(0, code, stderr)
        old_catalog = (self.output / "reports/catalog.jsonl").read_bytes()
        old_skills = sorted(
            path.relative_to(self.output).as_posix()
            for path in (self.output / "skills").rglob("SKILL.md")
        )
        collision_repo = self.tempdir / "collision-source"
        _initialize_repository(collision_repo)
        _make_skill(collision_repo, "skills/one", "one-copy")
        collision_commit = _commit(collision_repo, "portable collision")
        collision_source = SourceSpec(
            id="Test/direct",
            url="https://github.com/Test/direct",
            mode="direct",
        )

        def raw_synchronizer(spec, _cache_root, locked_commit=None):
            if spec.id == "test/direct":
                checkout = self.direct
                commit = _git("rev-parse", "HEAD", cwd=self.direct)
            else:
                checkout = collision_repo
                commit = collision_commit
            if locked_commit is not None and locked_commit != commit:
                raise ValueError("fixture lock mismatch")
            return ResolvedSource(source=spec, checkout=checkout, commit=commit)

        code, _, stderr = self.run_cli(
            "all",
            sources=[self.sources[0], collision_source],
            synchronizer=raw_synchronizer,
        )

        self.assertEqual(1, code)
        self.assertIn("path collision", stderr.lower())
        self.assertEqual(old_catalog, (self.output / "reports/catalog.jsonl").read_bytes())
        self.assertEqual(
            old_skills,
            sorted(
                path.relative_to(self.output).as_posix()
                for path in (self.output / "skills").rglob("SKILL.md")
            ),
        )

    def test_report_summary_is_stable_and_validate_can_write_explicit_report(self):
        code, _, stderr = self.run_cli("all")
        self.assertEqual(0, code, stderr)

        first = self.run_cli("report", "--summary")
        second = self.run_cli("report", "--summary")
        self.assertEqual(first, second)
        summary = json.loads(first[1])
        self.assertEqual(
            {
                "duplicate", "imported", "inaccessible", "low_confidence",
                "parse_failure", "unknown_license", "unsafe_symlink",
            },
            set(summary),
        )
        explicit = self.tempdir / "validation-output.json"
        code, _, stderr = self.run_cli("validate", "--report", str(explicit))
        self.assertEqual(0, code, stderr)
        self.assertTrue(json.loads(explicit.read_text())["valid"])

        completed = subprocess.run(
            [
                "python3", "-m", "skill_atlas", "validate",
                "--taxonomy", str(ROOT / "config/taxonomy.json"),
                "--root", str(self.output),
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["valid"])

    def test_sync_then_build_uses_the_written_lock(self):
        code, _, stderr = self.run_cli("sync")
        self.assertEqual(0, code, stderr)
        self.assertTrue((self.output / "reports/sources.lock.json").is_file())

        code, _, stderr = self.run_cli("build")

        self.assertEqual(0, code, stderr)
        self.assertEqual(3, len(list((self.output / "skills").rglob("SKILL.md"))))

    def test_config_directory_resolves_sources_and_default_taxonomy_together(self):
        config_directory = self.tempdir / "catalog-config"
        config_directory.mkdir()
        (config_directory / "sources.json").write_text("{}\n")
        shutil.copyfile(
            ROOT / "config/taxonomy.json", config_directory / "taxonomy.json"
        )
        loaded_paths = []
        output = self.tempdir / "directory-config-output"
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                [
                    "all",
                    "--config", str(config_directory),
                    "--root", str(output),
                    "--cache", str(self.tempdir / "directory-config-cache"),
                ],
                source_loader=lambda path: loaded_paths.append(path) or [self.sources[0]],
                synchronizer=self.local_synchronizer,
            )

        self.assertEqual(0, code, stderr.getvalue())
        self.assertEqual([config_directory / "sources.json"], loaded_paths)
        self.assertEqual(3, len(list((output / "skills").rglob("SKILL.md"))))

    def test_invalid_lock_commit_is_rejected_before_synchronization(self):
        invalid_lock = self.tempdir / "invalid-lock.json"
        invalid_lock.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "sources": [
                        {
                            "id": "test/direct",
                            "url": "https://github.com/test/direct",
                            "status": "resolved",
                            "commit": "HEAD",
                        }
                    ]
                }
            )
        )
        called = []

        def must_not_sync(*args, **kwargs):
            called.append((args, kwargs))
            raise AssertionError("invalid lock must fail first")

        code, _, stderr = self.run_cli(
            "all", "--locked", str(invalid_lock), synchronizer=must_not_sync
        )

        self.assertEqual(2, code)
        self.assertIn("commit", stderr)
        self.assertEqual([], called)

    def test_locked_build_rejects_unconsumed_source_entries(self):
        code, _, stderr = self.run_cli("all")
        self.assertEqual(0, code, stderr)
        old_catalog = (self.output / "reports/catalog.jsonl").read_bytes()
        payload = json.loads((self.output / "reports/sources.lock.json").read_text())
        extra = dict(payload["sources"][0])
        extra.update(
            {
                "id": "ghost/repository",
                "url": "https://github.com/ghost/repository",
            }
        )
        payload["sources"].append(extra)
        locked = self.tempdir / "extra-source.lock.json"
        locked.write_text(json.dumps(payload), encoding="utf-8")

        code, _, stderr = self.run_cli("all", "--locked", str(locked))

        self.assertEqual(2, code)
        self.assertIn("lock/config mismatch", stderr)
        self.assertEqual(old_catalog, (self.output / "reports/catalog.jsonl").read_bytes())

    def test_locked_build_rejects_role_mismatch_and_unsafe_paths(self):
        code, _, stderr = self.run_cli("all")
        self.assertEqual(0, code, stderr)
        payload = json.loads((self.output / "reports/sources.lock.json").read_text())
        direct = next(item for item in payload["sources"] if item["id"] == "test/direct")

        direct["mode"] = "reference"
        role_lock = self.tempdir / "role.lock.json"
        role_lock.write_text(json.dumps(payload), encoding="utf-8")
        code, _, stderr = self.run_cli("all", "--locked", str(role_lock))
        self.assertEqual(2, code)
        self.assertIn("mode", stderr)

        direct["mode"] = "direct"
        direct["include_paths"] = ["../outside"]
        path_lock = self.tempdir / "path.lock.json"
        path_lock.write_text(json.dumps(payload), encoding="utf-8")
        code, _, stderr = self.run_cli("all", "--locked", str(path_lock))
        self.assertEqual(2, code)
        self.assertIn("path", stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "requires symlink support")
    def test_sync_and_report_writers_never_follow_fixed_temp_or_target_symlinks(self):
        reports = self.output / "reports"
        reports.mkdir(parents=True)
        external = self.tempdir / "external.json"
        original = b'{"outside": true}\n'
        external.write_bytes(original)
        (reports / ".sources.lock.json.tmp").symlink_to(external)

        code, _, stderr = self.run_cli("sync")

        self.assertEqual(0, code, stderr)
        self.assertEqual(original, external.read_bytes())
        self.assertTrue((reports / ".sources.lock.json.tmp").is_symlink())

        (reports / "sources.lock.json").unlink()
        (reports / "sources.lock.json").symlink_to(external)
        code, _, stderr = self.run_cli("sync")
        self.assertEqual(2, code)
        self.assertIn("symlink", stderr)
        self.assertEqual(original, external.read_bytes())

    @unittest.skipUnless(hasattr(os, "symlink"), "requires symlink support")
    def test_build_and_validate_report_temp_symlinks_cannot_rewrite_external_file(self):
        report = self.tempdir / "build-report.json"
        external = self.tempdir / "external-build.json"
        original = b"external\n"
        external.write_bytes(original)
        report.with_name(f".{report.name}.tmp").symlink_to(external)

        pipeline_module._write_text(report, "catalog\n")

        self.assertEqual(b"catalog\n", report.read_bytes())
        self.assertEqual(original, external.read_bytes())

        code, _, stderr = self.run_cli("all")
        self.assertEqual(0, code, stderr)
        validation = self.tempdir / "validation.json"
        validation.with_name(f".{validation.name}.tmp").symlink_to(external)
        code, _, stderr = self.run_cli(
            "validate", "--report", str(validation)
        )
        self.assertEqual(0, code, stderr)
        self.assertEqual(original, external.read_bytes())

    def test_publication_rolls_back_after_one_mid_sequence_replace_failure(self):
        root, staging = self._publication_fixture()
        real_replace = os.replace
        calls = []

        def fail_fourth(source, destination):
            calls.append((Path(source), Path(destination)))
            if len(calls) == 4:
                raise OSError("injected publish failure")
            return real_replace(source, destination)

        with mock.patch("skill_atlas.pipeline.os.replace", side_effect=fail_fourth):
            with self.assertRaises(OSError):
                pipeline_module._publish_generated_tree(staging, root)

        for name in ("skills", "licenses", "reports"):
            self.assertEqual(
                f"old-{name}\n".encode(), (root / name / "sentinel").read_bytes()
            )

    def test_unrecoverable_publication_retains_backup_outside_cleanup(self):
        root, staging = self._publication_fixture()
        real_replace = os.replace
        calls = []

        def fail_from_fourth(source, destination):
            calls.append((Path(source), Path(destination)))
            if len(calls) >= 4:
                raise OSError("persistent injected failure")
            return real_replace(source, destination)

        with mock.patch("skill_atlas.pipeline.os.replace", side_effect=fail_from_fourth):
            with self.assertRaises(pipeline_module.PublicationRecoveryError) as caught:
                pipeline_module._publish_generated_tree(staging, root)

        recovery = caught.exception.recovery_path
        self.assertTrue(recovery.is_dir())
        self.assertEqual(
            b"old-skills\n", (recovery / "skills" / "sentinel").read_bytes()
        )
        self.assertEqual(
            b"old-licenses\n", (recovery / "licenses" / "sentinel").read_bytes()
        )

    def test_build_finally_does_not_delete_reported_recovery_path(self):
        recovery_paths = []

        def fail_with_recovery(staging, _root):
            recovery = staging.parent / "backup"
            (recovery / "skills").mkdir(parents=True)
            (recovery / "skills" / "sentinel").write_bytes(b"old\n")
            recovery_paths.append(recovery)
            raise pipeline_module.PublicationRecoveryError(
                recovery, OSError("persistent injected failure")
            )

        with mock.patch(
            "skill_atlas.pipeline._publish_generated_tree",
            side_effect=fail_with_recovery,
        ):
            code, _, stderr = self.run_cli("all")

        self.assertEqual(2, code)
        self.assertIn(str(recovery_paths[0]), stderr)
        self.assertEqual(
            b"old\n", (recovery_paths[0] / "skills" / "sentinel").read_bytes()
        )

    def _publication_fixture(self):
        root = self.tempdir / "publication-root"
        staging_parent = self.tempdir / "publication-staging"
        staging = staging_parent / "catalog"
        for base, prefix in ((root, "old"), (staging, "new")):
            for name in ("skills", "licenses", "reports"):
                directory = base / name
                directory.mkdir(parents=True)
                (directory / "sentinel").write_text(f"{prefix}-{name}\n")
        return root, staging

    def test_successful_rebuild_preserves_user_non_generated_files(self):
        code, _, stderr = self.run_cli("all")
        self.assertEqual(0, code, stderr)
        user_file = self.output / "reports" / "human-notes.md"
        user_file.write_bytes(b"keep me\n")

        code, _, stderr = self.run_cli("all")

        self.assertEqual(0, code, stderr)
        self.assertEqual(b"keep me\n", user_file.read_bytes())

    @unittest.skipUnless(hasattr(os, "symlink"), "requires symlink support")
    def test_managed_containers_fail_closed_when_file_or_symlink(self):
        original_output = self.output
        try:
            for index, name in enumerate(("skills", "licenses", "reports")):
                with self.subTest(name=name):
                    self.output = self.tempdir / f"invalid-container-{index}"
                    self.output.mkdir()
                    container = self.output / name
                    if name == "skills":
                        container.write_bytes(b"user-owned-file\n")
                    else:
                        external = self.tempdir / f"external-container-{index}"
                        external.mkdir()
                        (external / "sentinel").write_bytes(b"outside\n")
                        container.symlink_to(external, target_is_directory=True)

                    code, _, stderr = self.run_cli("all")

                    self.assertEqual(2, code)
                    self.assertIn("managed", stderr)
                    if name == "skills":
                        self.assertEqual(b"user-owned-file\n", container.read_bytes())
                    else:
                        self.assertTrue(container.is_symlink())
                        self.assertEqual(b"outside\n", (external / "sentinel").read_bytes())
        finally:
            self.output = original_output

    def test_rebuild_refuses_to_delete_user_file_inside_generated_skill_root(self):
        code, _, stderr = self.run_cli("all")
        self.assertEqual(0, code, stderr)
        skill_root = next(path.parent for path in (self.output / "skills").rglob("SKILL.md"))
        user_file = skill_root / "human-local-notes.txt"
        user_file.write_bytes(b"not generated\n")

        code, _, stderr = self.run_cli("all")

        self.assertEqual(1, code)
        self.assertIn("user content", stderr)
        self.assertEqual(b"not generated\n", user_file.read_bytes())

    def test_index_tree_target_is_sparse_complete_deduplicated_and_has_provenance(self):
        derived_repo = self.tempdir / "derived"
        _initialize_repository(derived_repo)
        _make_skill(derived_repo, "packs/selected", "selected")
        _make_skill(derived_repo, "packs/not-selected", "not-selected")
        _commit(derived_repo, "derived Skills")
        (self.index / "README.md").write_text(
            "\n".join(
                [
                    "https://github.com/acme/skills/tree/main/packs/selected",
                    "https://github.com/acme/skills/tree/main/packs/selected",
                    "https://github.com/test/direct",
                    "https://github.com/test/reference",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        _commit(self.index, "index derived target")

        def mapped_synchronizer(spec, cache_root, locked_commit=None):
            if spec.id == "acme/skills":
                local = derived_repo
                local_id = "test/derived"
            else:
                local = self.local_repositories[spec.id]
                local_id = spec.id
            local_spec = SourceSpec(
                id=local_id,
                url=local.as_uri(),
                mode=spec.mode,
                include_paths=list(spec.include_paths),
                exclude_paths=list(spec.exclude_paths),
            )
            resolved = sync_source(local_spec, cache_root, locked_commit=locked_commit)
            return ResolvedSource(source=spec, checkout=resolved.checkout, commit=resolved.commit)

        code, _, stderr = self.run_cli(
            "all", synchronizer=mapped_synchronizer
        )

        self.assertEqual(0, code, stderr)
        skill_documents = list((self.output / "skills").rglob("SKILL.md"))
        self.assertEqual(4, len(skill_documents))
        contents = [path.read_text() for path in skill_documents]
        self.assertTrue(any("name: selected" in content for content in contents))
        self.assertFalse(any("name: not-selected" in content for content in contents))
        selected = next(path.parent for path in skill_documents if "name: selected" in path.read_text())
        self.assertEqual(b"\x00\x01binary", (selected / "assets/template.bin").read_bytes())
        self.assertTrue((selected / "scripts/run.py").is_file())
        lock = json.loads((self.output / "reports/sources.lock.json").read_text())
        derived = next(item for item in lock["sources"] if item["id"] == "acme/skills")
        direct = next(item for item in lock["sources"] if item["id"] == "test/direct")
        self.assertEqual("archive", derived["mode"])
        self.assertEqual(["packs/selected"], derived["include_paths"])
        self.assertEqual(["test/index:README.md"], derived["index_provenance"])
        self.assertEqual(["test/index:README.md"], direct["index_provenance"])

    def test_index_derived_failure_is_reported_without_blocking_configured_direct(self):
        (self.index / "README.md").write_text(
            "https://github.com/missing/derived/tree/main/skills/one\n",
            encoding="utf-8",
        )
        _commit(self.index, "missing derived target")

        code, _, stderr = self.run_cli("all")

        self.assertEqual(0, code, stderr)
        self.assertEqual(3, len(list((self.output / "skills").rglob("SKILL.md"))))
        unresolved = json.loads((self.output / "reports/unresolved.json").read_text())
        self.assertTrue(
            any(item["source_id"] == "missing/derived" for item in unresolved["unresolved"])
        )
        summary = json.loads((self.output / "reports/summary.json").read_text())
        self.assertEqual(1, summary["inaccessible"])

    def test_index_derived_parse_failure_is_nonblocking_but_direct_parse_failure_blocks(self):
        derived_repo = self.tempdir / "malformed-derived"
        _initialize_repository(derived_repo)
        malformed = derived_repo / "skills" / "broken"
        malformed.mkdir(parents=True)
        (malformed / "SKILL.md").write_text("# missing frontmatter\n")
        _commit(derived_repo, "malformed derived Skill")
        (self.index / "README.md").write_text(
            "https://github.com/acme/bad-skills/tree/main/skills/broken\n"
        )
        _commit(self.index, "link malformed derived Skill")

        def mapped_synchronizer(spec, cache_root, locked_commit=None):
            if spec.id == "acme/bad-skills":
                local = derived_repo
                local_id = "test/malformed-derived"
            else:
                local = self.local_repositories[spec.id]
                local_id = spec.id
            local_spec = SourceSpec(
                id=local_id,
                url=local.as_uri(),
                mode=spec.mode,
                include_paths=list(spec.include_paths),
                exclude_paths=list(spec.exclude_paths),
            )
            resolved = sync_source(local_spec, cache_root, locked_commit=locked_commit)
            return ResolvedSource(source=spec, checkout=resolved.checkout, commit=resolved.commit)

        code, _, stderr = self.run_cli("all", synchronizer=mapped_synchronizer)

        self.assertEqual(0, code, stderr)
        self.assertEqual(3, len(list((self.output / "skills").rglob("skill-atlas.json"))))
        unresolved = json.loads((self.output / "reports/unresolved.json").read_text())
        self.assertTrue(
            any(
                item["source_id"] == "acme/bad-skills"
                and item["reason"] == "parse-failure"
                for item in unresolved["unresolved"]
            )
        )

        direct_broken = self.direct / "skills" / "broken"
        direct_broken.mkdir()
        (direct_broken / "SKILL.md").write_text("# missing frontmatter\n")
        _commit(self.direct, "malformed configured direct Skill")
        code, _, stderr = self.run_cli("all", sources=[self.sources[0]])
        self.assertEqual(1, code)
        self.assertIn("import failure", stderr)

    def test_nested_skill_is_both_complete_outer_resource_and_independent_entry(self):
        outer = self.direct / "skills" / "outer"
        _make_skill(self.direct, "skills/outer", "outer")
        _make_skill(
            self.direct,
            "skills/outer/references/embedded",
            "embedded",
        )
        _commit(self.direct, "nested Skill fixture")

        code, _, stderr = self.run_cli("all")

        self.assertEqual(0, code, stderr)
        skill_roots = [
            path.parent for path in (self.output / "skills").rglob("SKILL.md")
            if (path.parent / "skill-atlas.json").is_file()
        ]
        self.assertEqual(5, len(skill_roots))
        outer_copy = next(
            root for root in skill_roots
            if root.name == "outer" and (root / "references/embedded/SKILL.md").is_file()
        )
        embedded_copy = next(
            root for root in skill_roots
            if root.name == "embedded" and root != outer_copy / "references/embedded"
        )
        self.assertTrue((embedded_copy / "assets/template.bin").is_file())
        outer_sidecar = json.loads((outer_copy / "skill-atlas.json").read_text())
        self.assertEqual(
            outer_sidecar["integrity"]["content_hash"],
            hash_materialized_skill(outer_copy),
        )
        validation = json.loads(
            (self.output / "reports/validation.json").read_text()
        )
        self.assertEqual([], validation["failures"])


if __name__ == "__main__":
    unittest.main()

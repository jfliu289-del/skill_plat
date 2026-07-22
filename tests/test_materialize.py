import hashlib
import json
import os
import stat
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import skill_atlas.materialize as materialize_module
from skill_atlas.config import load_taxonomy
from skill_atlas.materialize import (
    MaterializationError,
    MaterializationSecurityError,
    catalog_path,
    cluster_duplicates,
    materialize,
)
from skill_atlas.models import Classification, ImportResult, SkillRecord, SourceSpec


ROOT = Path(__file__).resolve().parents[1]


class MaterializeTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.tempdir = Path(self.temporary_directory.name)
        self.source_skill = self.tempdir / "checkout" / "reviews" / "reviewing-code"
        self.source_skill.mkdir(parents=True)
        self.skill_bytes = (
            b"---\r\nname: reviewing-code\r\n"
            b"description: Review a pull request.\r\n---\r\n# Review\r\n"
        )
        (self.source_skill / "SKILL.md").write_bytes(self.skill_bytes)
        self.output = self.tempdir / "catalog"
        self.taxonomy = load_taxonomy(ROOT / "config" / "taxonomy.json")
        self.source = SourceSpec(
            id="acme/tools",
            url="https://github.com/acme/tools",
            mode="direct",
            redistribution_review=False,
        )
        self.record = SkillRecord(
            source=self.source,
            repository=self.source.url,
            commit="a" * 40,
            source_path="reviews/reviewing-code",
            skill_root=self.source_skill,
            name="reviewing-code",
            description="Review a pull request.",
            license="MIT",
            license_evidence=["LICENSE", "LICENSE"],
            skill_md_hash=hashlib.sha256(self.skill_bytes).hexdigest(),
            redistribution_review=False,
        )
        self.classification = Classification(
            primary_category="C07",
            secondary_categories=["C06", "C06"],
            tasks=["test", "review", "review"],
            stages=["validate"],
            artifacts=["code"],
            domains=["software"],
            audiences=["developer"],
            risk_level="R1",
            confidence=0.8123,
            needs_review=False,
            reasons=["z-reason", "a-reason", "a-reason"],
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_routes_and_preserves_skill_md_byte_for_byte(self):
        result = materialize(
            self.record, self.output, self.classification, self.taxonomy
        )

        self.assertEqual(
            Path(
                "skills/B-software-systems-automation/"
                "C07-debugging-testing-quality/acme/tools/reviews/reviewing-code"
            ),
            result.relative_path,
        )
        copied = self.output / result.relative_path / "SKILL.md"
        self.assertEqual(self.skill_bytes, copied.read_bytes())
        self.assertEqual(hashlib.sha256(self.skill_bytes).hexdigest(), result.skill_md_hash)

    def test_sidecar_has_fixed_format_complete_metadata_and_sorted_arrays(self):
        result = materialize(
            self.record, self.output, self.classification, self.taxonomy
        )
        sidecar = self.output / result.relative_path / "skill-atlas.json"
        payload = sidecar.read_bytes()
        data = json.loads(payload)

        self.assertTrue(payload.endswith(b"\n"))
        self.assertEqual(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            + b"\n",
            payload,
        )
        self.assertEqual("1.0", data["schema_version"])
        self.assertEqual(self.taxonomy.version, data["taxonomy_version"])
        self.assertEqual("1.0", data["classifier_version"])
        self.assertEqual(
            {
                "repository": "https://github.com/acme/tools",
                "commit": "a" * 40,
                "source_path": "reviews/reviewing-code",
                "license": "MIT",
                "license_evidence": ["LICENSE"],
                "redistribution_review": False,
                "registry_archive_mirror": False,
            },
            data["provenance"],
        )
        self.assertEqual(["C06"], data["classification"]["secondary_categories"])
        self.assertEqual(["review", "test"], data["classification"]["tasks"])
        self.assertEqual(["a-reason", "z-reason"], data["classification"]["reasons"])
        self.assertEqual([], data["integrity"]["excluded_paths"])
        self.assertRegex(data["integrity"]["content_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(result.sidecar_path, result.relative_path / "skill-atlas.json")

    def test_copies_the_complete_nested_skill_bundle(self):
        expected = {
            "scripts/run.py": b"print('run')\n",
            "references/api.md": b"# API\n",
            "assets/template.bin": b"\x00\x01template",
            "templates/report.md": b"# Report {{ title }}\n",
            "images/logo.png": b"\x89PNG\r\n\x1a\n",
            ".skill-resource": b"hidden resource\n",
            "empty/.keep": b"",
        }
        for relative, payload in expected.items():
            path = self.source_skill / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        (self.source_skill / "empty-directory").mkdir()

        result = materialize(
            self.record, self.output, self.classification, self.taxonomy
        )

        target = self.output / result.relative_path
        for relative, payload in expected.items():
            self.assertEqual(payload, (target / relative).read_bytes())
        self.assertTrue((target / "empty-directory").is_dir())

    @unittest.skipUnless(hasattr(os, "symlink"), "requires symlink support")
    def test_keeps_only_relative_symlinks_that_remain_inside_copied_skill(self):
        references = self.source_skill / "references"
        references.mkdir()
        (references / "guide.md").write_text("guide\n", encoding="utf-8")
        (self.source_skill / "guide-link").symlink_to("references/guide.md")
        (references / "escape").symlink_to("../../../../secret")
        (references / "absolute").symlink_to(references / "guide.md")
        (references / "broken").symlink_to("missing.md")

        result = materialize(
            self.record, self.output, self.classification, self.taxonomy
        )

        target = self.output / result.relative_path
        self.assertTrue((target / "guide-link").is_symlink())
        self.assertEqual("references/guide.md", os.readlink(target / "guide-link"))
        self.assertEqual(
            ["references/absolute", "references/broken", "references/escape"],
            result.excluded_paths,
        )
        for relative in result.excluded_paths:
            self.assertFalse((target / relative).exists())
            self.assertFalse((target / relative).is_symlink())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires FIFO support")
    def test_excludes_git_internals_and_special_files_without_reading_them(self):
        (self.source_skill / ".git" / "objects").mkdir(parents=True)
        (self.source_skill / ".git" / "objects" / "data").write_bytes(b"git")
        os.mkfifo(self.source_skill / "named-pipe")

        result = materialize(
            self.record, self.output, self.classification, self.taxonomy
        )

        self.assertEqual([".git", "named-pipe"], result.excluded_paths)
        target = self.output / result.relative_path
        self.assertFalse((target / ".git").exists())
        self.assertFalse((target / "named-pipe").exists())

    def test_content_hash_excludes_generated_sidecar_but_includes_mode(self):
        script = self.source_skill / "scripts" / "run.py"
        script.parent.mkdir()
        script.write_bytes(b"print('run')\n")
        script.chmod(0o644)
        first = materialize(
            self.record, self.output / "one", self.classification, self.taxonomy
        )
        changed_classification = Classification(
            **{
                **self.classification.__dict__,
                "confidence": 0.1234,
                "reasons": ["different-sidecar"],
            }
        )
        second = materialize(
            self.record, self.output / "two", changed_classification, self.taxonomy
        )
        self.assertEqual(first.content_hash, second.content_hash)

        script.chmod(0o755)
        third = materialize(
            self.record, self.output / "three", self.classification, self.taxonomy
        )
        self.assertNotEqual(first.content_hash, third.content_hash)

    def test_rejects_existing_upstream_sidecar_and_existing_destination(self):
        (self.source_skill / "skill-atlas.json").write_text("upstream\n", encoding="utf-8")
        with self.assertRaises(MaterializationError):
            materialize(self.record, self.output, self.classification, self.taxonomy)
        self.assertFalse(self.output.exists())

        (self.source_skill / "skill-atlas.json").unlink()
        relative = catalog_path(self.record, self.classification, self.taxonomy)
        existing = self.output / relative
        existing.mkdir(parents=True)
        sentinel = existing / "sentinel"
        sentinel.write_bytes(b"keep")
        with self.assertRaises(MaterializationError):
            materialize(self.record, self.output, self.classification, self.taxonomy)
        self.assertEqual(b"keep", sentinel.read_bytes())

    def test_nested_skill_atlas_named_resource_is_preserved_and_hashed(self):
        nested = self.source_skill / "references" / "skill-atlas.json"
        nested.parent.mkdir()
        nested.write_bytes(b'{"upstream": true}\n')

        result = materialize(
            self.record, self.output, self.classification, self.taxonomy
        )
        target = self.output / result.relative_path

        self.assertEqual(b'{"upstream": true}\n', (target / "references" / "skill-atlas.json").read_bytes())
        self.assertEqual(
            result.content_hash,
            materialize_module.hash_materialized_skill(target),
        )
        (target / "references" / "skill-atlas.json").write_bytes(
            b'{"upstream": false}\n'
        )
        self.assertNotEqual(
            result.content_hash,
            materialize_module.hash_materialized_skill(target),
        )

    def test_rejects_unsafe_or_inconsistent_routing_inputs(self):
        bad_path = SkillRecord(
            **{**self.record.__dict__, "source_path": "../reviewing-code"}
        )
        with self.assertRaises(MaterializationSecurityError):
            catalog_path(bad_path, self.classification, self.taxonomy)

        bad_repository = SkillRecord(
            **{**self.record.__dict__, "repository": "https://github.com/acme/tools/../evil"}
        )
        with self.assertRaises(MaterializationSecurityError):
            catalog_path(bad_repository, self.classification, self.taxonomy)

        unknown_category = Classification(
            **{**self.classification.__dict__, "primary_category": "C99"}
        )
        with self.assertRaises(MaterializationError):
            catalog_path(self.record, unknown_category, self.taxonomy)

        malformed_group = replace(self.taxonomy.groups["B"], id="C07")
        malformed_taxonomy = replace(
            self.taxonomy,
            groups={**self.taxonomy.groups, "B": malformed_group},
        )
        with self.assertRaises(MaterializationSecurityError):
            catalog_path(self.record, self.classification, malformed_taxonomy)

    def test_source_parent_keys_are_stable_and_unambiguous(self):
        root_record = SkillRecord(
            **{**self.record.__dict__, "source_path": "."}
        )
        multi_record = SkillRecord(
            **{**self.record.__dict__, "source_path": "packs/backend/reviewing-code"}
        )
        top_level_record = SkillRecord(
            **{**self.record.__dict__, "source_path": "reviewing-code"}
        )
        similar_record = SkillRecord(
            **{**self.record.__dict__, "source_path": "packs-backend/reviewing-code"}
        )

        root = catalog_path(root_record, self.classification, self.taxonomy)
        top_level = catalog_path(top_level_record, self.classification, self.taxonomy)
        multi = catalog_path(multi_record, self.classification, self.taxonomy)
        similar = catalog_path(similar_record, self.classification, self.taxonomy)

        self.assertEqual("_root-skill", root.parts[-2])
        self.assertEqual("_repository-root", root.parts[-1])
        self.assertNotEqual(root, top_level)
        self.assertTrue(multi.parts[-2].startswith("_encoded-m-"))
        self.assertNotEqual(multi, similar)

    def test_root_route_cannot_collide_with_legal_reserved_source_path(self):
        root_record = SkillRecord(
            **{**self.record.__dict__, "source_path": "."}
        )
        reserved_root = self.tempdir / "checkout" / "_root-skill" / "_repository-root"
        reserved_root.mkdir(parents=True)
        (reserved_root / "SKILL.md").write_bytes(self.skill_bytes)
        reserved_record = SkillRecord(
            **{
                **self.record.__dict__,
                "source_path": "_root-skill/_repository-root",
                "skill_root": reserved_root,
            }
        )

        root_path = catalog_path(root_record, self.classification, self.taxonomy)
        reserved_path = catalog_path(
            reserved_record, self.classification, self.taxonomy
        )

        self.assertNotEqual(root_path, reserved_path)
        self.assertEqual("_root-skill", root_path.parts[-2])
        self.assertTrue(reserved_path.parts[-2].startswith("_encoded-s-"))

    def test_hash_is_independently_recomputed_from_materialized_bundle(self):
        script = self.source_skill / "scripts" / "run.py"
        script.parent.mkdir()
        script.write_bytes(b"print('run')\n")
        script.chmod(0o755)
        (self.source_skill / "empty-directory").mkdir()

        result = materialize(
            self.record, self.output, self.classification, self.taxonomy
        )
        target = self.output / result.relative_path

        self.assertEqual(
            result.content_hash,
            materialize_module.hash_materialized_skill(target),
        )
        sidecar = target / "skill-atlas.json"
        sidecar.write_bytes(sidecar.read_bytes() + b" \n")
        self.assertEqual(
            result.content_hash,
            materialize_module.hash_materialized_skill(target),
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "requires symlink support")
    def test_different_excluded_dangling_targets_have_the_same_materialized_hash(self):
        references = self.source_skill / "references"
        references.mkdir()
        link = references / "missing"
        link.symlink_to("first-missing-target")
        first = materialize(
            self.record, self.output / "one", self.classification, self.taxonomy
        )
        first_root = self.output / "one" / first.relative_path

        link.unlink()
        link.symlink_to("second-missing-target")
        second = materialize(
            self.record, self.output / "two", self.classification, self.taxonomy
        )
        second_root = self.output / "two" / second.relative_path

        self.assertEqual(["references/missing"], first.excluded_paths)
        self.assertEqual(first.excluded_paths, second.excluded_paths)
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(first.content_hash, materialize_module.hash_materialized_skill(first_root))
        self.assertEqual(second.content_hash, materialize_module.hash_materialized_skill(second_root))

    def test_materialization_does_not_use_replacing_rename_for_publication(self):
        with mock.patch(
            "skill_atlas.materialize.os.rename",
            side_effect=AssertionError("replacing rename must not publish a Skill"),
        ):
            result = materialize(
                self.record, self.output, self.classification, self.taxonomy
            )

        self.assertTrue((self.output / result.relative_path / "SKILL.md").is_file())

    def test_preserves_skill_root_directory_mode(self):
        self.source_skill.chmod(0o750)

        result = materialize(
            self.record, self.output, self.classification, self.taxonomy
        )

        copied_mode = stat.S_IMODE((self.output / result.relative_path).stat().st_mode)
        self.assertEqual(0o750, copied_mode)

    def test_failure_removes_reserved_target_even_with_read_only_nested_directory(self):
        locked = self.source_skill / "references"
        locked.mkdir()
        (locked / "guide.md").write_bytes(b"guide\n")
        locked.chmod(0o555)
        target = self.output / catalog_path(
            self.record, self.classification, self.taxonomy
        )

        try:
            with mock.patch(
                "skill_atlas.materialize._write_sidecar",
                side_effect=MaterializationError("injected sidecar failure"),
            ):
                with self.assertRaises(MaterializationError):
                    materialize(
                        self.record,
                        self.output,
                        self.classification,
                        self.taxonomy,
                    )
            self.assertFalse(target.exists())
        finally:
            locked.chmod(0o755)
            copied_locked = target / "references"
            if copied_locked.exists():
                copied_locked.chmod(0o755)

    def test_skill_md_hash_mismatch_fails_before_creating_output(self):
        mismatched = SkillRecord(
            **{**self.record.__dict__, "skill_md_hash": "0" * 64}
        )
        with self.assertRaises(MaterializationError):
            materialize(mismatched, self.output, self.classification, self.taxonomy)
        self.assertFalse(self.output.exists())


class DuplicateClusterTests(unittest.TestCase):
    @staticmethod
    def result(relative_path: str, content_hash: str) -> ImportResult:
        source = SourceSpec.for_test("file:///unused")
        record = SkillRecord(
            source=source,
            repository="https://github.com/acme/tools",
            commit="a" * 40,
            source_path=relative_path,
            skill_root=Path("/unused"),
            name=Path(relative_path).name,
        )
        return ImportResult(
            record=record,
            relative_path=Path(relative_path),
            content_hash=content_hash,
            skill_md_hash="f" * 64,
        )

    def test_clusters_only_actual_duplicates_and_sorts_variants(self):
        results = [
            self.result("skills/z", "a" * 64),
            self.result("skills/singleton", "b" * 64),
            self.result("skills/a", "a" * 64),
        ]

        self.assertEqual(
            {"a" * 64: ["skills/a", "skills/z"]},
            cluster_duplicates(results),
        )


if __name__ == "__main__":
    unittest.main()

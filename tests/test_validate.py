import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from skill_atlas.config import load_taxonomy
from skill_atlas.materialize import cluster_duplicates, materialize
from skill_atlas.models import Classification, SkillRecord, SourceSpec
from skill_atlas.validate import detect_path_collisions, validate_catalog


ROOT = Path(__file__).resolve().parents[1]


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.tempdir = Path(self.temporary_directory.name)
        self.catalog = self.tempdir / "catalog"
        self.taxonomy = load_taxonomy(ROOT / "config" / "taxonomy.json")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _materialize(self, owner: str, name: str, payload: bytes = b"asset\n"):
        source_root = self.tempdir / "source" / owner / name
        (source_root / "assets").mkdir(parents=True)
        skill_bytes = (
            f"---\nname: {name}\ndescription: Review code safely.\n---\n# Review\n"
        ).encode()
        (source_root / "SKILL.md").write_bytes(skill_bytes)
        (source_root / "assets" / "payload.bin").write_bytes(payload)
        # An upstream nested file with the sidecar name is ordinary bundle content.
        (source_root / "assets" / "skill-atlas.json").write_text(
            '{"upstream": true}\n', encoding="utf-8"
        )
        source = SourceSpec(
            id=f"{owner}/tools",
            url=f"https://github.com/{owner}/tools",
            mode="direct",
            redistribution_review=True,
        )
        record = SkillRecord(
            source=source,
            repository=source.url,
            commit="a" * 40,
            source_path=f"skills/{name}",
            skill_root=source_root,
            name=name,
            description="Review code safely.",
            skill_md_hash=hashlib.sha256(skill_bytes).hexdigest(),
            redistribution_review=True,
        )
        classification = Classification(
            primary_category="C07",
            secondary_categories=["C06"],
            tasks=["review"],
            stages=["validate"],
            artifacts=["code"],
            domains=["software"],
            audiences=["developer"],
            risk_level="R1",
            confidence=0.9,
            needs_review=False,
            reasons=["test"],
        )
        return materialize(record, self.catalog, classification, self.taxonomy)

    def _write_reports(self, results):
        reports = self.catalog / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        records = []
        for result in results:
            sidecar = json.loads(
                (self.catalog / result.sidecar_path).read_text(encoding="utf-8")
            )
            records.append(
                {"catalog_path": result.relative_path.as_posix(), **sidecar}
            )
        (reports / "catalog.jsonl").write_text(
            "".join(
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
                for item in sorted(records, key=lambda item: item["catalog_path"])
            ),
            encoding="utf-8",
        )
        (reports / "duplicates.json").write_text(
            json.dumps(
                {"duplicates": cluster_duplicates(results)},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_valid_catalog_has_no_failures_and_ignores_nested_sidecar_name(self):
        results = [self._materialize("acme", "one"), self._materialize("beta", "two")]
        self._write_reports(results)

        report = validate_catalog(self.catalog, self.taxonomy)

        self.assertEqual([], report.failures)
        self.assertEqual(2, report.skill_count)
        self.assertEqual(2, report.central_record_count)

    def test_detects_missing_sidecar_and_category_path_mismatch(self):
        first = self._materialize("acme", "one")
        second = self._materialize("beta", "two")
        (self.catalog / first.sidecar_path).unlink()
        sidecar_path = self.catalog / second.sidecar_path
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        payload["classification"]["primary_category"] = "C06"
        sidecar_path.write_text(json.dumps(payload), encoding="utf-8")
        self._write_reports([second])

        codes = {item.code for item in validate_catalog(self.catalog, self.taxonomy).failures}

        self.assertIn("missing-sidecar", codes)
        self.assertIn("category-path-mismatch", codes)

    def test_detects_skill_md_and_complete_bundle_hash_mismatch(self):
        result = self._materialize("acme", "one")
        self._write_reports([result])
        skill_root = self.catalog / result.relative_path
        (skill_root / "SKILL.md").write_bytes(b"tampered\n")
        (skill_root / "assets" / "payload.bin").write_bytes(b"also tampered\n")

        codes = {item.code for item in validate_catalog(self.catalog, self.taxonomy).failures}

        self.assertIn("skill-md-hash-mismatch", codes)
        self.assertIn("content-hash-mismatch", codes)

    def test_validates_complete_schema_taxonomy_and_license_condition(self):
        result = self._materialize("acme", "one")
        self._write_reports([result])
        sidecar_path = self.catalog / result.sidecar_path
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        payload["unexpected"] = True
        payload["provenance"]["commit"] = "ABC"
        payload["provenance"]["redistribution_review"] = False
        payload["provenance"]["license"] = None
        payload["provenance"]["license_evidence"] = []
        payload["classification"]["tasks"] = ["not-controlled"]
        sidecar_path.write_text(json.dumps(payload), encoding="utf-8")

        failures = validate_catalog(self.catalog, self.taxonomy).failures
        codes = {item.code for item in failures}

        self.assertIn("schema-additional-property", codes)
        self.assertIn("schema-format", codes)
        self.assertIn("schema-condition", codes)
        self.assertIn("unknown-task", codes)
        self.assertEqual(
            sorted((item.code, item.path, item.message) for item in failures),
            [(item.code, item.path, item.message) for item in failures],
        )

    def test_detects_central_catalog_path_and_duplicate_inconsistency(self):
        first = self._materialize("acme", "one", b"same\n")
        second = self._materialize("beta", "two", b"same\n")
        # Make bundle hashes genuinely identical by aligning SKILL.md bytes too.
        first_root = self.catalog / first.relative_path
        second_root = self.catalog / second.relative_path
        (second_root / "SKILL.md").write_bytes((first_root / "SKILL.md").read_bytes())
        second_sidecar_path = second_root / "skill-atlas.json"
        second_sidecar = json.loads(second_sidecar_path.read_text(encoding="utf-8"))
        first_sidecar = json.loads((first_root / "skill-atlas.json").read_text(encoding="utf-8"))
        second_sidecar["integrity"] = first_sidecar["integrity"]
        second_sidecar_path.write_text(json.dumps(second_sidecar), encoding="utf-8")
        self._write_reports([first, second])
        catalog_lines = (self.catalog / "reports/catalog.jsonl").read_text().splitlines()
        central = json.loads(catalog_lines[0])
        central["catalog_path"] = "skills/not/the/real/path"
        catalog_lines[0] = json.dumps(central)
        (self.catalog / "reports/catalog.jsonl").write_text("\n".join(catalog_lines) + "\n")
        (self.catalog / "reports/duplicates.json").write_text('{"duplicates": {}}\n')

        codes = {item.code for item in validate_catalog(self.catalog, self.taxonomy).failures}

        self.assertIn("central-path-mismatch", codes)
        self.assertIn("duplicate-cluster-mismatch", codes)

    def test_detects_nfc_and_casefold_portability_collisions(self):
        collisions = detect_path_collisions(
            [
                "skills/A/Readme",
                "skills/a/README",
                "skills/Caf\u00e9/SKILL.md",
                "skills/Cafe\u0301/SKILL.md",
            ]
        )

        self.assertEqual(2, len(collisions))
        self.assertEqual(
            ["skills/A/Readme", "skills/a/README"], collisions[0].paths
        )
        self.assertEqual(
            ["skills/Cafe\u0301/SKILL.md", "skills/Caf\u00e9/SKILL.md"],
            collisions[1].paths,
        )


if __name__ == "__main__":
    unittest.main()

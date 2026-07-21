import tempfile
import unittest
from pathlib import Path

from skill_atlas.classifier import classify
from skill_atlas.config import load_taxonomy
from skill_atlas.frontmatter import parse_skill
from skill_atlas.models import SourceSpec


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "skills"
RISK_ORDER = {f"R{level}": level for level in range(5)}


class ClassifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.taxonomy = load_taxonomy(ROOT / "config/taxonomy.json")

    def classify_fixture(self, fixture: str):
        return classify(
            parse_skill(FIXTURES / fixture / "SKILL.md"),
            self.taxonomy,
            SourceSpec.for_test("https://github.com/test/source"),
        )

    def classify_text(self, name: str, description: str, body: str = ""):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text(
                f"---\nname: {name}\ndescription: {description}\n---\n{body}\n",
                encoding="utf-8",
            )
            return classify(
                parse_skill(path),
                self.taxonomy,
                SourceSpec.for_test("https://github.com/test/source"),
            )

    def test_code_review_is_quality(self):
        result = self.classify_fixture("code-review")

        self.assertEqual("C07", result.primary_category)
        self.assertIn("review", result.tasks)
        self.assertIn("code", result.artifacts)

    def test_literature_review_is_science_with_search_secondary(self):
        result = self.classify_fixture("literature-review")

        self.assertEqual("C15", result.primary_category)
        self.assertIn("C01", result.secondary_categories)
        self.assertIn("paper", result.artifacts)

    def test_browser_crm_is_action_automation(self):
        result = self.classify_fixture("browser-crm")

        self.assertEqual("C19", result.primary_category)
        self.assertIn("automate", result.tasks)

    def test_output_is_deterministic_unique_and_sorted(self):
        first = self.classify_fixture("code-review")
        second = self.classify_fixture("code-review")

        self.assertEqual(first, second)
        for values in (
            first.secondary_categories,
            first.tasks,
            first.stages,
            first.artifacts,
            first.domains,
            first.audiences,
            first.reasons,
        ):
            self.assertEqual(sorted(set(values)), values)

    def test_source_default_is_used_only_for_weak_text_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text(
                "---\nname: helper\ndescription: Handle a routine workflow.\n---\n",
                encoding="utf-8",
            )
            source = SourceSpec.for_test("https://github.com/test/source")
            source.default_categories = ["C14"]

            weak = classify(parse_skill(path), self.taxonomy, source)

        strong = self.classify_fixture("code-review")
        self.assertEqual("C14", weak.primary_category)
        self.assertTrue(weak.needs_review)
        self.assertEqual("C07", strong.primary_category)

    def test_unmatched_skill_still_gets_reviewable_primary_category(self):
        result = self.classify_text("helper", "Handle a routine workflow.")

        self.assertEqual("C00", result.primary_category)
        self.assertEqual(0.0, result.confidence)
        self.assertTrue(result.needs_review)

    def test_classification_ignores_machine_checkout_ancestors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = []
            source_paths = []
            for checkout in ("plain-checkout", "deployment-security-checkout"):
                checkout_root = root / checkout
                checkout_root.mkdir()
                path = checkout_root / "SKILL.md"
                path.write_text(
                    "---\nname: helper\ndescription: Handle a routine workflow.\n---\n",
                    encoding="utf-8",
                )
                parsed = parse_skill(path)
                source_paths.append(parsed.source_path)
                results.append(
                    classify(
                        parsed,
                        self.taxonomy,
                        SourceSpec.for_test("https://github.com/test/source"),
                    )
                )

        self.assertEqual([".", "."], source_paths)
        self.assertEqual(results[0], results[1])

    def test_repo_relative_source_path_remains_classification_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            skill_directory = repository / "catalog" / "deployment" / "helper"
            skill_directory.mkdir(parents=True)
            path = skill_directory / "SKILL.md"
            path.write_text(
                "---\nname: helper\ndescription: Handle a routine workflow.\n---\n",
                encoding="utf-8",
            )

            result = classify(
                parse_skill(path, source_root=repository),
                self.taxonomy,
                SourceSpec.for_test("https://github.com/test/source"),
            )

        self.assertEqual("C08", result.primary_category)
        self.assertEqual("R3", result.risk_level)

    def test_credentials_deployment_and_external_writes_are_at_least_r3(self):
        for description in (
            "Rotate credentials for an application.",
            "Perform a production deployment.",
            "Write updates to an external account.",
            "Writes changes to external accounts.",
            "Publishes customer content.",
            "Deploying services to production.",
        ):
            with self.subTest(description=description):
                result = self.classify_text("operations", description)
                self.assertGreaterEqual(RISK_ORDER[result.risk_level], 3)

    def test_high_stakes_and_offensive_security_decisions_are_r4(self):
        for description in (
            "Recommend a medical treatment decision.",
            "Provide legal advice for a contract decision.",
            "Make an investment decision using financial data.",
            "Plan vulnerability exploitation for an offensive security engagement.",
            "Makes medical diagnostic decisions for patients.",
            "Makes legal decisions for clients.",
            "Makes financial decisions for investors.",
        ):
            with self.subTest(description=description):
                result = self.classify_text("decision-support", description)
                self.assertEqual("R4", result.risk_level)


if __name__ == "__main__":
    unittest.main()

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_atlas.frontmatter import SkillParseError, parse_skill


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class FrontmatterTests(unittest.TestCase):
    def test_parses_folded_description_without_mutating_bytes(self):
        path = FIXTURES / "skills/code-review/SKILL.md"
        before = path.read_bytes()

        parsed = parse_skill(path)

        self.assertEqual("reviewing-code", parsed.name)
        self.assertIn("pull request", parsed.description.lower())
        self.assertEqual(before, parsed.raw_bytes)
        self.assertEqual(hashlib.sha256(before).hexdigest(), parsed.skill_md_hash)
        self.assertIn("Code Review", parsed.headings)
        self.assertEqual(before, path.read_bytes())

    def test_rejects_missing_frontmatter(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text("# Missing metadata\n", encoding="utf-8")

            with self.assertRaises(SkillParseError):
                parse_skill(path)

    def test_requires_non_empty_string_name_and_description(self):
        invalid_metadata = [
            "name: ''\ndescription: useful\n",
            "name: example\ndescription: []\n",
        ]
        for metadata in invalid_metadata:
            with self.subTest(metadata=metadata), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "SKILL.md"
                path.write_text(f"---\n{metadata}---\n# Body\n", encoding="utf-8")

                with self.assertRaises(SkillParseError):
                    parse_skill(path)

    def test_decodes_classification_text_with_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            raw = b"---\nname: example\ndescription: useful\n---\n# Invalid\n\xff\n"
            path.write_bytes(raw)

            parsed = parse_skill(path)

            self.assertIn("\ufffd", parsed.text)
            self.assertEqual(raw, parsed.raw_bytes)

    def test_records_repo_relative_skill_directory_as_source_path(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            skill_directory = repository / "catalog" / "deployment" / "helper"
            skill_directory.mkdir(parents=True)
            path = skill_directory / "SKILL.md"
            path.write_text(
                "---\nname: helper\ndescription: Handle a routine workflow.\n---\n",
                encoding="utf-8",
            )

            parsed = parse_skill(path, source_root=repository)

            self.assertEqual("catalog/deployment/helper", parsed.source_path)

    def test_rejects_source_path_outside_explicit_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            outside = root / "outside" / "SKILL.md"
            outside.parent.mkdir()
            outside.write_text(
                "not frontmatter\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SkillParseError, "outside source root"):
                parse_skill(outside, source_root=repository)

    def test_rejects_escaping_symlink_before_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            outside = root / "outside" / "SKILL.md"
            outside.parent.mkdir()
            outside.write_text("not frontmatter\n", encoding="utf-8")
            symlink = repository / "SKILL.md"
            symlink.symlink_to(outside)

            with patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("out-of-root path was read"),
            ):
                with self.assertRaisesRegex(SkillParseError, "outside source root"):
                    parse_skill(symlink, source_root=repository)


if __name__ == "__main__":
    unittest.main()

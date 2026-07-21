import hashlib
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()

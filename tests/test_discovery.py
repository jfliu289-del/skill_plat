import json
import tempfile
import unittest
from pathlib import Path

from skill_atlas.discovery import (
    DiscoverySecurityError,
    discover_github_targets,
    discover_openclaw_archive_paths,
    discover_skill_roots,
    parse_github_tree_url,
)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.tempdir = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def make_skill_repository(self) -> Path:
        repository = self.tempdir / "repository"
        valid = repository / "skills" / "valid"
        (valid / "references").mkdir(parents=True)
        (valid / "SKILL.md").write_text("# Valid\n", encoding="utf-8")
        (valid / "references" / "guide.md").write_text("guide\n", encoding="utf-8")
        lowercase = repository / "skills" / "lowercase"
        lowercase.mkdir(parents=True)
        (lowercase / "skill.md").write_text("# Wrong case\n", encoding="utf-8")
        vendor = repository / "vendor" / "blocked"
        vendor.mkdir(parents=True)
        (vendor / "SKILL.md").write_text("# Excluded\n", encoding="utf-8")
        git_internal = repository / ".git" / "hidden"
        git_internal.mkdir(parents=True)
        (git_internal / "SKILL.md").write_text("# Git internal\n", encoding="utf-8")
        outside = self.tempdir / "outside"
        outside.mkdir()
        (outside / "SKILL.md").write_text("# Outside\n", encoding="utf-8")
        (repository / "skills" / "linked-outside").symlink_to(
            outside, target_is_directory=True
        )
        return repository

    def make_github_index(self) -> Path:
        index = self.tempdir / "github-index"
        index.mkdir()
        (index / "README.md").write_text(
            "\n".join(
                [
                    "[Calendar](https://github.com/openclaw/skills/tree/main/skills/alice/calendar)",
                    "https://github.com/openclaw/skills/tree/main/skills/bob/research",
                    "https://github.com/openclaw/skills/tree/main/skills/alice/calendar",
                    "https://github.com/example/tool.git",
                    "https://github.com/trailing/repository/",
                    "https://github.com/ignored/repo/issues/1",
                ]
            ),
            encoding="utf-8",
        )
        return index

    def make_openclaw_index(self) -> Path:
        index = self.tempdir / "openclaw-index"
        index.mkdir()
        (index / "README.md").write_text(
            "\n".join(
                [
                    "[Calendar](https://clawskills.sh/skills/alice/calendar)",
                    "https://clawhub.ai/bob/research",
                    "https://clawskills.sh/skills/alice/calendar",
                    "https://clawskills.sh/skills/alice",
                    "https://clawhub.ai/bob/research/extra",
                    "https://clawhub.ai/carol/writing?source=index",
                ]
            ),
            encoding="utf-8",
        )
        return index

    def test_finds_only_exact_uppercase_skill_md_without_following_symlinks(self):
        repository = self.make_skill_repository()

        roots = discover_skill_roots(repository, ["."], ["vendor", ".git"])

        self.assertEqual([repository / "skills/valid"], roots)

    def test_rejects_include_path_outside_repository(self):
        repository = self.make_skill_repository()

        with self.assertRaises(DiscoverySecurityError):
            discover_skill_roots(repository, ["../outside"], [])

    def test_many_tree_links_become_one_repo_target_with_index_provenance(self):
        index = self.make_github_index()

        targets = discover_github_targets(index)

        target = next(
            item for item in targets if item.url == "https://github.com/openclaw/skills"
        )
        self.assertEqual(
            ["skills/alice/calendar", "skills/bob/research"],
            target.include_paths,
        )
        self.assertEqual(["README.md"], target.provenance)
        self.assertEqual(
            [
                "https://github.com/example/tool",
                "https://github.com/openclaw/skills",
                "https://github.com/trailing/repository",
            ],
            [item.url for item in targets],
        )

    def test_rejects_tree_path_traversal(self):
        self.assertIsNone(
            parse_github_tree_url("https://github.com/a/b/tree/main/../../etc")
        )
        self.assertIsNone(
            parse_github_tree_url("https://github.com/a/b/tree/main/%2e%2e/etc")
        )

    def test_maps_openclaw_links_and_records_malformed_links(self):
        index = self.make_openclaw_index()

        paths = discover_openclaw_archive_paths(index)

        self.assertEqual(
            ["skills/alice/calendar", "skills/bob/research"],
            paths,
        )
        self.assertEqual(
            {
                "unresolved": [
                    {
                        "index_path": "README.md",
                        "reason": "malformed_openclaw_skill_url",
                        "url": "https://clawhub.ai/bob/research/extra",
                    },
                    {
                        "index_path": "README.md",
                        "reason": "malformed_openclaw_skill_url",
                        "url": "https://clawhub.ai/carol/writing?source=index",
                    },
                    {
                        "index_path": "README.md",
                        "reason": "malformed_openclaw_skill_url",
                        "url": "https://clawskills.sh/skills/alice",
                    },
                ]
            },
            json.loads((index / "unresolved.json").read_text(encoding="utf-8")),
        )

    def test_unresolved_report_refuses_symlink_without_rewriting_external_target(self):
        index = self.make_openclaw_index()
        external_report = self.tempdir / "external-unresolved.json"
        original = b'{"outside": true}\n'
        external_report.write_bytes(original)
        (index / "unresolved.json").symlink_to(external_report)

        with self.assertRaises(DiscoverySecurityError):
            discover_openclaw_archive_paths(index)

        self.assertEqual(original, external_report.read_bytes())
        self.assertTrue((index / "unresolved.json").is_symlink())


if __name__ == "__main__":
    unittest.main()

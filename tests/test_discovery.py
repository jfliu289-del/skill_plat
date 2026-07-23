import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from skill_atlas.discovery import (
    DiscoverySecurityError,
    discover_clawhub_claims,
    discover_github_targets,
    discover_skill_roots,
    parse_github_tree_url,
    registry_claim_id,
)
from skill_atlas.models import RegistryClaim, RegistryIndexEntry


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

    def make_clawhub_index(self) -> Path:
        index = self.tempdir / "clawhub-index"
        categories = index / "categories"
        categories.mkdir(parents=True)
        (categories / "research.md").write_text(
            "\n".join(
                [
                    "[arxiv-search-collector](https://clawskills.sh/skills/xukp20-arxiv-search-collector)",
                    "[arxiv-search-collector](https://clawskills.sh/skills/xukp20-arxiv-search-collector)",
                ]
            ),
            encoding="utf-8",
        )
        (categories / "productivity.md").write_text(
            "\n".join(
                [
                    "[calendar](https://clawhub.ai/alice/calendar)",
                    "[calendar](https://clawhub.ai/alice/skills/calendar)",
                    "[calendar](https://clawhub.ai/alice/calendar)",
                ]
            ),
            encoding="utf-8",
        )
        return index

    def make_malformed_clawhub_index(self) -> Path:
        index = self.tempdir / "malformed-clawhub-index"
        index.mkdir()
        (index / "README.md").write_text(
            "\n".join(
                [
                    "[not-calendar](https://clawhub.ai/Alice/calendar?source=index#fragment)",
                    "https://clawhub.ai/alice/calendar",
                ]
            ),
            encoding="utf-8",
        )
        return index

    def snapshot_tree(self, root: Path):
        return tuple(
            (path.relative_to(root).as_posix(), path.read_bytes())
            for path in sorted(root.rglob("*"))
            if path.is_file()
        )

    def valid_claim(self) -> RegistryClaim:
        return RegistryClaim(
            claimed_slug="calendar",
            claimed_owner="alice",
            legacy_id=None,
            index_entries=(
                RegistryIndexEntry(
                    "categories/productivity.md",
                    "calendar",
                    "https://clawhub.ai/alice/calendar",
                ),
                RegistryIndexEntry(
                    "README.md",
                    "calendar",
                    "https://clawhub.ai/alice/skills/calendar",
                ),
            ),
        )

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

    def test_discovers_legacy_and_canonical_claims_without_modifying_index(self):
        index = self.make_clawhub_index()
        before = self.snapshot_tree(index)

        discovery = discover_clawhub_claims(index)

        self.assertEqual(before, self.snapshot_tree(index))
        self.assertEqual(
            [
                ("arxiv-search-collector", None, "xukp20-arxiv-search-collector"),
                ("calendar", "alice", None),
            ],
            [
                (item.claimed_slug, item.claimed_owner, item.legacy_id)
                for item in discovery.claims
            ],
        )
        self.assertEqual(
            (
                RegistryIndexEntry(
                    "categories/research.md",
                    "arxiv-search-collector",
                    "https://clawskills.sh/skills/xukp20-arxiv-search-collector",
                ),
            ),
            discovery.claims[0].index_entries,
        )
        self.assertEqual(
            (
                RegistryIndexEntry(
                    "categories/productivity.md",
                    "calendar",
                    "https://clawhub.ai/alice/calendar",
                ),
                RegistryIndexEntry(
                    "categories/productivity.md",
                    "calendar",
                    "https://clawhub.ai/alice/skills/calendar",
                ),
            ),
            discovery.claims[1].index_entries,
        )
        self.assertEqual((), discovery.unresolved)

    def test_records_label_mismatch_query_fragment_and_malformed_components(self):
        discovery = discover_clawhub_claims(
            self.make_malformed_clawhub_index()
        )

        self.assertEqual(
            ["malformed-clawhub-link", "missing-markdown-label"],
            sorted(item["reason"] for item in discovery.unresolved),
        )
        self.assertTrue(
            all(
                item["source_id"] == "VoltAgent/awesome-openclaw-skills"
                for item in discovery.unresolved
            )
        )

    def test_rejects_unsafe_or_noncanonical_clawhub_components(self):
        invalid_urls = [
            "https://clawhub.ai/alice/calendar?source=index",
            "https://clawhub.ai/alice/calendar#fragment",
            "https://clawhub.ai/alice/%5Ccalendar",
            "https://clawhub.ai/alice/%00calendar",
            "https://clawhub.ai/alice/../calendar",
            "https://clawhub.ai/alice/%2e%2e",
            "https://clawhub.ai/alice/%252e%252e",
            "https://clawhub.ai/Alice/calendar",
        ]
        for offset, url in enumerate(invalid_urls):
            with self.subTest(url=url):
                index = self.tempdir / f"invalid-{offset}.md"
                index.write_text(f"[calendar]({url})\n", encoding="utf-8")
                discovery = discover_clawhub_claims(index)
                self.assertEqual((), discovery.claims)
                self.assertEqual(
                    ["malformed-clawhub-link"],
                    [item["reason"] for item in discovery.unresolved],
                )

    def test_claim_id_is_stable_and_changes_with_any_audited_claim_field(self):
        claim = self.valid_claim()
        reordered = replace(claim, index_entries=tuple(reversed(claim.index_entries)))
        self.assertEqual(registry_claim_id(claim), registry_claim_id(reordered))

        changed_entries = {
            "claimed_slug": replace(claim, claimed_slug="calendar-two"),
            "claimed_owner": replace(claim, claimed_owner="bob"),
            "legacy_id": replace(claim, legacy_id="alice-calendar"),
            "index_path": replace(
                claim,
                index_entries=(
                    replace(claim.index_entries[0], index_path="README.md"),
                    claim.index_entries[1],
                ),
            ),
            "label": replace(
                claim,
                index_entries=(
                    replace(claim.index_entries[0], label="calendar-two"),
                    claim.index_entries[1],
                ),
            ),
            "url": replace(
                claim,
                index_entries=(
                    replace(
                        claim.index_entries[0],
                        url="https://clawhub.ai/alice/skills/calendar",
                    ),
                    claim.index_entries[1],
                ),
            ),
        }
        original_id = registry_claim_id(claim)
        for field, changed in changed_entries.items():
            with self.subTest(field=field):
                self.assertNotEqual(original_id, registry_claim_id(changed))


if __name__ == "__main__":
    unittest.main()

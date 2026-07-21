import unittest
from pathlib import Path

from skill_atlas.config import load_sources, load_taxonomy


ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_taxonomy_has_six_groups_and_twenty_unique_categories(self):
        taxonomy = load_taxonomy(ROOT / "config/taxonomy.json")
        self.assertEqual(6, len(taxonomy.groups))
        self.assertEqual({f"C{i:02d}" for i in range(20)}, set(taxonomy.categories))
        routed = [item.id for group in taxonomy.groups.values() for item in group.categories]
        self.assertEqual(20, len(routed))
        self.assertEqual(20, len(set(routed)))

    def test_sources_are_unique_https_github_repositories(self):
        sources = load_sources(ROOT / "config/sources.json")
        self.assertEqual(len(sources), len({item.id for item in sources}))
        self.assertTrue(all(item.url.startswith("https://github.com/") for item in sources))
        self.assertTrue(
            all(item.mode in {"direct", "index", "archive", "reference"} for item in sources)
        )


if __name__ == "__main__":
    unittest.main()

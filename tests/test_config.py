import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from skill_atlas.config import load_registry, load_sources, load_taxonomy
from skill_atlas.models import SkillRecord


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_ROUTING = {
    "A": ["C01", "C02", "C03", "C04", "C05"],
    "B": ["C06", "C07", "C08", "C09", "C10", "C19"],
    "C": ["C11", "C12", "C13", "C14"],
    "D": ["C15", "C16"],
    "E": ["C17", "C18"],
    "F": ["C00"],
}

DIRECT_SOURCES = """
anthropics/skills openai/plugins github/awesome-copilot vercel-labs/agent-skills
huggingface/skills NVIDIA/skills obra/superpowers trailofbits/skills
openai/skills microsoft/skills dotnet/skills google/skills cloudflare/skills
supabase/agent-skills getsentry/skills grafana/skills addyosmani/agent-skills
antfu/skills softaworks/agent-toolkit wshobson/agents OthmanAdi/planning-with-files
gotalab/cc-sdd a5c-ai/babysitter semgrep/skills ljagiello/ctf-skills
antonbabenko/terraform-skill K-Dense-AI/scientific-agent-skills
claude-office-skills/skills googleworkspace/cli google-labs-code/stitch-skills
adobe/skills markdown-viewer/skills michaelboeding/skills
GarethManning/education-agent-skills CaseMark/skills OctagonAI/skills
phuryn/pm-skills product-on-purpose/pm-skills RefoundAI/lenny-skills
ncklrs/startup-os-skills coreyhaines31/marketingskills NEON-Rutger/B2B-revops-skills
alirezarezvani/claude-skills borghei/Claude-Skills lyndonkl/claude
openclaw/agent-skills vercel-labs/skills remotion-dev/skills WordPress/agent-skills
apify/agent-skills hashicorp/agent-skills elastic/agent-skills ClickHouse/agent-skills
laravel/agent-skills BuilderIO/skills firebase/agent-skills
callstackincubator/agent-skills TheQtCompanyRnD/agent-skills Automattic/agent-skills
Memento-Teams/Memento-Skills SynaLinks/synalinks-skills
Agentchengfeng/chengfeng-videocut-skills JimLiu/baoyu-skills
KKKKhazix/khazix-skills Agents365-ai/drawio-skill ningzimu/codex-ppt-skill
SamurAIGPT/Generative-Media-Skills kepano/obsidian-skills
""".split()

INDEX_SOURCES = """
VoltAgent/awesome-openclaw-skills VoltAgent/awesome-agent-skills
skillmatic-ai/awesome-agent-skills heilcheng/awesome-agent-skills
danielrosehill/Useful-AI-Agent-Skills ComposioHQ/awesome-claude-skills
sickn33/agentic-awesome-skills InternScience/Awesome-Scientific-Skills
""".split()

REFERENCE_SOURCES = [
    "agentskills/agentskills",
    "openclaw/clawhub",
    "cisco-ai-defense/skill-scanner",
    "datalayer/agent-skills",
]

EXPECTED_SOURCES = {
    **{source_id: "direct" for source_id in DIRECT_SOURCES},
    **{source_id: "index" for source_id in INDEX_SOURCES},
    **{source_id: "reference" for source_id in REFERENCE_SOURCES},
}


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.tempdir = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_registry(self, payload):
        path = self.tempdir / "clawhub.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_taxonomy_has_exact_six_group_routing(self):
        taxonomy = load_taxonomy(ROOT / "config/taxonomy.json")
        actual = {
            group_id: [category.id for category in group.categories]
            for group_id, group in taxonomy.groups.items()
        }
        self.assertEqual(EXPECTED_ROUTING, actual)
        self.assertEqual({f"C{i:02d}" for i in range(20)}, set(taxonomy.categories))

    def test_taxonomy_loads_typed_controlled_vocabularies_and_rules(self):
        taxonomy = load_taxonomy(ROOT / "config/taxonomy.json")

        for vocabulary in (
            taxonomy.tasks,
            taxonomy.stages,
            taxonomy.artifacts,
            taxonomy.domains,
            taxonomy.audiences,
        ):
            self.assertIsInstance(vocabulary, tuple)
            self.assertTrue(vocabulary)
            self.assertEqual(len(vocabulary), len(set(vocabulary)))

        self.assertEqual(20, len(taxonomy.categories))
        for category in taxonomy.categories.values():
            self.assertTrue(category.exact_phrases)
            self.assertTrue(category.tokens)

        self.assertTrue(taxonomy.cross_tag_rules)
        self.assertTrue(taxonomy.risk_cues)
        self.assertEqual(
            {"R3", "R4"},
            {cue.level for cue in taxonomy.risk_cues},
        )

    def test_sources_match_frozen_inventory_urls_modes_and_counts(self):
        sources = load_sources(ROOT / "config/sources.json")
        actual = {item.id: (item.url, item.mode) for item in sources}
        expected = {
            source_id: (f"https://github.com/{source_id}", mode)
            for source_id, mode in EXPECTED_SOURCES.items()
        }
        self.assertEqual(80, len(sources))
        self.assertNotIn("openclaw/skills", {item.id for item in sources})
        self.assertEqual(expected, actual)
        self.assertEqual(
            Counter({"direct": 68, "index": 8, "reference": 4}),
            Counter(item.mode for item in sources),
        )
        index = next(
            item for item in sources
            if item.id == "VoltAgent/awesome-openclaw-skills"
        )
        self.assertEqual(
            "6afb5d4e3e6f36ff181a33b3b6f88054348bc70a",
            index.ref,
        )

    def test_generic_archive_mirror_flows_from_source_to_skill_record_and_schema(self):
        archive = load_sources(
            self._write_sources(
                {
                    "id": "owner/archive",
                    "url": "https://github.com/owner/archive",
                    "mode": "archive",
                    "include_paths": ["skills/alice/calendar"],
                    "registry_archive_mirror": True,
                }
            )
        )[0]
        record = SkillRecord(
            source=archive,
            repository=archive.url,
            commit="0" * 40,
            source_path="skills/alice/calendar",
            skill_root=ROOT,
            name="calendar",
        )
        self.assertTrue(record.registry_archive_mirror)

        schema = json.loads(
            (ROOT / "schemas/skill-atlas.schema.json").read_text(encoding="utf-8")
        )
        provenance = schema["properties"]["provenance"]
        self.assertIn("registry_archive_mirror", provenance["required"])
        self.assertEqual(
            {"type": "boolean"},
            provenance["properties"]["registry_archive_mirror"],
        )

    def test_generic_archive_mirror_cannot_be_downgraded_on_skill_record(self):
        archive = load_sources(
            self._write_sources(
                {
                    "id": "owner/archive",
                    "url": "https://github.com/owner/archive",
                    "mode": "archive",
                    "include_paths": ["skills/alice/calendar"],
                    "registry_archive_mirror": True,
                }
            )
        )[0]
        record = SkillRecord(
            source=archive,
            repository=archive.url,
            commit="0" * 40,
            source_path="skills/alice/calendar",
            skill_root=ROOT,
            name="calendar",
            registry_archive_mirror=False,
        )
        self.assertTrue(record.registry_archive_mirror)

        regular = load_sources(
            self._write_sources(
                {
                    "id": "owner/regular",
                    "url": "https://github.com/owner/regular",
                    "mode": "direct",
                }
            )
        )[0]
        regular_record = SkillRecord(
            source=regular,
            repository=regular.url,
            commit="0" * 40,
            source_path="skills/example",
            skill_root=ROOT,
            name="example",
        )
        self.assertFalse(regular_record.registry_archive_mirror)

    def test_clawhub_registry_is_separate_strict_and_safe_by_default(self):
        registry = load_registry(ROOT / "config/clawhub.json")

        self.assertEqual("clawhub", registry.id)
        self.assertEqual("https://clawhub.ai", registry.base_url)
        self.assertEqual(
            "VoltAgent/awesome-openclaw-skills", registry.index_source_id
        )
        self.assertTrue(registry.non_suspicious_only)
        self.assertEqual(55 * 1024 * 1024, registry.max_download_bytes)
        self.assertEqual(10_000, registry.max_files)
        self.assertEqual(200, registry.max_compression_ratio)

    def test_registry_rejects_nonofficial_base_url_and_unsafe_limits(self):
        payload = json.loads((ROOT / "config/clawhub.json").read_text())
        payload["base_url"] = "https://mirror.example"
        with self.assertRaisesRegex(ValueError, "official ClawHub"):
            load_registry(self.write_registry(payload))

        invalid_values = {
            "non_suspicious_only": False,
            "request_timeout_seconds": float("inf"),
            "max_workers": 65,
            "max_attempts": 0,
            "max_download_bytes": 0,
            "max_github_archive_bytes": True,
            "max_uncompressed_bytes": -1,
            "max_github_uncompressed_bytes": 0,
            "max_files": 0,
            "max_compression_ratio": False,
        }
        original = json.loads((ROOT / "config/clawhub.json").read_text())
        for field, value in invalid_values.items():
            with self.subTest(field=field, value=value):
                mutated = dict(original)
                mutated[field] = value
                with self.assertRaises(ValueError):
                    load_registry(self.write_registry(mutated))

    def test_registry_rejects_noncanonical_index_source_id(self):
        payload = json.loads((ROOT / "config/clawhub.json").read_text())
        payload["index_source_id"] = "owner/alternate-index"

        with self.assertRaisesRegex(ValueError, "frozen VoltAgent"):
            load_registry(self.write_registry(payload))

    def test_registry_requires_exact_fields(self):
        payload = json.loads((ROOT / "config/clawhub.json").read_text())
        payload["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "fields"):
            load_registry(self.write_registry(payload))

        payload = json.loads((ROOT / "config/clawhub.json").read_text())
        del payload["max_files"]
        with self.assertRaisesRegex(ValueError, "fields"):
            load_registry(self.write_registry(payload))

    def test_schema_requires_review_without_license_and_evidence(self):
        schema = json.loads(
            (ROOT / "schemas/skill-atlas.schema.json").read_text(encoding="utf-8")
        )
        provenance = schema["properties"]["provenance"]
        license_schema = provenance["properties"]["license"]
        self.assertEqual(
            {"type": ["string", "null"], "minLength": 1},
            license_schema,
        )
        self.assertEqual(
            {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
            provenance["properties"]["license_evidence"],
        )

        review_rule = provenance["allOf"][0]
        self.assertEqual(
            {"properties": {"redistribution_review": {"const": False}}},
            review_rule["if"],
        )
        self.assertEqual(["license_evidence"], review_rule["then"]["required"])
        self.assertEqual(
            {"type": "string", "minLength": 1},
            review_rule["then"]["properties"]["license"],
        )
        self.assertEqual(
            1,
            review_rule["then"]["properties"]["license_evidence"]["minItems"],
        )

    def test_rejects_non_repository_github_urls(self):
        invalid_urls = [
            "http://github.com/owner/repo",
            "https://example.com/owner/repo",
            "https://github.com/owner",
            "https://github.com/owner/repo/tree/main",
            "https://github.com/owner/repo/",
            "https://github.com/owner/repo?tab=readme",
            "https://github.com/owner/repo#readme",
        ]
        for url in invalid_urls:
            with self.subTest(url=url), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "sources.json"
                path.write_text(
                    json.dumps(
                        {
                            "sources": [
                                {"id": "owner/repo", "url": url, "mode": "direct"}
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError):
                    load_sources(path)

    def test_rejects_wrong_source_field_types(self):
        invalid_fields = [
            {"include_paths": "skills"},
            {"include_paths": ["skills", 3]},
            {"exclude_paths": ".git"},
            {"exclude_paths": [".git", False]},
            {"redistribution_review": "false"},
            {"registry_archive_mirror": "true"},
        ]
        for invalid in invalid_fields:
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                source = {
                    "id": "owner/repo",
                    "url": "https://github.com/owner/repo",
                    "mode": "direct",
                    **invalid,
                }
                path = Path(directory) / "sources.json"
                path.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_sources(path)

    def test_rejects_noncanonical_include_and_exclude_paths(self):
        invalid_fields = [
            {"include_paths": ["/absolute"]},
            {"include_paths": ["../outside"]},
            {"include_paths": ["skills/../outside"]},
            {"include_paths": ["skills\\windows"]},
            {"include_paths": ["skills\x00hidden"]},
            {"include_paths": ["skills/"]},
            {"exclude_paths": ["../outside"]},
            {"exclude_paths": ["/absolute"]},
            {"exclude_paths": ["vendor\\windows"]},
        ]
        for invalid in invalid_fields:
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                source = {
                    "id": "owner/repo",
                    "url": "https://github.com/owner/repo",
                    "mode": "direct",
                    **invalid,
                }
                path = Path(directory) / "sources.json"
                path.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_sources(path)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "id": "owner/repo",
                                "url": "https://github.com/owner/repo",
                                "mode": "direct",
                                "include_paths": ["."],
                                "exclude_paths": [".git", "vendor/generated"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            source = load_sources(path)[0]
            self.assertEqual(["."], source.include_paths)
            self.assertEqual([".git", "vendor/generated"], source.exclude_paths)

    def _write_sources(self, source):
        path = self.tempdir / "sources.json"
        path.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()

import json
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from skill_atlas.config import load_sources, load_taxonomy
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

ARCHIVE_SOURCES = ["openclaw/skills"]

REFERENCE_SOURCES = [
    "agentskills/agentskills",
    "openclaw/clawhub",
    "cisco-ai-defense/skill-scanner",
    "datalayer/agent-skills",
]

EXPECTED_SOURCES = {
    **{source_id: "direct" for source_id in DIRECT_SOURCES},
    **{source_id: "index" for source_id in INDEX_SOURCES},
    **{source_id: "archive" for source_id in ARCHIVE_SOURCES},
    **{source_id: "reference" for source_id in REFERENCE_SOURCES},
}


class ConfigTests(unittest.TestCase):
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
        self.assertEqual(81, len(sources))
        self.assertEqual(expected, actual)
        self.assertEqual(
            Counter({"direct": 68, "index": 8, "archive": 1, "reference": 4}),
            Counter(item.mode for item in sources),
        )

    def test_registry_archive_mirror_flows_from_source_to_skill_record_and_schema(self):
        sources = load_sources(ROOT / "config/sources.json")
        mirror_ids = {item.id for item in sources if item.registry_archive_mirror}
        self.assertEqual({"openclaw/skills"}, mirror_ids)

        archive = next(item for item in sources if item.id == "openclaw/skills")
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

    def test_registry_archive_mirror_cannot_be_downgraded_on_skill_record(self):
        sources = load_sources(ROOT / "config/sources.json")
        archive = next(item for item in sources if item.id == "openclaw/skills")
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

        regular = next(item for item in sources if item.id == "anthropics/skills")
        regular_record = SkillRecord(
            source=regular,
            repository=regular.url,
            commit="0" * 40,
            source_path="skills/example",
            skill_root=ROOT,
            name="example",
        )
        self.assertFalse(regular_record.registry_archive_mirror)

    def test_schema_requires_true_mirror_marker_for_openclaw_repository(self):
        schema = json.loads(
            (ROOT / "schemas/skill-atlas.schema.json").read_text(encoding="utf-8")
        )
        provenance = schema["properties"]["provenance"]
        repository_url = "https://github.com/openclaw/skills"
        self.assertIsNotNone(
            re.fullmatch(provenance["properties"]["repository"]["pattern"], repository_url)
        )

        mirror_rule = provenance["allOf"][1]
        self.assertEqual(
            {"properties": {"repository": {"const": repository_url}}},
            mirror_rule["if"],
        )
        self.assertEqual(
            {"properties": {"registry_archive_mirror": {"const": True}}},
            mirror_rule["then"],
        )

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


if __name__ == "__main__":
    unittest.main()

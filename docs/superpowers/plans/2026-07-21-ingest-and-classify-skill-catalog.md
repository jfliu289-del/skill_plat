# Skill Catalog Ingestion and Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible pipeline that pulls every verified Skill from the surveyed GitHub sources, preserves upstream contents, routes each Skill into the approved six-group/twenty-category tree, and writes cross-category tags at one fixed location in every Skill folder.

**Architecture:** A Python 3.9 command-line package reads versioned taxonomy and source manifests, synchronizes shallow Git mirrors into an ignored cache, discovers real `SKILL.md` folders without executing upstream code, classifies each Skill with deterministic weighted rules, and materializes a provenance-pinned catalog. Upstream `SKILL.md` bytes stay unchanged; every copied Skill receives a sibling `skill-atlas.json`. Central lock, duplicate, unresolved-source, and validation reports make the import repeatable and auditable.

**Tech Stack:** Python 3.9, PyYAML 6.x, standard-library `unittest`, Git 2.x, JSON Schema draft 2020-12.

## Global Constraints

- Use C00 through C19 and the six navigation groups from `docs/superpowers/specs/2026-07-21-skill-encyclopedia-classification-design.md`.
- Give every Skill exactly one primary category and zero or more secondary categories, tasks, stages, artifacts, domains, and audiences.
- Preserve every upstream `SKILL.md` byte-for-byte.
- Write catalog metadata only to `<skill-root>/skill-atlas.json`, adjacent to `SKILL.md`.
- Never execute upstream scripts, Git hooks, installers, tests, submodules, or binaries.
- Pin every imported source to a commit SHA and record its repository URL and original relative path.
- Copy the complete Skill folder except Git internals and unsafe symlinks; record every exclusion.
- Keep exact duplicate source variants, but group them by content hash in `reports/duplicates.json`.
- Treat awesome lists and registries as discovery indexes, not as owners of linked Skills.
- Record unknown/restrictive licenses explicitly; never imply redistribution permission without evidence.
- Make classification deterministic for a fixed source commit, taxonomy version, and classifier version.
- Accept only HTTPS GitHub production sources.
- Mark OpenClaw archive entries as `registry_archive_mirror` and never present them as author-canonical repositories.
- Set `redistribution_review=true` when no standard repository- or Skill-level license evidence is found.

---

## File Map

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, Python floor, PyYAML dependency |
| `.gitignore` | Ignore virtual environment, upstream cache, staging, and bytecode |
| `config/taxonomy.json` | Groups, categories, controlled tags, keyword weights, risk cues |
| `config/sources.json` | Direct repositories, indexes, reference repositories, source defaults |
| `schemas/skill-atlas.schema.json` | Sidecar schema |
| `src/skill_atlas/models.py` | Typed source, Skill, classification, and import records |
| `src/skill_atlas/config.py` | Load and validate configuration |
| `src/skill_atlas/frontmatter.py` | Parse Skill metadata without changing raw bytes |
| `src/skill_atlas/classifier.py` | Deterministic primary and cross-tag classification |
| `src/skill_atlas/git_sources.py` | Safe clone/update and commit pinning |
| `src/skill_atlas/discovery.py` | Skill discovery and index URL expansion |
| `src/skill_atlas/materialize.py` | Safe copy, routing, hashing, sidecar generation |
| `src/skill_atlas/validate.py` | Catalog invariants and reports |
| `src/skill_atlas/cli.py` | `sync`, `build`, `validate`, `report`, `all` |
| `tests/` | Unit and local-Git integration tests |
| `skills/` | Generated catalog |
| `licenses/` | Repository-level license snapshots |
| `reports/` | Locks, catalog index, duplicates, unresolved items, validation |

---

### Task 1: Package Skeleton, Taxonomy, Sources, and Schema

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `config/taxonomy.json`
- Create: `config/sources.json`
- Create: `schemas/skill-atlas.schema.json`
- Create: `src/skill_atlas/__init__.py`
- Create: `src/skill_atlas/models.py`
- Create: `src/skill_atlas/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- `load_taxonomy(path: Path) -> Taxonomy`
- `load_sources(path: Path) -> list[SourceSpec]`
- Dataclasses: `Category`, `Taxonomy`, `SourceSpec`, `SkillRecord`, `Classification`, `ImportResult`

- [ ] **Step 1: Write failing configuration tests**

```python
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
        self.assertTrue(all(item.mode in {"direct", "index", "archive", "reference"} for item in sources))
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_config -v`

Expected: FAIL because package and configuration are absent.

- [ ] **Step 3: Implement configuration and schema**

Encode this exact group routing:

```json
{
  "A": ["C01", "C02", "C03", "C04", "C05"],
  "B": ["C06", "C07", "C08", "C09", "C10", "C19"],
  "C": ["C11", "C12", "C13", "C14"],
  "D": ["C15", "C16"],
  "E": ["C17", "C18"],
  "F": ["C00"]
}
```

Require sidecar keys `schema_version`, `taxonomy_version`, `classifier_version`, `provenance`, `classification`, and `integrity`. Classification requires primary/secondary categories, tasks, stages, artifacts, domains, audiences, risk level, confidence, review flag, and reasons. Provenance requires repository, 40-character commit, source path, and license. Integrity requires SHA-256 content and SKILL.md hashes.

Populate `config/sources.json` with the following frozen inventory.

Direct Skill sources:

```text
anthropics/skills                         openai/plugins
github/awesome-copilot                    vercel-labs/agent-skills
huggingface/skills                        NVIDIA/skills
obra/superpowers                          trailofbits/skills
openai/skills                             microsoft/skills
dotnet/skills                             google/skills
cloudflare/skills                         supabase/agent-skills
getsentry/skills                          grafana/skills
addyosmani/agent-skills                   antfu/skills
softaworks/agent-toolkit                  wshobson/agents
OthmanAdi/planning-with-files             gotalab/cc-sdd
a5c-ai/babysitter                         semgrep/skills
ljagiello/ctf-skills                      antonbabenko/terraform-skill
K-Dense-AI/scientific-agent-skills        claude-office-skills/skills
googleworkspace/cli                       google-labs-code/stitch-skills
adobe/skills                              markdown-viewer/skills
michaelboeding/skills                     GarethManning/education-agent-skills
CaseMark/skills                           OctagonAI/skills
phuryn/pm-skills                          product-on-purpose/pm-skills
RefoundAI/lenny-skills                    ncklrs/startup-os-skills
coreyhaines31/marketingskills             NEON-Rutger/B2B-revops-skills
alirezarezvani/claude-skills              borghei/Claude-Skills
lyndonkl/claude                           openclaw/agent-skills
vercel-labs/skills                        remotion-dev/skills
WordPress/agent-skills                    apify/agent-skills
hashicorp/agent-skills                    elastic/agent-skills
ClickHouse/agent-skills                   laravel/agent-skills
BuilderIO/skills                          firebase/agent-skills
callstackincubator/agent-skills           TheQtCompanyRnD/agent-skills
Automattic/agent-skills                   Memento-Teams/Memento-Skills
SynaLinks/synalinks-skills                Agentchengfeng/chengfeng-videocut-skills
JimLiu/baoyu-skills                       KKKKhazix/khazix-skills
Agents365-ai/drawio-skill                 ningzimu/codex-ppt-skill
SamurAIGPT/Generative-Media-Skills        kepano/obsidian-skills
```

Discovery indexes:

```text
VoltAgent/awesome-openclaw-skills         VoltAgent/awesome-agent-skills
skillmatic-ai/awesome-agent-skills        heilcheng/awesome-agent-skills
danielrosehill/Useful-AI-Agent-Skills     ComposioHQ/awesome-claude-skills
sickn33/agentic-awesome-skills            InternScience/Awesome-Scientific-Skills
```

Archive source: `openclaw/skills`, populated only from unique owner/slug paths resolved from the pinned VoltAgent index. Reference-only sources: `agentskills/agentskills`, `openclaw/clawhub`, `cisco-ai-defense/skill-scanner`, and `datalayer/agent-skills`. Record inventory `SKILL.md` counts as non-binding audit hints, not success assertions.

- [ ] **Step 4: Run GREEN**

Run: `PYTHONPATH=src python3 -m unittest tests.test_config -v`

Expected: two tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore config schemas src/skill_atlas tests/test_config.py
git commit -m "feat: define skill catalog taxonomy and sources"
```

---

### Task 2: Frontmatter Parsing and Classification

**Files:**
- Create: `src/skill_atlas/frontmatter.py`
- Create: `src/skill_atlas/classifier.py`
- Create: `tests/fixtures/skills/code-review/SKILL.md`
- Create: `tests/fixtures/skills/literature-review/SKILL.md`
- Create: `tests/fixtures/skills/browser-crm/SKILL.md`
- Test: `tests/test_frontmatter.py`
- Test: `tests/test_classifier.py`

**Interfaces:**
- `parse_skill(path: Path) -> ParsedSkill`
- `classify(skill: ParsedSkill, taxonomy: Taxonomy, source: SourceSpec) -> Classification`

- [ ] **Step 1: Write failing parser tests**

```python
class FrontmatterTests(unittest.TestCase):
    def test_parses_folded_description_without_mutating_bytes(self):
        path = FIXTURES / "skills/code-review/SKILL.md"
        before = path.read_bytes()
        parsed = parse_skill(path)
        self.assertEqual("reviewing-code", parsed.name)
        self.assertIn("pull request", parsed.description.lower())
        self.assertEqual(before, path.read_bytes())

    def test_rejects_missing_frontmatter(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text("# Missing metadata\n", encoding="utf-8")
            with self.assertRaises(SkillParseError):
                parse_skill(path)
```

- [ ] **Step 2: Run parser RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_frontmatter -v`

Expected: FAIL because the parser is absent.

- [ ] **Step 3: Implement safe parsing**

Read bytes once, require opening and closing `---`, parse YAML with `yaml.safe_load`, require non-empty string `name` and `description`, decode classification text with replacement, and retain raw bytes plus SHA-256. Never write the source file.

- [ ] **Step 4: Run parser GREEN**

Run: `PYTHONPATH=src python3 -m unittest tests.test_frontmatter -v`

Expected: PASS.

- [ ] **Step 5: Write failing category-boundary tests**

```python
class ClassifierTests(unittest.TestCase):
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

    def test_output_is_deterministic_and_sorted(self):
        first = self.classify_fixture("code-review")
        second = self.classify_fixture("code-review")
        self.assertEqual(first, second)
        self.assertEqual(sorted(set(first.tasks)), first.tasks)
```

- [ ] **Step 6: Run classifier RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_classifier -v`

Expected: FAIL because classification is absent.

- [ ] **Step 7: Implement weighted rules**

Build searchable text from name, description, headings, and source path. Score exact phrases before tokens; use source defaults only when text evidence is weak. Resolve ties by exact-phrase score then stable category ID. Set `needs_review=true` when confidence is below `0.55` or the normalized top-two difference is below `0.08`. Credentials, publishing, deployment, or external-account writes are at least R3; medical, legal, financial, and offensive-security decisions are R4.

- [ ] **Step 8: Run GREEN and commit**

Run: `PYTHONPATH=src python3 -m unittest tests.test_frontmatter tests.test_classifier -v`

Expected: all tests PASS.

```bash
git add src/skill_atlas/frontmatter.py src/skill_atlas/classifier.py tests
git commit -m "feat: classify skills with deterministic cross tags"
```

---

### Task 3: Safe Git Sync, Skill Discovery, and Index Expansion

**Files:**
- Create: `src/skill_atlas/git_sources.py`
- Create: `src/skill_atlas/discovery.py`
- Test: `tests/test_git_sources.py`
- Test: `tests/test_discovery.py`

**Interfaces:**
- `sync_source(spec: SourceSpec, cache_root: Path) -> ResolvedSource`
- `discover_skill_roots(repo_root: Path, include_paths: list[str], exclude_paths: list[str]) -> list[Path]`
- `discover_github_targets(index_root: Path) -> list[DiscoveredTarget]`
- `discover_openclaw_archive_paths(index_root: Path) -> list[str]`

- [ ] **Step 1: Write failing local-Git tests**

```python
class GitSourceTests(unittest.TestCase):
    def test_sync_pins_commit_without_submodules(self):
        remote, expected_sha = make_local_fixture_repository(self.tempdir)
        resolved = sync_source(SourceSpec.for_test(remote.as_uri()), self.cache)
        self.assertEqual(expected_sha, resolved.commit)
        self.assertTrue((resolved.checkout / "skills/example/SKILL.md").is_file())
        self.assertFalse((resolved.checkout / "vendor/submodule/.git").exists())

    def test_rejects_non_https_production_source(self):
        source = SourceSpec(id="bad", url="http://example.com/repo", mode="direct")
        with self.assertRaises(SourceSecurityError):
            sync_source(source, self.cache)
```

- [ ] **Step 2: Run sync RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_git_sources -v`

Expected: FAIL.

- [ ] **Step 3: Implement sync**

Use subprocess argument lists, not shell strings. Clone direct sources with `git -c core.hooksPath=/dev/null clone --depth 1 --no-recurse-submodules`. Clone archives with `--filter=blob:none --no-checkout`, initialize sparse checkout, and check out only validated index-derived paths. Existing caches fetch then detach at the configured ref. Return `git rev-parse HEAD`. Sanitize cache names to `owner--repo`.

- [ ] **Step 4: Run sync GREEN**

Run: `PYTHONPATH=src python3 -m unittest tests.test_git_sources -v`

Expected: PASS.

- [ ] **Step 5: Write failing discovery tests**

```python
class DiscoveryTests(unittest.TestCase):
    def test_finds_only_exact_uppercase_skill_md(self):
        roots = discover_skill_roots(FIXTURE_REPO, ["."], ["vendor", ".git"])
        self.assertEqual([FIXTURE_REPO / "skills/valid"], roots)

    def test_many_tree_links_become_one_repo_target(self):
        targets = discover_github_targets(FIXTURE_INDEX)
        target = next(item for item in targets if item.url == "https://github.com/openclaw/skills")
        self.assertEqual(
            ["skills/alice/calendar", "skills/bob/research"],
            target.include_paths,
        )

    def test_rejects_tree_path_traversal(self):
        self.assertIsNone(parse_github_tree_url(
            "https://github.com/a/b/tree/main/../../etc"
        ))

    def test_maps_clawskills_links_to_archive_paths_and_deduplicates(self):
        paths = discover_openclaw_archive_paths(FIXTURE_OPENCLAW_INDEX)
        self.assertEqual(
            ["skills/alice/calendar", "skills/bob/research"],
            paths,
        )
```

- [ ] **Step 6: Run discovery RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_discovery -v`

Expected: FAIL.

- [ ] **Step 7: Implement discovery**

Do not follow symlink directories. Exclude Git internals and configured paths. Accept only exact `SKILL.md`. Parse Markdown/plain HTTPS GitHub repository and tree URLs, normalize `.git`, validate relative paths, group tree paths by repository, deduplicate, and preserve the index as discovery provenance. For the pinned VoltAgent OpenClaw index, strictly parse `clawskills.sh/skills/<owner>/<slug>` and `clawhub.ai/<owner>/<slug>`, convert them to `skills/<owner>/<slug>`, deduplicate, and write malformed links to `unresolved.json`.

- [ ] **Step 8: Run GREEN and commit**

Run: `PYTHONPATH=src python3 -m unittest tests.test_git_sources tests.test_discovery -v`

Expected: all tests PASS.

```bash
git add src/skill_atlas/git_sources.py src/skill_atlas/discovery.py tests
git commit -m "feat: safely synchronize and discover skill sources"
```

---

### Task 4: Materialization, Sidecars, and Duplicates

**Files:**
- Create: `src/skill_atlas/materialize.py`
- Test: `tests/test_materialize.py`

**Interfaces:**
- `catalog_path(record, classification, taxonomy) -> Path`
- `materialize(record, destination_root, classification) -> ImportResult`
- `cluster_duplicates(results) -> dict[str, list[str]]`
- Path: `skills/<group-id>-<slug>/<category-id>-<slug>/<owner>/<repo>/<source-parent-key>/<original-skill-directory>/`

- [ ] **Step 1: Write failing materialization tests**

```python
class MaterializeTests(unittest.TestCase):
    def test_routes_and_preserves_skill_md(self):
        before = (self.source_skill / "SKILL.md").read_bytes()
        result = materialize(self.record, self.output, self.classification)
        self.assertEqual(
            Path("skills/B-software-systems-automation/C07-debugging-testing-quality/acme/tools/reviews/reviewing-code"),
            result.relative_path,
        )
        self.assertEqual(before, (self.output / result.relative_path / "SKILL.md").read_bytes())

    def test_sidecar_contains_cross_tags_and_integrity(self):
        result = materialize(self.record, self.output, self.classification)
        data = json.loads((self.output / result.relative_path / "skill-atlas.json").read_text())
        self.assertEqual("C07", data["classification"]["primary_category"])
        self.assertEqual(["C06"], data["classification"]["secondary_categories"])
        self.assertEqual(self.record.commit, data["provenance"]["commit"])
        self.assertRegex(data["integrity"]["content_hash"], r"^[0-9a-f]{64}$")

    def test_escaping_symlink_is_excluded(self):
        link = self.source_skill / "references/escape"
        link.parent.mkdir(exist_ok=True)
        link.symlink_to("../../../../secret")
        result = materialize(self.record, self.output, self.classification)
        self.assertIn("references/escape", result.excluded_paths)
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_materialize -v`

Expected: FAIL.

- [ ] **Step 3: Implement safe deterministic copy**

Copy paths lexicographically. Never follow symlinks; accept one only if its resolved target remains inside the Skill root, otherwise exclude it. Hash relative path, file mode, and bytes for every upstream file before sidecar creation. Serialize sidecars as sorted, two-space UTF-8 JSON with a final newline. Keep duplicate variants and cluster by content hash.

- [ ] **Step 4: Run GREEN and commit**

Run: `PYTHONPATH=src python3 -m unittest tests.test_materialize -v`

Expected: PASS.

```bash
git add src/skill_atlas/materialize.py tests/test_materialize.py
git commit -m "feat: materialize catalog skills with provenance tags"
```

---

### Task 5: CLI, Atomic Builds, and Validation

**Files:**
- Create: `src/skill_atlas/validate.py`
- Create: `src/skill_atlas/cli.py`
- Create: `src/skill_atlas/__main__.py`
- Test: `tests/test_validate.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- `python -m skill_atlas sync|build|validate|report|all`
- `validate_catalog(root: Path, taxonomy: Taxonomy) -> ValidationReport`

- [ ] **Step 1: Write failing validator tests**

```python
class ValidateTests(unittest.TestCase):
    def test_valid_catalog_has_no_failures(self):
        report = validate_catalog(VALID_CATALOG, self.taxonomy)
        self.assertEqual([], report.failures)
        self.assertEqual(2, report.skill_count)

    def test_detects_missing_sidecar_and_category_path_mismatch(self):
        codes = {item.code for item in validate_catalog(BROKEN_CATALOG, self.taxonomy).failures}
        self.assertIn("missing-sidecar", codes)
        self.assertIn("category-path-mismatch", codes)

    def test_detects_skill_md_hash_mismatch(self):
        codes = {item.code for item in validate_catalog(TAMPERED_CATALOG, self.taxonomy).failures}
        self.assertIn("skill-md-hash-mismatch", codes)
```

- [ ] **Step 2: Run validator RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_validate -v`

Expected: FAIL.

- [ ] **Step 3: Implement validator**

Check one sidecar per Skill, schema conformance, group/category path consistency, controlled vocabularies, 40-character commit SHA, integrity hashes, central-record paths, and duplicate-cluster consistency. Write stable JSON with failures and counts.

- [ ] **Step 4: Write failing end-to-end local CLI test**

```python
class CliTests(unittest.TestCase):
    def test_all_builds_catalog_lock_and_reports_atomically(self):
        completed = run_cli("all", config=self.fixture_config, root=self.output)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(3, count_files(self.output / "skills", "SKILL.md"))
        self.assertEqual(3, count_files(self.output / "skills", "skill-atlas.json"))
        self.assertTrue((self.output / "reports/sources.lock.json").is_file())
        validation = json.loads((self.output / "reports/validation.json").read_text())
        self.assertEqual([], validation["failures"])
```

- [ ] **Step 5: Run CLI RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_cli -v`

Expected: FAIL.

- [ ] **Step 6: Implement orchestration**

`sync` resolves direct sources and expands indexes into a unique source graph. `build` writes into a sibling staging directory and atomically replaces the previous generated tree only after reports are complete. `validate` is read-only. `report --summary` prints imported, duplicate, parse-failure, inaccessible, unknown-license, unsafe-symlink, and low-confidence counts. `all` returns nonzero for direct-source or validation failures; inaccessible index-derived sources remain unresolved without blocking unrelated sources.

- [ ] **Step 7: Run full GREEN and commit**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`

Expected: all tests PASS without network access.

```bash
git add src/skill_atlas/validate.py src/skill_atlas/cli.py src/skill_atlas/__main__.py tests
git commit -m "feat: add reproducible catalog build and validation"
```

---

### Task 6: Full Import and Audit

**Files:**
- Generate: `skills/**`
- Generate: `licenses/**`
- Generate: `reports/sources.lock.json`
- Generate: `reports/catalog.jsonl`
- Generate: `reports/duplicates.json`
- Generate: `reports/unresolved.json`
- Generate: `reports/validation.json`
- Create: `README.md`

- [ ] **Step 1: Install declared dependencies**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

Expected: package installs with PyYAML 6.x.

- [ ] **Step 2: Run pre-import tests**

Run: `.venv/bin/python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 3: Execute the full import**

Run: `.venv/bin/python -m skill_atlas all --config config --root . --cache .cache/upstreams`

Expected: accessible sources are pinned, valid Skills are routed under `skills/`, each has one sidecar, and all reports exist.

- [ ] **Step 4: Audit exceptions**

Run: `.venv/bin/python -m skill_atlas report --root . --summary`

Expected: separate counts for imported, duplicate, parse failure, inaccessible source, unknown license, unsafe symlink, and low-confidence classification.

- [ ] **Step 5: Verify deterministic rebuild from the lock**

```bash
find skills licenses reports -type f -print0 | sort -z | xargs -0 shasum -a 256 > /tmp/skill-atlas-before.sha256
.venv/bin/python -m skill_atlas all --config config --root . --cache .cache/upstreams --locked
find skills licenses reports -type f -print0 | sort -z | xargs -0 shasum -a 256 > /tmp/skill-atlas-after.sha256
diff -u /tmp/skill-atlas-before.sha256 /tmp/skill-atlas-after.sha256
```

Expected: no diff.

- [ ] **Step 6: Write repository README**

Explain the taxonomy tree, leaf path convention, fixed sidecar, source lock, license caveat, no-upstream-execution rule, rebuild/validation commands, generated counts, and links to the design and plan.

- [ ] **Step 7: Run final verification**

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m skill_atlas validate --root . --report reports/validation.json
git diff --check
git status --short
```

Expected: all tests pass, structural failures are zero, diff check is clean, and status contains only intended code, configuration, documentation, catalog, license, and report files.

- [ ] **Step 8: Commit the catalog**

```bash
git add README.md skills licenses reports config/sources.json
git commit -m "data: import and classify surveyed skill catalog"
```

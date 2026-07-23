# ClawHub Registry Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dead `openclaw/skills` archive with an official ClawHub adapter that imports every currently public, exactly owned, clean, complete bundle referenced by the frozen VoltAgent index.

**Architecture:** Keep Git sources and the ClawHub registry as separate trust domains. A registry adapter parses immutable index claims, resolves owner/slug/version through public safe APIs, validates hosted ZIP or `public-github` handoff contents against the official per-file manifest, and exposes verified local Skill roots to the existing classifier/materializer. Git commits remain in `sources.lock.json`; owner/slug/version, archive hashes, manifests, security state, and failures live in a separate deterministic `clawhub.lock.json`.

**Tech Stack:** Python 3.9 standard library (`urllib`, `zipfile`, `hashlib`, `concurrent.futures`), PyYAML 6.x, `unittest`, JSON Schema draft 2020-12, Git 2.x.

## Global Constraints

- Implement the approved design in `docs/superpowers/specs/2026-07-22-clawhub-registry-adapter-design.md`.
- Use only `https://clawhub.ai` public v1 APIs and official GitHub/codeload handoffs; never recover deleted content from a historical mirror.
- Import only entries discovered from the pinned `VoltAgent/awesome-openclaw-skills` checkout, not the entire live ClawHub catalog.
- Resolve legacy links by exact search result comparison; never split owner and slug at the first hyphen and never accept a replacement owner.
- Require `nonSuspiciousOnly=true`, acceptable moderation fields, and version `security.status == "clean"`.
- Fix owner, slug, explicit version, version metadata hash, archive hash, and the complete path/size/SHA-256 file manifest.
- Preserve every official version-manifest file byte-for-byte; `_meta.json` is registry metadata and is not materialized as upstream Skill content.
- Reject unsafe or noncanonical archive paths, special files, symlinks, encrypted entries, duplicate normalized paths, Unicode/casefold collisions, ZIP bombs, extra files, missing files, and all size/hash mismatches.
- Never execute upstream scripts, hooks, installers, tests, submodules, or binaries.
- Keep `sources.lock.json` Git-only and add deterministic `reports/clawhub.lock.json` for registry entries.
- Locked registry rebuilds never select latest or a different owner, but must recheck current public visibility and security before using cached content.
- Treat a locked recheck only as a gate: when identity remains public and clean, retain the locked security/provenance bytes instead of replacing them with mutable scanner timestamps or prose.
- Expected unavailable/hidden/blocked/owner-mismatch claims are unresolved and nonblocking; malformed API, exhausted transport, archive security, cache, lock, or integrity failures are blocking.
- Keep catalog publication sibling-staged, validated, atomic, and rollback-safe.
- Preserve the existing six-group/twenty-category routing and write all cross-category metadata only to the adjacent `skill-atlas.json`.
- Use TDD for every production behavior: write one failing test, run it and observe the expected failure, add minimal implementation, then run the focused and full suites.
- Write live progress only to stderr, every 100 normalized claims, without tokens, temporary paths, request identifiers, or other nondeterministic response data; stdout remains one parseable JSON result.

---

## File Map

| Path | Responsibility |
|---|---|
| `config/clawhub.json` | Official registry endpoint, frozen index id, concurrency, retry, download, ZIP, and GitHub archive limits |
| `config/sources.json` | Git-only inventory; remove the dead `openclaw/skills` archive and pin the VoltAgent index ref |
| `src/skill_atlas/models.py` | Registry configuration, claim, file manifest, security/provenance, bundle, and registry outcome dataclasses |
| `src/skill_atlas/config.py` | Strict ClawHub configuration loader without weakening Git source validation |
| `src/skill_atlas/git_sources.py` | Resolve a pinned 40-character source ref from an empty cache without misusing `git clone --branch` |
| `src/skill_atlas/discovery.py` | Pure frozen-index claim parser with stable unresolved results |
| `src/skill_atlas/clawhub.py` | Public API transport, safe exact resolution, explicit-version locking, retries, and registry orchestration |
| `src/skill_atlas/zip_bundle.py` | Bounded download, safe ZIP inspection, exact manifest verification, extraction, and atomic cache publication |
| `src/skill_atlas/materialize.py` | ClawHub catalog route and tagged sidecar provenance |
| `src/skill_atlas/classifier.py` | Classify from explicit default-category values rather than a Git-only `SourceSpec` |
| `schemas/skill-atlas.schema.json` | Strict Git/ClawHub provenance `oneOf` |
| `src/skill_atlas/validate.py` | Registry provenance, route, manifest, and materialized file validation |
| `src/skill_atlas/pipeline.py` | Registry sync/build merge, lock/report generation, blocking semantics, and summary counts |
| `src/skill_atlas/cli.py` | Load/inject registry adapter and consume both locks for `sync`, `build`, and `all` |
| `src/skill_atlas/audit.py` | Verify claim/download/import count equations and lock/report referential integrity |
| `tests/fixtures/clawhub/` | Frozen official-response fixtures and synthetic OpenAPI-derived handoff fixtures |
| `tests/test_clawhub.py` | Resolution, moderation, versions, lock, retry, and cache-reuse tests |
| `tests/test_zip_bundle.py` | ZIP and handoff archive security/integrity tests |
| `tests/test_config.py` | Git/registry configuration contract tests |
| `tests/test_discovery.py` | Legacy/canonical claim parsing and unresolved tests |
| `tests/test_materialize.py` | Registry route and sidecar tests |
| `tests/test_validate.py` | Registry schema/path/file-manifest validation tests |
| `tests/test_cli.py` | Offline end-to-end Git plus registry, locked replay, failure, and atomic-publication tests |
| `tests/test_audit.py` | Stable count equations and report relationship tests |

---

### Task 6: Registry Configuration, Models, and Frozen Index Claims

**Files:**
- Create: `config/clawhub.json`
- Modify: `config/sources.json`
- Modify: `src/skill_atlas/models.py`
- Modify: `src/skill_atlas/config.py`
- Modify: `src/skill_atlas/git_sources.py`
- Modify: `src/skill_atlas/discovery.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_git_sources.py`
- Modify: `tests/test_discovery.py`

**Interfaces:**
- `load_registry(path: Path) -> RegistrySpec`
- `discover_clawhub_claims(index_root: Path) -> RegistryDiscovery`
- `RegistryDiscovery.claims: Tuple[RegistryClaim, ...]` where the tuple may contain any number of immutable claims
- `RegistryDiscovery.unresolved: Tuple[Dict[str, object], ...]` where every item has `source_id` and `reason`
- `RegistryClaim(claimed_slug, claimed_owner, legacy_id, index_entries)`
- `registry_claim_id(claim: RegistryClaim) -> str`
- `GitSkillOrigin(repository, commit, source_path, source_id, default_categories, registry_archive_mirror)`
- `RegistrySkillOrigin(provenance, source_id="clawhub")`
- `SkillOrigin = Union[GitSkillOrigin, RegistrySkillOrigin]`

- [ ] **Step 1: Write failing registry configuration tests**

Add tests that require 80 Git sources, no archive source, a pinned VoltAgent ref, and a separately validated official registry:

```python
def test_git_inventory_drops_dead_openclaw_archive_and_pins_index(self):
    sources = load_sources(ROOT / "config/sources.json")
    self.assertEqual(80, len(sources))
    self.assertNotIn("openclaw/skills", {item.id for item in sources})
    index = next(item for item in sources if item.id == "VoltAgent/awesome-openclaw-skills")
    self.assertEqual("6afb5d4e3e6f36ff181a33b3b6f88054348bc70a", index.ref)

def test_clawhub_registry_is_separate_strict_and_safe_by_default(self):
    registry = load_registry(ROOT / "config/clawhub.json")
    self.assertEqual("clawhub", registry.id)
    self.assertEqual("https://clawhub.ai", registry.base_url)
    self.assertEqual("VoltAgent/awesome-openclaw-skills", registry.index_source_id)
    self.assertTrue(registry.non_suspicious_only)
    self.assertEqual(55 * 1024 * 1024, registry.max_download_bytes)
    self.assertEqual(10_000, registry.max_files)
    self.assertEqual(200, registry.max_compression_ratio)

def test_registry_rejects_nonofficial_base_url_and_unsafe_limits(self):
    payload = json.loads((ROOT / "config/clawhub.json").read_text())
    payload["base_url"] = "https://mirror.example"
    with self.assertRaisesRegex(ValueError, "official ClawHub"):
        load_registry(self.write_registry(payload))
```

Add a local Git regression test before changing synchronization:

```python
def test_empty_cache_checks_out_exact_commit_ref_detached(self):
    first = _commit(self.remote, "first")
    _commit(self.remote, "second")
    spec = SourceSpec.for_test(self.remote.as_uri())
    spec.ref = first
    resolved = sync_source(spec, self.cache)
    self.assertEqual(first, resolved.commit)
    self.assertEqual("", _git("branch", "--show-current", cwd=resolved.checkout))
```

- [ ] **Step 2: Run configuration RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_config -v
PYTHONPATH=src python3 -m unittest tests.test_git_sources.GitSourceTests.test_empty_cache_checks_out_exact_commit_ref_detached -v
```

Expected: configuration FAILS because `RegistrySpec`, `load_registry`, and `config/clawhub.json` do not exist and the Git inventory still contains the dead archive; the Git regression FAILS because the current empty-cache path passes the raw SHA to `git clone --branch`.

- [ ] **Step 3: Add exact typed registry configuration**

Add these immutable model fields:

```python
@dataclass(frozen=True)
class RegistrySpec:
    id: str
    base_url: str
    index_source_id: str
    non_suspicious_only: bool
    request_timeout_seconds: float
    max_workers: int
    max_attempts: int
    max_download_bytes: int
    max_github_archive_bytes: int
    max_uncompressed_bytes: int
    max_github_uncompressed_bytes: int
    max_files: int
    max_compression_ratio: int

@dataclass(frozen=True, order=True)
class RegistryIndexEntry:
    index_path: str
    label: str
    url: str

@dataclass(frozen=True)
class RegistryClaim:
    claimed_slug: str
    claimed_owner: Optional[str]
    legacy_id: Optional[str]
    index_entries: Tuple[RegistryIndexEntry, ...]

@dataclass(frozen=True)
class RegistryDiscovery:
    claims: Tuple[RegistryClaim, ...]
    unresolved: Tuple[Dict[str, object], ...]

@dataclass(frozen=True)
class GitSkillOrigin:
    repository: str
    commit: str
    source_path: str
    source_id: str
    default_categories: Tuple[str, ...]
    registry_archive_mirror: bool

@dataclass(frozen=True)
class RegistrySkillOrigin:
    provenance: "RegistryProvenance"
    source_id: str = "clawhub"

SkillOrigin = Union[GitSkillOrigin, RegistrySkillOrigin]
```

`load_registry` must require an exact object with no unknown fields, exact base URL `https://clawhub.ai`, id `clawhub`, `non_suspicious_only=true`, positive finite timeout, `1 <= max_workers <= 64`, `1 <= max_attempts <= 10`, and positive integer limits. Use these configuration values:

```json
{
  "schema_version": "1.0",
  "id": "clawhub",
  "base_url": "https://clawhub.ai",
  "index_source_id": "VoltAgent/awesome-openclaw-skills",
  "non_suspicious_only": true,
  "request_timeout_seconds": 30,
  "max_workers": 16,
  "max_attempts": 7,
  "max_download_bytes": 57671680,
  "max_github_archive_bytes": 268435456,
  "max_uncompressed_bytes": 53477376,
  "max_github_uncompressed_bytes": 536870912,
  "max_files": 10000,
  "max_compression_ratio": 200
}
```

In `sync_source`, recognize a lowercase 40-character `spec.ref` before the branch/tag clone path. For an empty cache, initialize or clone without `--branch`, disable hooks, fetch that exact SHA with depth 1, and check out detached; verify `rev-parse HEAD` equals the requested SHA. Branch/tag refs continue using the existing behavior. Never pass a raw SHA to `git clone --branch`.

- [ ] **Step 4: Run configuration GREEN**

Run: `PYTHONPATH=src python3 -m unittest tests.test_config tests.test_git_sources -v`

Expected: all configuration and Git synchronization tests PASS; the pinned SHA checks out detached from an empty cache while `load_sources` still rejects every non-GitHub production URL.

- [ ] **Step 5: Write failing pure claim-discovery tests**

Use an index fixture containing duplicate category entries, a legacy link, both current ClawHub URL shapes, and malformed candidates:

```python
def test_discovers_legacy_and_canonical_claims_without_modifying_index(self):
    before = self.snapshot_tree(self.index)
    discovery = discover_clawhub_claims(self.index)
    self.assertEqual(before, self.snapshot_tree(self.index))
    self.assertEqual(
        [
            ("arxiv-search-collector", None, "xukp20-arxiv-search-collector"),
            ("calendar", "alice", None),
        ],
        [(item.claimed_slug, item.claimed_owner, item.legacy_id) for item in discovery.claims],
    )
    self.assertEqual(
        (RegistryIndexEntry("categories/research.md", "arxiv-search-collector", "https://clawskills.sh/skills/xukp20-arxiv-search-collector"),),
        discovery.claims[0].index_entries,
    )

def test_records_label_mismatch_query_fragment_and_malformed_components(self):
    discovery = discover_clawhub_claims(self.malformed_index)
    self.assertEqual(
        ["malformed-clawhub-link", "missing-markdown-label"],
        sorted(item["reason"] for item in discovery.unresolved),
    )

def test_claim_id_is_stable_and_changes_with_any_audited_claim_field(self):
    claim = self.valid_claim()
    self.assertEqual(registry_claim_id(claim), registry_claim_id(self.reordered_entries(claim)))
    self.assertNotEqual(registry_claim_id(claim), registry_claim_id(self.changed_label(claim)))
```

- [ ] **Step 6: Run discovery RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_discovery -v`

Expected: FAIL because `discover_clawhub_claims` is absent and the old archive parser expects a nonexistent owner/slug archive layout.

- [ ] **Step 7: Implement deterministic claim discovery**

Parse Markdown links together with labels instead of scanning bare URLs alone. Preserve the label in every `RegistryIndexEntry`. Require ASCII lower-case ClawHub components matching `[a-z0-9][a-z0-9_.-]*`, decode percent escapes once, reject query/fragment/backslash/NUL/path traversal, aggregate duplicate claims, sort index entries, and return unresolved in canonical JSON-key order. Remove the write into the index checkout and stop using `discover_openclaw_archive_paths` in production.

Define `registry_claim_id` as SHA-256 over canonical JSON containing exactly `claimed_slug`, nullable `claimed_owner`, nullable `legacy_id`, and sorted index entries with `index_path`, `label`, and `url`. This key exists before any network call and is used to reconcile both resolved and unresolved lock entries.

Delete or rewrite every old test that requires 81 sources, `ARCHIVE_SOURCES = ["openclaw/skills"]`, registry archive mirror propagation from that dead source, or mutation of an index checkout by `discover_openclaw_archive_paths`. Retain the generic Git archive and mirror implementation tests through local fixtures where they remain valid; only the dead configured OpenClaw archive assumptions are removed.

- [ ] **Step 8: Run focused and full GREEN, then commit**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_config tests.test_git_sources tests.test_discovery -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: all tests PASS.

Commit:

```bash
git add config/clawhub.json config/sources.json src/skill_atlas/models.py src/skill_atlas/config.py src/skill_atlas/git_sources.py src/skill_atlas/discovery.py tests/test_config.py tests/test_git_sources.py tests/test_discovery.py
git commit -m "feat: discover pinned ClawHub registry claims"
```

---

### Task 7: Safe Exact ClawHub API Resolution and Version Locks

**Files:**
- Create: `src/skill_atlas/clawhub.py`
- Create: `tests/fixtures/clawhub/search-exact.json`
- Create: `tests/fixtures/clawhub/skill-clean.json`
- Create: `tests/fixtures/clawhub/version-clean.json`
- Create: `tests/fixtures/clawhub/skill-blocked.json`
- Create: `tests/test_clawhub.py`
- Modify: `src/skill_atlas/models.py`

**Interfaces:**
- `HttpTransport(request: HttpRequest, timeout_seconds: float, max_body_bytes: int) -> HttpResponse`
- `HttpRequest(method, url, allowed_final_hosts)`
- `HttpResponse(status, headers, body, final_url)`
- `ClawHubClient(spec: RegistrySpec, transport: HttpTransport, sleeper: Callable[[float], None], clock: Callable[[], float])`
- `ClawHubClient.resolve(claim: RegistryClaim) -> RegistryResolveResult`
- `ClawHubClient.recheck_locked(entry: ResolvedRegistryLockEntry) -> RegistryGateResult`
- `sync_claims(spec: RegistrySpec, claims: Sequence[RegistryClaim], client: ClawHubClient) -> RegistryResolutionResult`
- `RegistryFile(path, size, sha256, content_type)`
- `RegistryResolution(claim_id, claim, owner_handle, owner_id, slug, version, published_at, canonical_url, version_metadata_sha256, files, security)`
- `RegistryResolveResult(resolution: Optional[RegistryResolution], unresolved_lock_entry: Optional[UnresolvedRegistryLockEntry], failure: Optional[Dict[str, object]], blocking: bool)`
- `ResolvedRegistryLockEntry(claim_id, status, resolution fields, artifact_kind, archive_sha256, registry_meta_sha256, github_handoff)`
- `UnresolvedRegistryLockEntry(claim_id, status, claim, failure)`
- `RegistryLockEntry = Union[ResolvedRegistryLockEntry, UnresolvedRegistryLockEntry]`
- `RegistryResolutionResult(resolutions, unresolved_lock_entries, unresolved, blocking_failures, stats)`

- [ ] **Step 1: Freeze minimal official-response fixtures**

Store only fields consumed by the adapter. The clean version fixture must contain:

```json
{
  "skill": {"slug": "arxiv-search-collector", "displayName": "Arxiv Search Collector"},
  "version": {
    "version": "0.1.1",
    "createdAt": 1771071167907,
    "files": [
      {"path": "SKILL.md", "size": 20, "sha256": "e4f6d6f7d6038d82cc3d9ddf99c474d4e95b12dca4d0c13f5306ec6844e4a08a", "contentType": null},
      {"path": "scripts/run.py", "size": 13, "sha256": "c23423063f1f8359317c4c323af3b24d26df00bc990d9c9f6b7f0f9d8602894d", "contentType": null}
    ],
    "security": {"status": "clean", "hasWarnings": true, "hasScanResult": true, "scanners": {}}
  }
}
```

Mark `public-github` fixtures as synthetic and OpenAPI-derived in a sibling `README.md`; do not describe them as live observations.

- [ ] **Step 2: Write failing exact-resolution and safety tests**

```python
def test_legacy_claim_requires_exact_slug_and_full_owner_slug_identity(self):
    resolution = self.client.resolve(self.legacy_claim()).resolution
    self.assertIsNotNone(resolution)
    self.assertEqual("xukp20", resolution.owner_handle)
    self.assertEqual("arxiv-search-collector", resolution.slug)
    self.assertEqual("0.1.1", resolution.version)
    self.assertIn("nonSuspiciousOnly=true", self.transport.urls[0])
    self.assertTrue(any("ownerHandle=xukp20" in url and "/versions/0.1.1" in url for url in self.transport.urls))

def test_owner_mismatch_is_unresolved_and_never_downloaded(self):
    result = self.client.resolve(self.claim(owner="old-owner"))
    self.assertEqual("owner-mismatch", result.failure["reason"])
    self.assertFalse(any("/download?" in url for url in self.transport.urls))

def test_nonclean_moderation_or_version_security_fails_closed(self):
    for status in ("pending", "error", "suspicious", "malicious", None):
        with self.subTest(status=status):
            result = self.resolve_with_security(status)
            self.assertEqual("security-not-clean", result.failure["reason"])

def test_moderation_flags_fail_closed_even_when_search_was_filtered(self):
    for field, value in (("isSuspicious", True), ("isMalwareBlocked", True), ("verdict", "suspicious")):
        with self.subTest(field=field):
            result = self.resolve_with_moderation({field: value})
            self.assertEqual("moderation-blocked", result.failure["reason"])

def test_zero_multiple_legacy_or_detail_identity_mismatches_are_mapping_failures(self):
    for fixture in self.identity_mismatch_cases():
        with self.subTest(fixture=fixture.name):
            result = self.client_for(fixture).resolve(self.legacy_claim())
            self.assertEqual("mapping-unresolved", result.failure["reason"])

def test_status_semantics_are_endpoint_specific(self):
    self.assertEqual("unavailable-or-hidden", self.resolve_detail_http(404).failure["reason"])
    self.assertEqual("moderation-blocked", self.resolve_detail_http(403).failure["reason"])
    self.assertEqual("api-conflict", self.resolve_detail_http(409).failure["reason"])
    self.assertTrue(self.resolve_detail_http(409).blocking)
```

- [ ] **Step 3: Run resolver RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_clawhub.ClawHubResolutionTests -v`

Expected: FAIL because the client and registry lock models do not exist.

- [ ] **Step 4: Implement strict public API parsing**

Use a small injected transport that receives `HttpRequest(method, url, allowed_final_hosts)` and returns `HttpResponse(status, headers, body, final_url)`. The default urllib transport must reject a redirect whose final scheme/host is outside the request's allowlist and must stop reading as soon as either declared `Content-Length` or streamed bytes exceed `max_body_bytes`. Build URLs only from the fixed base URL and `urllib.parse.urlencode`. Reject missing/wrong field types, noncanonical owner/slug/version, duplicate manifest paths, negative/non-integer size, non-lowercase SHA-256, missing root `SKILL.md`, and unexpected null version. Permit unknown fields in general JSON responses for forward compatibility; the later `public-github` handoff parser is the one strict `additionalProperties=false` response.

Map errors by endpoint. Search with zero or multiple exact candidates and any legacy-id mismatch yields expected nonblocking `mapping-unresolved`. Detail/version 403 yields `moderation-blocked`, 404 yields `unavailable-or-hidden`, and 409 or malformed 2xx payload is a blocking `api-conflict`. Download 409 is a blocking `download-conflict`; it is never downgraded to owner ambiguity. After search, require the detail response to repeat the exact owner and slug. The current explicit-version response does not carry owner, so require its `skill.slug` and `version.version` to repeat the requested slug and explicit version; owner remains fixed by the detail gate and is sent as `ownerHandle` on both version and download requests. The only request that selects latest is the fresh detail request; every version and download request uses the resolved explicit version.

Build `stable_manifest = {"owner_handle": owner, "slug": slug, "version": version, "published_at": created_at, "files": sorted_files}` and canonicalize it with `json.dumps(stable_manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. Compute `version_metadata_sha256` from those UTF-8 bytes. Do not include mutable scan timestamps or scanner prose in that hash; store the complete current security snapshot separately without adding timestamps of this importer. Require owner and slug to match `[a-z0-9][a-z0-9_.-]*`; require version to match `[A-Za-z0-9][A-Za-z0-9._+-]*` before using it in a URL, cache key, or path.

- [ ] **Step 5: Write failing retry and stable-order tests**

```python
def test_429_obeys_retry_after_then_succeeds(self):
    transport = SequenceTransport([response(429, b"", {"Retry-After": "2"}), self.clean_search])
    sleeps = []
    client = ClawHubClient(self.spec, transport, sleeps.append, lambda: 1000.0)
    client.search_exact("arxiv-search-collector")
    self.assertEqual([2.0], sleeps)

def test_retry_exhaustion_is_blocking_and_contains_no_secret_or_temp_path(self):
    client = ClawHubClient(self.spec, self.always_503, lambda _: None, lambda: 1000.0)
    result = sync_claims(self.spec, [self.legacy_claim()], client)
    self.assertEqual(1, result.blocking_failures)
    serialized = json.dumps(result.unresolved, sort_keys=True)
    self.assertNotIn(str(self.cache), serialized)

def test_parallel_resolution_returns_successes_and_failures_in_stable_claim_order(self):
    client = ClawHubClient(self.spec, self.transport, lambda _: None, lambda: 1000.0)
    result = sync_claims(self.spec, list(reversed(self.claims)), client)
    resolved_ids = [item.claim_id for item in result.resolutions]
    unresolved_ids = [item.claim_id for item in result.unresolved_lock_entries]
    self.assertEqual(sorted(resolved_ids), resolved_ids)
    self.assertEqual(sorted(unresolved_ids), unresolved_ids)

def test_bounded_transport_rejects_declared_streamed_and_redirect_overflow(self):
    for fixture in self.transport_boundary_cases():
        with self.subTest(fixture=fixture.name), self.assertRaises(RegistryTransportError):
            self.transport_for(fixture)(fixture.request, 30.0, 1024)

def test_retry_after_http_date_uses_clock_and_invalid_value_falls_back(self):
    self.assertEqual(10.0, retry_delay({"Retry-After": "Thu, 01 Jan 1970 00:16:50 GMT"}, 0, 1000.0))
    self.assertEqual(1.0, retry_delay({"Retry-After": "invalid"}, 0, 1000.0))
```

- [ ] **Step 6: Run retry RED, implement bounded retries and concurrency, then GREEN**

Retry only 429, 500, 502, 503, and 504 up to `max_attempts`. Choose delay from numeric or HTTP-date `Retry-After`, then relative `RateLimit-Reset`, then absolute Unix `X-RateLimit-Reset`, otherwise use capped exponential delays `1, 2, 4, 8, 16, 30` seconds; malformed rate headers fall through to the next source. Inject the clock and sleeper so tests do not wait. The one urllib timeout value applies to each socket operation, while the bounded reader independently limits total body bytes. Use at most `max_workers` threads, never serialize credentials, and sort all outputs after completion.

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_clawhub -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/skill_atlas/clawhub.py src/skill_atlas/models.py tests/fixtures/clawhub tests/test_clawhub.py
git commit -m "feat: resolve clean ClawHub versions exactly"
```

---

### Task 8: Complete Hosted ZIP and Public-GitHub Bundle Verification

**Files:**
- Create: `src/skill_atlas/zip_bundle.py`
- Create: `tests/test_zip_bundle.py`
- Modify: `src/skill_atlas/clawhub.py`
- Modify: `src/skill_atlas/models.py`

**Interfaces:**
- `download_verified_bundle(client, resolution, cache_root) -> RegistryDownloadResult`
- `verify_and_extract_hosted_zip(payload, manifest, destination, limits) -> ArchiveVerification`
- `verify_and_extract_github_archive(payload, handoff, manifest, destination, limits) -> ArchiveVerification`
- `ResolvedRegistryBundle(resolution, lock_entry: ResolvedRegistryLockEntry, skill_root)`
- `RegistryDownloadResult(bundle: Optional[ResolvedRegistryBundle], failure: Optional[Dict[str, object]], blocking: bool)`
- `ArchiveVerification(archive_sha256, registry_meta_sha256: Optional[str], extracted_files)`

- [ ] **Step 1: Write failing hosted ZIP completeness tests**

Build ZIP bytes in memory from exact manifest payloads:

```python
def test_extracts_every_manifest_file_and_omits_only_registry_meta(self):
    payload = make_zip({
        "SKILL.md": SKILL_BYTES,
        "scripts/run.py": RUN_BYTES,
        "_meta.json": b'{"owner":"xukp20"}\n',
    })
    verified = verify_and_extract_hosted_zip(payload, self.manifest, self.output, self.limits)
    self.assertEqual(SKILL_BYTES, (self.output / "SKILL.md").read_bytes())
    self.assertEqual(RUN_BYTES, (self.output / "scripts/run.py").read_bytes())
    self.assertFalse((self.output / "_meta.json").exists())
    self.assertRegex(verified.archive_sha256, r"^[0-9a-f]{64}$")
    self.assertRegex(verified.registry_meta_sha256, r"^[0-9a-f]{64}$")

def test_registry_meta_is_optional_but_recorded_when_present(self):
    without_meta = verify_and_extract_hosted_zip(self.payload_without_meta, self.manifest, self.output / "none", self.limits)
    with_meta = verify_and_extract_hosted_zip(self.payload_with_meta, self.manifest, self.output / "present", self.limits)
    self.assertIsNone(without_meta.registry_meta_sha256)
    self.assertRegex(with_meta.registry_meta_sha256, r"^[0-9a-f]{64}$")

def test_rejects_missing_extra_size_or_sha_mismatch(self):
    cases = {
        "missing": make_zip({"SKILL.md": SKILL_BYTES}),
        "extra": make_zip({"SKILL.md": SKILL_BYTES, "scripts/run.py": RUN_BYTES, "extra.txt": b"x"}),
        "changed": make_zip({"SKILL.md": SKILL_BYTES, "scripts/run.py": b"changed"}),
    }
    for reason, payload in cases.items():
        with self.subTest(reason=reason), self.assertRaises(BundleIntegrityError):
            verify_and_extract_hosted_zip(payload, self.manifest, self.output / reason, self.limits)
```

- [ ] **Step 2: Run hosted ZIP RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_zip_bundle.HostedZipTests -v`

Expected: FAIL because the ZIP verifier is absent.

- [ ] **Step 3: Implement inspect-before-extract hosted verification**

Read the archive bytes only after the bounded HTTP reader has rejected a response above `max_download_bytes`. Inspect every `ZipInfo` before creating destination files. Normalize with POSIX semantics and Unicode NFC; reject backslash, absolute/drive paths, control characters, dot segments, encryption, symlink/special mode bits, duplicate normalized paths, casefold/NFC collisions, too many files, excess uncompressed bytes, and per-file compression ratio greater than the configured maximum. Permit directory marker entries only when they are parents of manifest files. Hash while copying to new regular files and require exact manifest path, size, and digest equality.

- [ ] **Step 4: Write and run failing archive attack tests**

Cover each attack independently:

```python
def test_rejects_traversal_absolute_backslash_and_drive_paths(self):
    for name in ("../escape", "/absolute", "folder\\name", "C:/drive", "./dot", "folder/./dot", "bad\x1fname"):
        with self.subTest(name=name), self.assertRaises(BundleSecurityError):
            verify_and_extract_hosted_zip(make_zip({name: b"x"}), self.manifest, self.output / "bad", self.limits)

def test_rejects_raw_nul_and_invalid_utf8_filename_bytes(self):
    payloads = (
        raw_zip_with_filename_bytes(b"bad\x00name", utf8_flag=False),
        raw_zip_with_filename_bytes(b"bad\xffname", utf8_flag=True),
        raw_zip_with_filename_bytes(b"caf\x82.txt", utf8_flag=False),
    )
    for payload in payloads:
        with self.assertRaises(BundleSecurityError):
            verify_and_extract_hosted_zip(payload, self.manifest, self.output / "raw", self.limits)

def test_rejects_symlink_device_encrypted_and_duplicate_entries(self):
    for payload in self.special_entry_archives():
        with self.assertRaises(BundleSecurityError):
            verify_and_extract_hosted_zip(payload, self.manifest, self.output / "special", self.limits)

def test_rejects_nfc_and_casefold_collisions(self):
    for left, right in (("A.txt", "a.txt"), ("é.txt", "e\u0301.txt")):
        with self.assertRaises(BundleSecurityError):
            verify_and_extract_hosted_zip(make_zip_entries([(left, b"1"), (right, b"2")]), self.manifest, self.output / "collision", self.limits)

def test_rejects_file_count_total_size_and_compression_ratio_limits(self):
    for payload, limits in self.limit_violation_cases():
        with self.assertRaises(BundleSecurityError):
            verify_and_extract_hosted_zip(payload, self.manifest, self.output / "limit", limits)

def test_failure_leaves_no_partial_cache_directory(self):
    with self.assertRaises(BundleIntegrityError):
        publish_verified_bundle(self.changed_payload, self.resolution, self.cache)
    self.assertEqual([], list(self.cache.glob("**/.complete.json")))
    self.assertEqual([], [path for path in self.cache.rglob("*") if path.name.startswith(".tmp-")])
    self.assertFalse(self.expected_final_cache.exists())

def test_download_409_is_blocking_conflict_not_mapping_ambiguity(self):
    result = download_verified_bundle(self.client_returning(409), self.resolution, self.cache)
    self.assertTrue(result.blocking)
    self.assertEqual("download-conflict", result.failure["reason"])
```

Run: `PYTHONPATH=src python3 -m unittest tests.test_zip_bundle.ZipSecurityTests -v`

Expected: FAIL on every not-yet-enforced boundary for the expected reason.

`raw_zip_with_filename_bytes` must construct or patch both the local header and central-directory filename bytes directly; do not use `zipfile.writestr` for the NUL/invalid-UTF-8 cases because it normalizes or truncates them before the verifier sees the attack.

- [ ] **Step 5: Implement atomic content cache and run hosted GREEN**

Fix the cache layout as `<cache-root>/clawhub/<owner>/<slug>/<version>/<version-metadata-sha256>/.complete.json` plus sibling directory `bundle/`. `ResolvedRegistryBundle.skill_root` points to `bundle/`, never to the marker parent, so `.complete.json` cannot enter materialization. Use a random temporary sibling directory, verify all bytes, write the sorted marker containing owner/slug/version, version metadata hash, archive hash, optional registry meta hash, artifact kind, handoff fields, and file manifest, fsync files where supported, then publish with one non-replacing directory rename. A cache hit is valid only after re-hashing every manifest file, proving no extra path exists below `bundle/`, and checking the marker; a symlink, missing marker, extra file, or mismatch invalidates the entry without following links.

Run: `PYTHONPATH=src python3 -m unittest tests.test_zip_bundle.HostedZipTests tests.test_zip_bundle.ZipSecurityTests -v`

Expected: all hosted ZIP tests PASS.

- [ ] **Step 6: Write failing `public-github` handoff tests**

```python
def test_extracts_only_exact_handoff_path_from_pinned_commit_archive(self):
    handoff = self.handoff(repo="alice/skills", commit="a" * 40, path="skills/calendar")
    archive = make_github_archive("skills-" + "a" * 7, {
        "skills/calendar/SKILL.md": SKILL_BYTES,
        "skills/calendar/scripts/run.py": RUN_BYTES,
        "skills/other/SKILL.md": b"not selected",
    })
    verify_and_extract_github_archive(archive, handoff, self.manifest, self.output, self.limits)
    self.assertFalse((self.output / "skills/other").exists())
    self.assertEqual(SKILL_BYTES, (self.output / "SKILL.md").read_bytes())

def test_rejects_wrong_repo_commit_path_host_redirect_or_manifest(self):
    cases = [
        self.handoff(repo="alice/skills.git", commit="a" * 40, path="skills/calendar"),
        self.handoff(repo="alice/skills", commit="main", path="skills/calendar"),
        self.handoff(repo="alice/skills", commit="a" * 40, path="../escape"),
        self.handoff(repo="alice/skills", commit="a" * 40, path="skills/calendar", archive_url="https://evil.example/archive.zip"),
    ]
    for handoff in cases:
        with self.assertRaises(BundleSecurityError):
            verify_and_extract_github_archive(self.github_archive, handoff, self.manifest, self.output / "bad", self.limits)
```

- [ ] **Step 7: Run handoff RED, implement exact handoff checks, then GREEN**

Require the handoff JSON to contain exactly `sourceRef`, `repo`, `commit`, `path`, `contentHash`, and `archiveUrl`, with `sourceRef == "public-github"`. Accept only canonical `owner/repo` using the existing case-preserving GitHub owner/repository grammar, lowercase 40-character commit, safe relative path, and `https://github.com` or `https://codeload.github.com` archive URL whose owner/repo/commit match the descriptor; uppercase legal owners such as `NVIDIA` remain valid, but `.git`, empty, traversal, or option-shaped components do not. The bounded transport must also report a matching allowed `final_url` after redirects. Apply the same ZIP security checks with the GitHub-specific compressed and uncompressed limits, strip exactly one archive root plus the handoff path, and require the resulting file set to equal the ClawHub version manifest. Because repository license evidence is not resolved in this task, mark every GitHub-backed record `redistribution_review=true`; never infer that a registry policy silently overrides a repository license.

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_zip_bundle -v
PYTHONPATH=src python3 -m unittest tests.test_clawhub -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/skill_atlas/zip_bundle.py src/skill_atlas/clawhub.py src/skill_atlas/models.py tests/test_zip_bundle.py tests/test_clawhub.py
git commit -m "feat: verify complete ClawHub bundles"
```

---

### Task 9: Registry Provenance, Catalog Routing, Materialization, and Validation

**Files:**
- Modify: `src/skill_atlas/models.py`
- Modify: `src/skill_atlas/classifier.py`
- Modify: `src/skill_atlas/materialize.py`
- Modify: `src/skill_atlas/pipeline.py`
- Modify: `schemas/skill-atlas.schema.json`
- Modify: `src/skill_atlas/validate.py`
- Modify: `tests/test_classifier.py`
- Modify: `tests/test_materialize.py`
- Modify: `tests/test_validate.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- `SkillRecord(origin: SkillOrigin, skill_root, name, description, license, license_evidence, skill_md_hash, redistribution_review)`
- `classify(skill: ParsedSkill, taxonomy: Taxonomy, default_categories: Sequence[str] = ()) -> Classification`
- `_Candidate(source_id, source_type, blocking, record, classification)`
- `RegistryProvenance(registry, owner_handle, owner_id, slug, version, published_at, canonical_url, artifact_kind, archive_sha256, registry_meta_sha256, version_metadata_sha256, files, security, index_source_id, index_commit, index_entries, license_policy_url, github_handoff)`
- Git sidecar: `provenance.source_type == "git"`
- ClawHub sidecar: `provenance.source_type == "clawhub"`
- ClawHub route: `skills/<group>/<category>/<owner>/clawhub/<version>/<slug>/`

- [ ] **Step 1: Write failing registry materialization tests**

```python
def test_registry_skill_routes_by_owner_version_slug_and_preserves_bundle(self):
    result = materialize(self.registry_record(), self.output, self.classification, self.taxonomy)
    self.assertEqual(
        Path("skills/B-software-systems-automation/C07-debugging-testing-quality/xukp20/clawhub/0.1.1/arxiv-search-collector"),
        result.relative_path,
    )
    self.assertEqual(SKILL_BYTES, (self.output / result.relative_path / "SKILL.md").read_bytes())

def test_registry_sidecar_contains_fixed_identity_manifest_security_and_hashes(self):
    result = materialize(self.registry_record(), self.output, self.classification, self.taxonomy)
    data = json.loads((self.output / result.sidecar_path).read_text())
    provenance = data["provenance"]
    self.assertEqual("clawhub", provenance["source_type"])
    self.assertEqual("xukp20", provenance["owner_handle"])
    self.assertEqual("0.1.1", provenance["version"])
    self.assertEqual(self.version_metadata_sha256, provenance["version_metadata_sha256"])
    self.assertEqual(self.archive_sha256, provenance["archive_sha256"])
    self.assertEqual(["SKILL.md", "scripts/run.py"], [item["path"] for item in provenance["files"]])
```

- [ ] **Step 2: Run materialization RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_materialize.RegistryMaterializeTests -v`

Expected: FAIL because catalog paths and provenance assume a GitHub repository and commit.

- [ ] **Step 3: Decouple records and classification from Git-only source types**

Replace `SkillRecord.source/repository/commit/source_path/registry_archive_mirror` with one required `origin: SkillOrigin`. Existing Git construction uses `GitSkillOrigin` and retains the same exact Git values. Change classifier callers to pass `origin.default_categories` for Git and `()` for registry; the classifier no longer accepts `SourceSpec`. Change `_Candidate` to carry explicit `source_id`, `source_type`, and `blocking` rather than a mandatory `SyncedSource`. Existing configured direct Git candidates set `blocking=true`; index-derived Git candidates remain nonblocking; every verified registry candidate sets `blocking=true` for later parse/classification/path/materialization failures.

Run the focused classifier and CLI tests after this refactor before adding registry materialization:

```bash
PYTHONPATH=src python3 -m unittest tests.test_classifier tests.test_cli -v
```

Expected: existing Git behavior PASS with no synthetic ClawHub `SourceSpec`, fake repository, or fake commit.

- [ ] **Step 4: Implement tagged provenance without weakening Git checks**

Set sidecar `schema_version` and the JSON Schema to `2.0` because tagged provenance is not backward-compatible; update `CLASSIFIER_VERSION` only if classifier output behavior changes beyond the input signature. Add `source_type: "git"` to existing Git sidecars. Make the schema provenance a strict `oneOf`: the Git branch retains repository/commit/source_path/license/review/mirror requirements; the ClawHub branch requires registry URL, owner handle/id, slug, version, canonical URL, published timestamp, artifact kind, archive and version hashes, optional registry meta hash, sorted file manifest, security snapshot, index source id/commit/entries including labels, license fields, policy URL, and optional strict GitHub handoff. Both branches set `additionalProperties: false`.

Construct `RegistryProvenance` only from a successful `ResolvedRegistryLockEntry` and its pinned index context. Hosted entries use `license="MIT-0"`, `license_policy_url="https://github.com/openclaw/clawhub/blob/main/docs/skill-format.md#license"`, nonempty policy evidence, and `redistribution_review=false`. Public-GitHub entries preserve the same registry policy claim but set `redistribution_review=true` because repository license evidence is not independently resolved. `registry_meta_sha256` is nullable and must match the cache marker when present.

For registry records, derive route components only from validated provenance. Use owner as the first source component, literal `clawhub` as the repository component, version as the parent key, and slug as the leaf. Do not put a fake Git commit or repository into the sidecar.

- [ ] **Step 5: Run materialization GREEN**

Run: `PYTHONPATH=src python3 -m unittest tests.test_materialize -v`

Expected: all Git and registry materialization tests PASS.

- [ ] **Step 6: Write failing registry validation tests**

```python
def test_valid_registry_catalog_recomputes_route_bundle_and_manifest_hashes(self):
    result = self.materialize_registry()
    self.write_reports([result])
    self.assertEqual([], validate_catalog(self.catalog, self.taxonomy).failures)

def test_detects_registry_owner_version_route_manifest_and_file_tampering(self):
    for mutation, expected_code in self.registry_mutations():
        with self.subTest(expected_code=expected_code):
            catalog = mutation(self.fresh_registry_catalog())
            codes = {item.code for item in validate_catalog(catalog, self.taxonomy).failures}
            self.assertIn(expected_code, codes)
```

Require separate codes for `registry-provenance-invalid`, `catalog-path-mismatch`, `registry-manifest-mismatch`, and existing `content-hash-mismatch`/`skill-md-hash-mismatch`.

- [ ] **Step 7: Run validation RED, implement exact validation, then full GREEN**

Reconstruct the route from provenance, compare the sidecar file manifest with every materialized upstream file except `skill-atlas.json`, verify size/SHA-256, require root `SKILL.md`, and validate the canonical URL `https://clawhub.ai/<owner>/skills/<slug>`. Preserve existing nested-Skill and portability behavior.

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_validate -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/skill_atlas/models.py src/skill_atlas/classifier.py src/skill_atlas/materialize.py src/skill_atlas/pipeline.py schemas/skill-atlas.schema.json src/skill_atlas/validate.py tests/test_classifier.py tests/test_materialize.py tests/test_validate.py tests/test_cli.py
git commit -m "feat: preserve ClawHub provenance in catalog"
```

---

### Task 10: Pipeline, CLI, Registry Lock, Reports, and Locked Replay

**Files:**
- Modify: `src/skill_atlas/pipeline.py`
- Modify: `src/skill_atlas/cli.py`
- Modify: `src/skill_atlas/__main__.py`
- Create: `src/skill_atlas/audit.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_clawhub.py`
- Create: `tests/test_audit.py`

**Interfaces:**
- `sync_source_graph(configured_sources, cache_root, locked_path=None, synchronizer=sync_source, registry_spec=None, registry_adapter=None, registry_locked_path=None) -> SyncOutcome`
- `SyncOutcome.registry_bundles`
- `SyncOutcome.registry_lock_entries`
- `SyncOutcome.registry_blocking_failures`
- `SyncOutcome.registry_stats`
- `SyncOutcome.registry_lock_payload() -> Dict[str, object]`
- `audit_reports(root: Path) -> List[ValidationFailure]`
- Report: `reports/clawhub.lock.json`
- CLI lock rule: `--locked [sources-path]` uses `clawhub.lock.json` from the same directory unless `--registry-locked [path]` overrides it; root defaults require both reports when a registry is configured

- [ ] **Step 1: Write failing offline Git-plus-ClawHub end-to-end test**

Inject a fake registry adapter that consumes the fixture index checkout and returns one verified local bundle:

```python
def test_all_combines_git_and_clawhub_with_two_independent_locks(self):
    code, stdout, stderr = self.run_cli("all", registry_adapter=self.registry_adapter)
    self.assertEqual(0, code, stderr)
    self.assertEqual(4, len(list((self.output / "skills").rglob("skill-atlas.json"))))
    self.assertTrue((self.output / "reports/sources.lock.json").is_file())
    lock = json.loads((self.output / "reports/clawhub.lock.json").read_text())
    self.assertEqual("1.0", lock["schema_version"])
    self.assertEqual("resolved", lock["skills"][0]["status"])
    summary = json.loads((self.output / "reports/summary.json").read_text())
    self.assertEqual(1, summary["clawhub_imported"])
    self.assertEqual(4, summary["imported"])

def test_existing_custom_loader_without_registry_config_remains_offline(self):
    code, _, stderr = self.run_cli("all", registry_loader=lambda _: None)
    self.assertEqual(0, code, stderr)
    self.assertEqual([], self.network_requests)
```

- [ ] **Step 2: Run integration RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_cli.CliTests.test_all_combines_git_and_clawhub_with_two_independent_locks -v`

Expected: FAIL because the CLI and pipeline do not load or invoke a registry.

- [ ] **Step 3: Integrate registry sync after the pinned index checkout**

Extend `main` with injected `registry_loader` and `registry_adapter_factory`; existing tests whose custom config path has no sibling `clawhub.json` receive `None` and never construct a live client. The production config directory loads `config/clawhub.json`.

Locate the configured registry's `index_source_id` in resolved indexes. If absent, add stable unresolved `registry-index-unavailable` and one blocking registry failure. For fresh sync, discover claims and resolve/download them. For locked sync, read `clawhub.lock.json`, require exact registry id/base URL/index id/index commit and complete `claim_id` uniqueness, recheck current visibility/security as a gate, and reuse only exact cached version/version-metadata/archive hashes. When the gate remains clean, keep the lock's original security snapshot and provenance bytes. If visibility changes to hidden/blocked, create a stable unresolved transition; never overwrite a clean lock with merely refreshed checkedAt/scanner text.

`--locked` without a value reads `reports/sources.lock.json` and `reports/clawhub.lock.json`. `--locked /external/sources.lock.json` derives `/external/clawhub.lock.json`; `--registry-locked /other/clawhub.lock.json` overrides that derivation. `build` without flags requires both root locks whenever the registry config is present. Missing, extra, duplicate, wrong-index, or unconsumed claim ids fail before synchronization or catalog publication.

Merge verified registry bundles into `_Candidate` creation through `RegistrySkillOrigin`, never a synthetic `SourceSpec`. Sort combined candidates by `(source_type, source_identity, source_path)` before collision checks. A download/archive/cache failure increments `clawhub_artifact_failure`; a verified bundle whose `SKILL.md` parsing, classification, route, or materialization fails increments `clawhub_materialization_failure`; their sum is the reported `clawhub_integrity_failure`. Both are blocking and make `all` return 1. Keep all existing staging and publication code paths.

- [ ] **Step 4: Write failing lock and failure-semantics tests**

```python
def test_locked_registry_rebuild_never_queries_search_or_latest(self):
    self.run_cli("all", registry_adapter=self.registry_adapter)
    code, _, stderr = self.run_cli("all", "--locked", registry_adapter=self.registry_adapter)
    self.assertEqual(0, code, stderr)
    self.assertNotIn("/search?", self.registry_adapter.urls_for_locked_run)
    self.assertNotIn("tag=latest", "".join(self.registry_adapter.urls_for_locked_run))

def test_locked_registry_rechecks_visibility_and_removes_now_hidden_bundle(self):
    self.seed_resolved_registry_lock_and_catalog()
    code, _, _ = self.run_cli("all", "--locked", registry_adapter=self.hidden_registry_adapter)
    self.assertEqual(0, code)
    self.assertFalse(any("arxiv-search-collector" in str(path) for path in (self.output / "skills").rglob("SKILL.md")))
    self.assertIn("unavailable-or-hidden", (self.output / "reports/unresolved.json").read_text())

def test_locked_clean_recheck_does_not_replace_pinned_security_snapshot(self):
    before = self.seed_resolved_registry_lock_and_catalog()
    self.registry_adapter.current_security["checkedAt"] += 1000
    self.registry_adapter.current_security["scanners"]["llm"]["summary"] = "new mutable prose"
    code, _, stderr = self.run_cli("all", "--locked", registry_adapter=self.registry_adapter)
    self.assertEqual(0, code, stderr)
    self.assertEqual(before["clawhub.lock.json"], (self.output / "reports/clawhub.lock.json").read_bytes())

def test_external_git_lock_derives_sibling_registry_lock_and_override_wins(self):
    self.seed_external_locks()
    code, _, stderr = self.run_cli("all", "--locked", str(self.external_sources_lock), registry_adapter=self.registry_adapter)
    self.assertEqual(0, code, stderr)
    self.assertEqual(self.external_clawhub_lock, self.registry_adapter.consumed_lock)
    code, _, stderr = self.run_cli("all", "--locked", str(self.external_sources_lock), "--registry-locked", str(self.override_clawhub_lock), registry_adapter=self.registry_adapter)
    self.assertEqual(0, code, stderr)
    self.assertEqual(self.override_clawhub_lock, self.registry_adapter.consumed_lock)

def test_hash_mismatch_or_transport_exhaustion_publishes_verified_entries_but_returns_one(self):
    code, _, stderr = self.run_cli("all", registry_adapter=self.one_good_one_integrity_failure)
    self.assertEqual(1, code)
    self.assertIn("registry integrity", stderr)
    self.assertTrue(any((self.output / "skills").rglob("skill-atlas.json")))

def test_invalid_or_unconsumed_registry_lock_fails_before_catalog_publication(self):
    old = self.seed_catalog_and_invalid_registry_lock(extra_identity=("ghost", "skill", "1.0.0"))
    code, _, stderr = self.run_cli("all", "--locked", registry_adapter=self.registry_adapter)
    self.assertEqual(2, code)
    self.assertIn("unconsumed registry lock", stderr)
    self.assertEqual(old, self.generated_bytes())

def test_publication_failure_after_registry_staging_preserves_previous_catalog_bytes(self):
    old = self.seed_successful_catalog()
    with mock.patch("skill_atlas.pipeline.os.replace", side_effect=OSError("injected publish failure")):
        code, _, stderr = self.run_cli("all", registry_adapter=self.registry_adapter)
    self.assertEqual(2, code)
    self.assertIn("injected publish failure", stderr)
    self.assertEqual(old, self.generated_bytes())
```

- [ ] **Step 5: Run lock RED, implement deterministic registry reports, then GREEN**

`clawhub.lock.json` must contain exact top-level keys `schema_version`, `registry`, `index`, and `skills`. Every normalized claim gets a `claim_id` equal to the SHA-256 of canonical claimed slug/owner/legacy id/index entries, so even an unresolved legacy claim has a stable lock identity. Resolved entries additionally require owner, slug, version, manifest, security, artifact kind, archive hash, and cache identity. Unresolved entries require the original claim fields and `failure`. Never record retrieval time, temp paths, local cache paths, request ids, rate-limit state, or tokens.

Extend the stable summary with:

```text
clawhub_index_claims
clawhub_normalized_claims
clawhub_discovery_failure
clawhub_duplicate_claims
clawhub_exact_safe_matches
clawhub_artifact_verified
clawhub_hosted_verified
clawhub_github_backed_verified
clawhub_artifact_failure
clawhub_materialization_failure
clawhub_unavailable_or_hidden
clawhub_moderation_blocked
clawhub_owner_mismatch
clawhub_mapping_unresolved
clawhub_transport_failure
clawhub_api_failure
clawhub_integrity_failure
clawhub_imported
git_imported
```

Update `read_summary` to require the complete exact key set. Add `clawhub.lock.json` to generated report manifests and rollback coverage.

Write failing `tests/test_audit.py` cases before implementing `audit_reports`. The audit must require these exact equations using actual summary keys and lock failure reasons:

```text
clawhub_index_claims
  = clawhub_normalized_claims + clawhub_discovery_failure + clawhub_duplicate_claims

clawhub_normalized_claims
  = clawhub_exact_safe_matches
  + clawhub_unavailable_or_hidden
  + clawhub_moderation_blocked
  + clawhub_owner_mismatch
  + clawhub_mapping_unresolved
  + clawhub_transport_failure
  + clawhub_api_failure

clawhub_exact_safe_matches
  = clawhub_artifact_verified + clawhub_artifact_failure

clawhub_artifact_verified
  = clawhub_hosted_verified + clawhub_github_backed_verified

clawhub_artifact_verified
  = clawhub_imported + clawhub_materialization_failure

clawhub_integrity_failure
  = clawhub_artifact_failure + clawhub_materialization_failure

imported = git_imported + clawhub_imported
```

It must also prove one `claim_id` per normalized claim, one central catalog row per generated sidecar, existing duplicate paths with matching hashes, and `source_id`/`reason` on every unresolved item. Add CLI command `audit --config config --root .` that prints one JSON object and returns 1 on findings.

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_cli tests.test_clawhub -v
PYTHONPATH=src python3 -m unittest tests.test_audit -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
git diff --check
```

Expected: all tests PASS and `git diff --check` prints nothing.

- [ ] **Step 6: Commit**

```bash
git add src/skill_atlas/pipeline.py src/skill_atlas/cli.py src/skill_atlas/__main__.py src/skill_atlas/audit.py tests/test_cli.py tests/test_clawhub.py tests/test_audit.py
git commit -m "feat: integrate reproducible ClawHub ingestion"
```

---

### Task 11: Live Full Import, Audit, and Final Verification

**Files:**
- Generate: `skills/**`
- Generate: `reports/sources.lock.json`
- Generate: `reports/clawhub.lock.json`
- Generate: `reports/catalog.jsonl`
- Generate: `reports/duplicates.json`
- Generate: `reports/unresolved.json`
- Generate: `reports/summary.json`
- Generate: `reports/validation.json`
- Generate: `reports/generated-files.json`
- Generate: `licenses/**`
- Update during execution only: `.superpowers/sdd/progress.md` (ignored durable task ledger; do not add it to the release commit)

**Interfaces:**
- Fresh run: `PYTHONPATH=src python3 -m skill_atlas all --config config --root . --cache .cache/upstreams`
- Locked replay: `PYTHONPATH=src python3 -m skill_atlas all --config config --root . --cache .cache/upstreams --locked`
- Validation: `PYTHONPATH=src python3 -m skill_atlas validate --config config --root . --report`
- Audit: `PYTHONPATH=src python3 -m skill_atlas audit --config config --root .`

- [ ] **Step 1: Run a single real hosted Skill smoke import in a temporary root**

Use the pinned index claim for `xukp20/arxiv-search-collector`, explicit resolved version, and a temporary output root. Confirm two downloads produce the same ZIP SHA-256, all version-manifest files exist with exact bytes, `_meta.json` is not materialized, the adjacent sidecar validates, and no upstream code executes.

Expected: smoke catalog validation has zero failures.

- [ ] **Step 2: Run fresh full Git plus ClawHub import**

Run the fresh command with progress logging every 100 registry claims on stderr only; stdout must remain one JSON document. Respect 429 backoff and reuse independently verified cache entries. Do not change worker or security limits mid-run without adding the change to configuration and lock review.

Expected: all accessible Git sources and every safely resolved ClawHub claim are processed; expected historical failures appear in unresolved; integrity failures make the command return 1 and must be investigated before acceptance.

- [ ] **Step 3: Audit exact report relationships**

Run the implemented audit command; it checks these exact equations:

```text
clawhub_index_claims
  = clawhub_normalized_claims + clawhub_discovery_failure + clawhub_duplicate_claims

clawhub_normalized_claims
  = clawhub_exact_safe_matches
  + clawhub_unavailable_or_hidden
  + clawhub_moderation_blocked
  + clawhub_owner_mismatch
  + clawhub_mapping_unresolved
  + clawhub_transport_failure
  + clawhub_api_failure

clawhub_exact_safe_matches
  = clawhub_artifact_verified + clawhub_artifact_failure

clawhub_artifact_verified
  = clawhub_hosted_verified + clawhub_github_backed_verified

clawhub_artifact_verified
  = clawhub_imported + clawhub_materialization_failure

clawhub_integrity_failure
  = clawhub_artifact_failure + clawhub_materialization_failure

imported = git_imported + clawhub_imported
```

Also require one sidecar per generated root, one catalog JSONL record per sidecar, a complete generated-files manifest, duplicate paths that all exist and share the declared content hash, one unique `claim_id` per normalized claim, and no unresolved item without `source_id` or `reason`. The audit command must return 0 with an empty findings array.

- [ ] **Step 4: Run locked replay and byte-stability checks**

Save hashes of the generated catalog and reports, run `all --locked`, and compare outputs. Differences are allowed only for claims whose current public/security recheck changed state; each difference must correspond to a stable unresolved transition. No Skill may upgrade owner or version.

- [ ] **Step 5: Run fresh full verification evidence**

Run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m skill_atlas validate --config config --root . --report
PYTHONPATH=src python3 -m skill_atlas audit --config config --root .
git diff --check
git status --short
```

Expected:

- complete test suite: zero failures;
- catalog validation: `valid: true`, zero findings;
- `git diff --check`: no output;
- `git status --short`: only intended source, config, documentation, generated catalog, report, and license paths.

- [ ] **Step 6: Final whole-branch review and commit**

Dispatch the final reviewer against the merge-base-to-HEAD review package. Fix every Critical or Important finding, rerun affected tests and the full verification commands, and re-review.

Commit verified generated artifacts and final audit updates:

```bash
git add skills licenses reports
git commit -m "data: import verified Skill catalog"
```

Do not claim completion until the fresh full suite, catalog validator, report equations, locked replay, and final review all pass.

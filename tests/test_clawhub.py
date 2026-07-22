import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from skill_atlas.clawhub import (
    ClawHubClient,
    HttpRequest,
    HttpResponse,
    RegistryTransportError,
    retry_delay,
    sync_claims,
    urllib_transport,
)
from skill_atlas.discovery import registry_claim_id
from skill_atlas.models import (
    RegistryClaim,
    RegistryIndexEntry,
    RegistrySpec,
    ResolvedRegistryLockEntry,
)


FIXTURES = Path(__file__).parent / "fixtures" / "clawhub"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def json_response(payload, status=200, headers=None, final_url="https://clawhub.ai/"):
    response_headers = {"Content-Type": "application/json"}
    response_headers.update(headers or {})
    return HttpResponse(
        status=status,
        headers=response_headers,
        body=json.dumps(payload).encode("utf-8"),
        final_url=final_url,
    )


def text_response(status, text="", headers=None, final_url="https://clawhub.ai/"):
    response_headers = {"Content-Type": "text/plain; charset=utf-8"}
    response_headers.update(headers or {})
    return HttpResponse(
        status=status,
        headers=response_headers,
        body=text.encode("utf-8"),
        final_url=final_url,
    )


class RoutingTransport:
    def __init__(self, search, detail, version):
        self.search = search
        self.detail = detail
        self.version = version
        self.requests = []

    @property
    def urls(self):
        return [request.url for request in self.requests]

    def __call__(self, request, timeout_seconds, max_body_bytes):
        self.requests.append(request)
        if "/api/v1/search?" in request.url:
            response = self.search
        elif "/versions/" in request.url:
            response = self.version
        elif "/api/v1/skills/" in request.url:
            response = self.detail
        else:
            raise AssertionError("unexpected request: " + request.url)
        if callable(response):
            response = response(request)
        return response


class SequenceTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout_seconds, max_body_bytes):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("transport sequence exhausted")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ClawHubTestCase(unittest.TestCase):
    def setUp(self):
        self.spec = RegistrySpec(
            id="clawhub",
            base_url="https://clawhub.ai",
            index_source_id="VoltAgent/awesome-openclaw-skills",
            non_suspicious_only=True,
            request_timeout_seconds=30.0,
            max_workers=4,
            max_attempts=3,
            max_download_bytes=55 * 1024 * 1024,
            max_github_archive_bytes=256 * 1024 * 1024,
            max_uncompressed_bytes=51 * 1024 * 1024,
            max_github_uncompressed_bytes=512 * 1024 * 1024,
            max_files=10_000,
            max_compression_ratio=200,
        )
        self.search_payload = load_fixture("search-exact.json")
        self.detail_payload = load_fixture("skill-clean.json")
        self.version_payload = load_fixture("version-clean.json")

    def legacy_claim(self):
        return RegistryClaim(
            claimed_slug="arxiv-search-collector",
            claimed_owner=None,
            legacy_id="xukp20-arxiv-search-collector",
            index_entries=(
                RegistryIndexEntry(
                    index_path="categories/research.md",
                    label="arxiv-search-collector",
                    url="https://clawskills.sh/skills/xukp20-arxiv-search-collector",
                ),
            ),
        )

    def canonical_claim(self, owner="xukp20", slug="arxiv-search-collector"):
        return RegistryClaim(
            claimed_slug=slug,
            claimed_owner=owner,
            legacy_id=None,
            index_entries=(
                RegistryIndexEntry(
                    index_path="categories/research.md",
                    label=slug,
                    url=f"https://clawhub.ai/{owner}/skills/{slug}",
                ),
            ),
        )

    def make_client(self, search=None, detail=None, version=None, spec=None):
        transport = RoutingTransport(
            json_response(self.search_payload) if search is None else search,
            json_response(self.detail_payload) if detail is None else detail,
            json_response(self.version_payload) if version is None else version,
        )
        return (
            ClawHubClient(
                spec or self.spec,
                transport,
                lambda _: None,
                lambda: 1000.0,
            ),
            transport,
        )


class ClawHubResolutionTests(ClawHubTestCase):
    def test_legacy_claim_requires_exact_slug_and_full_owner_slug_identity(self):
        client, transport = self.make_client()

        result = client.resolve(self.legacy_claim())

        self.assertFalse(result.blocking)
        self.assertIsNone(result.failure)
        resolution = result.resolution
        self.assertIsNotNone(resolution)
        self.assertEqual("xukp20", resolution.owner_handle)
        self.assertEqual("owner-stable-id", resolution.owner_id)
        self.assertEqual("arxiv-search-collector", resolution.slug)
        self.assertEqual("0.1.1", resolution.version)
        self.assertEqual(
            "https://clawhub.ai/xukp20/skills/arxiv-search-collector",
            resolution.canonical_url,
        )
        self.assertIn("nonSuspiciousOnly=true", transport.urls[0])
        self.assertTrue(
            any(
                "ownerHandle=xukp20" in url and "/versions/0.1.1" in url
                for url in transport.urls
            )
        )
        self.assertFalse(any("/download?" in url for url in transport.urls))

    def test_owner_mismatch_is_unresolved_and_never_requests_detail_or_download(self):
        client, transport = self.make_client()

        result = client.resolve(self.canonical_claim(owner="old-owner"))

        self.assertEqual("owner-mismatch", result.failure["reason"])
        self.assertFalse(result.blocking)
        self.assertEqual(1, len(transport.urls))
        self.assertFalse(any("/download?" in url for url in transport.urls))

    def test_nonclean_version_security_fails_closed(self):
        for status in ("pending", "error", "suspicious", "malicious", None):
            with self.subTest(status=status):
                version = copy.deepcopy(self.version_payload)
                version["version"]["security"]["status"] = status
                client, _ = self.make_client(version=json_response(version))

                result = client.resolve(self.legacy_claim())

                self.assertEqual("security-not-clean", result.failure["reason"])
                self.assertFalse(result.blocking)

    def test_moderation_flags_fail_closed_even_when_search_was_filtered(self):
        blocked_values = (
            ("isSuspicious", True),
            ("isMalwareBlocked", True),
            ("verdict", "suspicious"),
            ("verdict", "malicious"),
        )
        for field, value in blocked_values:
            with self.subTest(field=field, value=value):
                detail = copy.deepcopy(self.detail_payload)
                detail["moderation"] = {field: value}
                client, _ = self.make_client(detail=json_response(detail))

                result = client.resolve(self.legacy_claim())

                self.assertEqual("moderation-blocked", result.failure["reason"])
                self.assertFalse(result.blocking)

    def test_zero_multiple_legacy_or_detail_identity_mismatches_are_mapping_failures(self):
        zero = {"results": []}
        multiple = copy.deepcopy(self.search_payload)
        multiple["results"].append(copy.deepcopy(multiple["results"][0]))
        wrong_detail = copy.deepcopy(self.detail_payload)
        wrong_detail["owner"]["handle"] = "other-owner"
        cases = (
            {"search": json_response(zero)},
            {"search": json_response(multiple)},
            {"detail": json_response(wrong_detail)},
        )
        for offset, overrides in enumerate(cases):
            with self.subTest(case=offset):
                client, _ = self.make_client(**overrides)

                result = client.resolve(self.legacy_claim())

                self.assertEqual("mapping-unresolved", result.failure["reason"])
                self.assertFalse(result.blocking)

    def test_explicit_version_identity_mismatch_is_blocking_api_conflict(self):
        version = copy.deepcopy(self.version_payload)
        version["version"]["version"] = "0.1.2"
        client, _ = self.make_client(version=json_response(version))

        result = client.resolve(self.legacy_claim())

        self.assertEqual("api-conflict", result.failure["reason"])
        self.assertTrue(result.blocking)

    def test_status_semantics_are_endpoint_specific(self):
        cases = (
            (403, "moderation-blocked", False),
            (404, "unavailable-or-hidden", False),
            (409, "api-conflict", True),
        )
        for status, reason, blocking in cases:
            with self.subTest(status=status):
                client, _ = self.make_client(detail=text_response(status, "failure"))

                result = client.resolve(self.legacy_claim())

                self.assertEqual(reason, result.failure["reason"])
                self.assertEqual(blocking, result.blocking)

    def test_general_json_tolerates_unknown_fields_and_preserves_security_snapshot(self):
        client, _ = self.make_client()

        resolution = client.resolve(self.legacy_claim()).resolution

        self.assertIsNotNone(resolution)
        self.assertEqual(1779966788797, resolution.security["checkedAt"])
        self.assertEqual("clean", resolution.security["scanners"]["llm"]["status"])

    def test_stable_manifest_hash_excludes_mutable_scanner_fields_and_prose(self):
        first_client, _ = self.make_client()
        first = first_client.resolve(self.legacy_claim()).resolution
        changed = copy.deepcopy(self.version_payload)
        changed["version"]["security"]["checkedAt"] += 1000
        changed["version"]["security"]["scanners"]["llm"]["summary"] = "new prose"
        changed["version"]["changelog"] = "new changelog prose"
        second_client, _ = self.make_client(version=json_response(changed))

        second = second_client.resolve(self.legacy_claim()).resolution

        self.assertEqual(first.version_metadata_sha256, second.version_metadata_sha256)
        stable_manifest = {
            "owner_handle": "xukp20",
            "slug": "arxiv-search-collector",
            "version": "0.1.1",
            "published_at": 1771071167907,
            "files": [
                {
                    "content_type": None,
                    "path": item.path,
                    "sha256": item.sha256,
                    "size": item.size,
                }
                for item in first.files
            ],
        }
        canonical = json.dumps(
            stable_manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            first.version_metadata_sha256,
        )

    def test_rejects_malformed_manifest_identity_and_field_types(self):
        cases = []
        duplicate = copy.deepcopy(self.version_payload)
        duplicate["version"]["files"].append(
            copy.deepcopy(duplicate["version"]["files"][0])
        )
        cases.append(duplicate)
        negative_size = copy.deepcopy(self.version_payload)
        negative_size["version"]["files"][0]["size"] = -1
        cases.append(negative_size)
        boolean_size = copy.deepcopy(self.version_payload)
        boolean_size["version"]["files"][0]["size"] = True
        cases.append(boolean_size)
        uppercase_hash = copy.deepcopy(self.version_payload)
        uppercase_hash["version"]["files"][0]["sha256"] = "A" * 64
        cases.append(uppercase_hash)
        missing_skill = copy.deepcopy(self.version_payload)
        missing_skill["version"]["files"] = missing_skill["version"]["files"][1:]
        cases.append(missing_skill)
        null_version = copy.deepcopy(self.version_payload)
        null_version["version"] = None
        cases.append(null_version)
        bad_path = copy.deepcopy(self.version_payload)
        bad_path["version"]["files"][1]["path"] = "../run.py"
        cases.append(bad_path)

        for offset, payload in enumerate(cases):
            with self.subTest(case=offset):
                client, _ = self.make_client(version=json_response(payload))

                result = client.resolve(self.legacy_claim())

                self.assertEqual("api-conflict", result.failure["reason"])
                self.assertTrue(result.blocking)

    def test_rejects_noncanonical_latest_before_using_it_in_a_version_url(self):
        detail = copy.deepcopy(self.detail_payload)
        detail["latestVersion"]["version"] = "../../escape"
        client, transport = self.make_client(detail=json_response(detail))

        result = client.resolve(self.legacy_claim())

        self.assertEqual("api-conflict", result.failure["reason"])
        self.assertTrue(result.blocking)
        self.assertFalse(any("/versions/" in url for url in transport.urls))

    def test_recheck_locked_uses_explicit_version_without_search_or_latest_selection(self):
        client, _ = self.make_client()
        resolution = client.resolve(self.legacy_claim()).resolution
        lock_entry = ResolvedRegistryLockEntry.from_resolution(resolution)
        changed_detail = copy.deepcopy(self.detail_payload)
        changed_detail["latestVersion"]["version"] = "9.9.9"
        recheck_client, transport = self.make_client(detail=json_response(changed_detail))

        gate = recheck_client.recheck_locked(lock_entry)

        self.assertTrue(gate.allowed)
        self.assertIsNone(gate.failure)
        self.assertFalse(any("/search?" in url for url in transport.urls))
        self.assertTrue(any("/versions/0.1.1" in url for url in transport.urls))


class ClawHubRetryAndSyncTests(ClawHubTestCase):
    def test_429_obeys_retry_after_then_succeeds(self):
        transport = SequenceTransport(
            [
                text_response(429, "rate limited", {"Retry-After": "2"}),
                json_response(self.search_payload),
            ]
        )
        sleeps = []
        client = ClawHubClient(self.spec, transport, sleeps.append, lambda: 1000.0)

        candidates = client.search_exact("arxiv-search-collector")

        self.assertEqual(1, len(candidates))
        self.assertEqual([2.0], sleeps)

    def test_retries_transport_and_selected_5xx_only(self):
        for first in (
            RegistryTransportError("temporary"),
            text_response(500),
            text_response(502),
            text_response(503),
            text_response(504),
        ):
            with self.subTest(first=first):
                transport = SequenceTransport([first, json_response(self.search_payload)])
                sleeps = []
                client = ClawHubClient(
                    self.spec, transport, sleeps.append, lambda: 1000.0
                )
                self.assertEqual(1, len(client.search_exact("arxiv-search-collector")))
                self.assertEqual([1.0], sleeps)

    def test_retry_exhaustion_is_blocking_and_contains_no_exception_detail(self):
        spec = replace(self.spec, max_attempts=2)
        transport = SequenceTransport(
            [RegistryTransportError("/tmp/secret-token"), text_response(503, "secret")]
        )
        client = ClawHubClient(spec, transport, lambda _: None, lambda: 1000.0)

        result = sync_claims(spec, [self.legacy_claim()], client)

        self.assertEqual(1, result.blocking_failures)
        serialized = json.dumps(result.unresolved, sort_keys=True)
        self.assertNotIn("/tmp/secret-token", serialized)
        self.assertNotIn("secret", serialized)
        self.assertIn("transport-failure", serialized)

    def test_parallel_resolution_captures_each_exception_and_sorts_outputs(self):
        success_claim = self.legacy_claim()
        failure_claim = self.canonical_claim(owner="old-owner")
        success_id = registry_claim_id(success_claim)
        failure_id = registry_claim_id(failure_claim)
        successful_resolution = self.make_client()[0].resolve(success_claim).resolution

        class Client:
            def resolve(self, claim):
                if registry_claim_id(claim) == success_id:
                    from skill_atlas.models import RegistryResolveResult

                    return RegistryResolveResult(
                        resolution=successful_resolution,
                        unresolved_lock_entry=None,
                        failure=None,
                        blocking=False,
                    )
                raise RuntimeError("sensitive unexpected detail")

        result = sync_claims(
            replace(self.spec, max_workers=2),
            [failure_claim, success_claim],
            Client(),
        )

        self.assertEqual([success_id], [item.claim_id for item in result.resolutions])
        self.assertEqual(
            [failure_id],
            [item.claim_id for item in result.unresolved_lock_entries],
        )
        self.assertEqual(1, result.blocking_failures)
        self.assertNotIn("sensitive", json.dumps(result.unresolved))

    def test_retry_after_http_date_uses_clock_and_invalid_value_falls_back(self):
        http_date = datetime.fromtimestamp(1010, tz=timezone.utc).strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )
        self.assertEqual(10.0, retry_delay({"Retry-After": http_date}, 0, 1000.0))
        self.assertEqual(
            7.0,
            retry_delay(
                {"Retry-After": "invalid", "RateLimit-Reset": "7"},
                0,
                1000.0,
            ),
        )
        self.assertEqual(
            9.0,
            retry_delay(
                {
                    "Retry-After": "invalid",
                    "RateLimit-Reset": "invalid",
                    "X-RateLimit-Reset": "1009",
                },
                0,
                1000.0,
            ),
        )
        self.assertEqual(1.0, retry_delay({"Retry-After": "invalid"}, 0, 1000.0))


class FakeNetworkResponse:
    def __init__(self, body, headers=None, final_url="https://clawhub.ai/final"):
        self.status = 200
        self.headers = headers or {}
        self.final_url = final_url
        self.body = body
        self.offset = 0

    def read(self, size=-1):
        if self.offset >= len(self.body):
            return b""
        if size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def geturl(self):
        return self.final_url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeOpener:
    def __init__(self, response):
        self.response = response

    def open(self, request, timeout):
        return self.response


class UrllibTransportTests(unittest.TestCase):
    def setUp(self):
        self.request = HttpRequest(
            method="GET",
            url="https://clawhub.ai/api/v1/search?q=example",
            allowed_final_hosts=("clawhub.ai",),
        )

    def run_transport(self, response, limit=1024):
        with mock.patch(
            "skill_atlas.clawhub.urllib.request.build_opener",
            return_value=FakeOpener(response),
        ):
            return urllib_transport(self.request, 30.0, limit)

    def test_bounded_transport_rejects_declared_length_overflow(self):
        response = FakeNetworkResponse(b"small", {"Content-Length": "1025"})
        with self.assertRaises(RegistryTransportError):
            self.run_transport(response)

    def test_bounded_transport_rejects_streamed_overflow(self):
        response = FakeNetworkResponse(b"x" * 1025)
        with self.assertRaises(RegistryTransportError):
            self.run_transport(response)

    def test_bounded_transport_rejects_disallowed_final_scheme_or_host(self):
        for final_url in ("https://evil.example/final", "http://clawhub.ai/final"):
            with self.subTest(final_url=final_url):
                response = FakeNetworkResponse(b"ok", final_url=final_url)
                with self.assertRaises(RegistryTransportError):
                    self.run_transport(response)

    def test_bounded_transport_returns_small_allowed_response(self):
        response = FakeNetworkResponse(
            b"{}", {"Content-Length": "2", "X-Test": "yes"}
        )

        result = self.run_transport(response)

        self.assertEqual(200, result.status)
        self.assertEqual(b"{}", result.body)
        self.assertEqual("yes", result.headers["X-Test"])


if __name__ == "__main__":
    unittest.main()

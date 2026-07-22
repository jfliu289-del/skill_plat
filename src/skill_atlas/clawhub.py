"""Exact, fail-closed resolution of public ClawHub Skill versions."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import PurePosixPath
import re
import time
from typing import Callable, Dict, Mapping, Optional, Sequence, Tuple
import urllib.error
import urllib.parse
import urllib.request

from .discovery import registry_claim_id
from .models import (
    RegistryClaim,
    RegistryFile,
    RegistryGateResult,
    RegistryResolution,
    RegistryResolutionResult,
    RegistryResolveResult,
    RegistrySpec,
    ResolvedRegistryLockEntry,
    UnresolvedRegistryLockEntry,
)


_COMPONENT = re.compile(r"[a-z0-9][a-z0-9_.-]*")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    allowed_final_hosts: Tuple[str, ...]


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


HttpTransport = Callable[[HttpRequest, float, int], HttpResponse]


class RegistryTransportError(RuntimeError):
    """A redacted registry network or response-boundary failure."""


class _RegistryHttpError(RuntimeError):
    def __init__(self, endpoint: str, status: int):
        super().__init__(endpoint)
        self.endpoint = endpoint
        self.status = status


class _RegistryPayloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class _SearchCandidate:
    owner_handle: str
    slug: str


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: Tuple[str, ...]):
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        if not _allowed_https_url(new_url, self.allowed_hosts):
            raise RegistryTransportError("registry redirect target is not allowed")
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


def urllib_transport(
    request: HttpRequest,
    timeout_seconds: float,
    max_body_bytes: int,
) -> HttpResponse:
    """Perform one bounded HTTPS request without trusting redirect targets."""

    if not _allowed_https_url(request.url, request.allowed_final_hosts):
        raise RegistryTransportError("registry request target is not allowed")
    if type(max_body_bytes) is not int or max_body_bytes <= 0:
        raise RegistryTransportError("registry response bound is invalid")

    opener = urllib.request.build_opener(
        _SafeRedirectHandler(request.allowed_final_hosts)
    )
    network_request = urllib.request.Request(
        request.url,
        method=request.method,
        headers={"Accept": "application/json"},
    )
    response = None
    try:
        try:
            response = opener.open(network_request, timeout_seconds)
        except urllib.error.HTTPError as error:
            response = error
        final_url = response.geturl()
        if not _allowed_https_url(final_url, request.allowed_final_hosts):
            raise RegistryTransportError("registry final response target is not allowed")
        headers = {str(key): str(value) for key, value in response.headers.items()}
        declared_length = _header(headers, "Content-Length")
        if declared_length is not None:
            try:
                parsed_length = int(declared_length, 10)
            except (TypeError, ValueError):
                parsed_length = None
            if parsed_length is not None and parsed_length > max_body_bytes:
                raise RegistryTransportError("registry response exceeds configured bound")

        chunks = []
        total = 0
        while True:
            chunk = response.read(min(64 * 1024, max_body_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > max_body_bytes:
                raise RegistryTransportError("registry response exceeds configured bound")
            chunks.append(chunk)
        status = getattr(response, "status", None)
        if status is None:
            status = response.getcode()
        return HttpResponse(
            status=int(status),
            headers=headers,
            body=b"".join(chunks),
            final_url=final_url,
        )
    except RegistryTransportError:
        raise
    except Exception as error:
        raise RegistryTransportError("registry request failed") from error
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass


def retry_delay(
    headers: Mapping[str, str], attempt: int, now: float
) -> float:
    """Choose a deterministic retry delay using the documented precedence."""

    retry_after = _header(headers, "Retry-After")
    parsed = _nonnegative_number(retry_after)
    if parsed is not None:
        return parsed
    if retry_after:
        try:
            parsed_date = parsedate_to_datetime(retry_after)
            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(tzinfo=timezone.utc)
            delay = parsed_date.timestamp() - now
            if delay >= 0:
                return float(delay)
        except (TypeError, ValueError, OverflowError):
            pass

    relative_reset = _nonnegative_number(_header(headers, "RateLimit-Reset"))
    if relative_reset is not None:
        return relative_reset

    absolute_reset = _nonnegative_number(_header(headers, "X-RateLimit-Reset"))
    if absolute_reset is not None and absolute_reset >= now:
        return float(absolute_reset - now)

    exponent = max(0, attempt)
    return float(min(30, 2 ** exponent))


class ClawHubClient:
    def __init__(
        self,
        spec: RegistrySpec,
        transport: HttpTransport = urllib_transport,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ):
        self.spec = spec
        self.transport = transport
        self.sleeper = sleeper
        self.clock = clock

    def search_exact(self, slug: str) -> Tuple[_SearchCandidate, ...]:
        _require_component(slug, "slug")
        query = [("q", slug)]
        if self.spec.non_suspicious_only:
            query.append(("nonSuspiciousOnly", "true"))
        payload = self._get_json(
            "search",
            "/api/v1/search",
            query,
        )
        results = payload.get("results")
        if not isinstance(results, list):
            raise _RegistryPayloadError("search results must be an array")

        candidates = []
        for item in results:
            if not isinstance(item, dict):
                raise _RegistryPayloadError("search result must be an object")
            item_slug = item.get("slug")
            if item_slug is None:
                continue
            if not isinstance(item_slug, str):
                raise _RegistryPayloadError("search result slug must be a string")
            if item_slug != slug:
                continue
            _require_component(item_slug, "slug")
            owner_handle = item.get("ownerHandle")
            if not isinstance(owner_handle, str):
                raise _RegistryPayloadError("search ownerHandle must be a string")
            _require_component(owner_handle, "owner handle")
            owner = item.get("owner")
            if owner is not None:
                if not isinstance(owner, dict):
                    raise _RegistryPayloadError("search owner must be an object")
                nested_handle = owner.get("handle")
                if nested_handle is not None and nested_handle != owner_handle:
                    raise _RegistryPayloadError("search owner identities conflict")
            candidates.append(_SearchCandidate(owner_handle, item_slug))
        return tuple(candidates)

    def resolve(self, claim: RegistryClaim) -> RegistryResolveResult:
        claim_id = registry_claim_id(claim)
        try:
            _require_component(claim.claimed_slug, "claimed slug")
            if claim.claimed_owner is not None:
                _require_component(claim.claimed_owner, "claimed owner")
            candidates = self.search_exact(claim.claimed_slug)
        except RegistryTransportError:
            return _failure_result(
                claim, claim_id, "transport-failure", True, "search"
            )
        except _RegistryHttpError as error:
            return _http_failure_result(claim, claim_id, error)
        except (TypeError, ValueError, _RegistryPayloadError):
            return _failure_result(claim, claim_id, "api-conflict", True, "search")

        if claim.legacy_id is not None:
            matches = [
                candidate
                for candidate in candidates
                if f"{candidate.owner_handle}-{candidate.slug}" == claim.legacy_id
            ]
            if len(matches) != 1:
                return _failure_result(
                    claim, claim_id, "mapping-unresolved", False, "search"
                )
            candidate = matches[0]
        elif claim.claimed_owner is not None:
            matches = [
                candidate
                for candidate in candidates
                if candidate.owner_handle == claim.claimed_owner
            ]
            if len(matches) != 1:
                reason = "owner-mismatch" if candidates and not matches else "mapping-unresolved"
                return _failure_result(claim, claim_id, reason, False, "search")
            candidate = matches[0]
        else:
            return _failure_result(
                claim, claim_id, "mapping-unresolved", False, "search"
            )

        try:
            detail = self._detail(candidate.owner_handle, candidate.slug)
        except RegistryTransportError:
            return _failure_result(
                claim, claim_id, "transport-failure", True, "detail"
            )
        except _RegistryHttpError as error:
            return _http_failure_result(claim, claim_id, error)
        except _RegistryPayloadError:
            return _failure_result(claim, claim_id, "api-conflict", True, "detail")

        if (
            detail["owner_handle"] != candidate.owner_handle
            or detail["slug"] != candidate.slug
        ):
            return _failure_result(
                claim, claim_id, "mapping-unresolved", False, "detail"
            )
        moderation_failure = _moderation_failure(detail["moderation"])
        if moderation_failure is not None:
            return _failure_result(
                claim, claim_id, moderation_failure, False, "detail"
            )

        version = detail["version"]
        try:
            resolution = self._version_resolution(
                claim,
                claim_id,
                detail["owner_handle"],
                detail["owner_id"],
                detail["slug"],
                version,
            )
        except RegistryTransportError:
            return _failure_result(
                claim, claim_id, "transport-failure", True, "version"
            )
        except _RegistryHttpError as error:
            return _http_failure_result(claim, claim_id, error)
        except _RegistryPayloadError:
            return _failure_result(claim, claim_id, "api-conflict", True, "version")

        if resolution is None:
            return _failure_result(
                claim, claim_id, "security-not-clean", False, "version"
            )
        return RegistryResolveResult(
            resolution=resolution,
            unresolved_lock_entry=None,
            failure=None,
            blocking=False,
        )

    def recheck_locked(
        self, entry: ResolvedRegistryLockEntry
    ) -> RegistryGateResult:
        try:
            _require_component(entry.owner_handle, "owner handle")
            _require_component(entry.slug, "slug")
            _require_version(entry.version)
            detail = self._detail(
                entry.owner_handle,
                entry.slug,
                require_latest=False,
            )
        except RegistryTransportError:
            return RegistryGateResult(
                allowed=False,
                failure=_failure("transport-failure", "detail"),
                blocking=True,
            )
        except _RegistryHttpError as error:
            result = _http_failure_result(entry.claim, entry.claim_id, error)
            return RegistryGateResult(False, result.failure, result.blocking)
        except (TypeError, ValueError, _RegistryPayloadError):
            return RegistryGateResult(
                False, _failure("api-conflict", "detail"), True
            )

        if (
            detail["owner_handle"] != entry.owner_handle
            or detail["slug"] != entry.slug
        ):
            return RegistryGateResult(
                False, _failure("mapping-unresolved", "detail"), False
            )
        moderation_failure = _moderation_failure(detail["moderation"])
        if moderation_failure is not None:
            return RegistryGateResult(
                False, _failure(moderation_failure, "detail"), False
            )
        try:
            resolution = self._version_resolution(
                entry.claim,
                entry.claim_id,
                entry.owner_handle,
                entry.owner_id,
                entry.slug,
                entry.version,
            )
        except RegistryTransportError:
            return RegistryGateResult(
                False, _failure("transport-failure", "version"), True
            )
        except _RegistryHttpError as error:
            result = _http_failure_result(entry.claim, entry.claim_id, error)
            return RegistryGateResult(False, result.failure, result.blocking)
        except _RegistryPayloadError:
            return RegistryGateResult(
                False, _failure("api-conflict", "version"), True
            )
        if resolution is None:
            return RegistryGateResult(
                False, _failure("security-not-clean", "version"), False
            )
        if resolution.version_metadata_sha256 != entry.version_metadata_sha256:
            return RegistryGateResult(
                False, _failure("api-conflict", "version"), True
            )
        return RegistryGateResult(
            allowed=True,
            failure=None,
            blocking=False,
            security=resolution.security,
        )

    def _detail(self, owner: str, slug: str, require_latest: bool = True):
        _require_component(owner, "owner handle")
        _require_component(slug, "slug")
        payload = self._get_json(
            "detail",
            f"/api/v1/skills/{slug}",
            [("ownerHandle", owner)],
        )
        skill = _required_object(payload, "skill")
        response_slug = _required_string(skill, "slug")
        _require_component(response_slug, "detail slug")
        owner_data = _required_object(payload, "owner")
        owner_handle = _required_string(owner_data, "handle")
        _require_component(owner_handle, "detail owner")
        owner_id = owner_data.get("userId")
        if owner_id is not None and not isinstance(owner_id, str):
            raise _RegistryPayloadError("owner id must be a string or null")
        moderation = payload.get("moderation")
        if moderation is not None and not isinstance(moderation, dict):
            raise _RegistryPayloadError("moderation must be an object or null")
        _validate_moderation(moderation)

        version = None
        if require_latest:
            latest = _required_object(payload, "latestVersion")
            version = _required_string(latest, "version")
            _require_version(version)
        return {
            "owner_handle": owner_handle,
            "owner_id": owner_id,
            "slug": response_slug,
            "version": version,
            "moderation": moderation,
        }

    def _version_resolution(
        self,
        claim: RegistryClaim,
        claim_id: str,
        owner: str,
        owner_id: Optional[str],
        slug: str,
        version: str,
    ) -> Optional[RegistryResolution]:
        _require_component(owner, "owner handle")
        _require_component(slug, "slug")
        _require_version(version)
        payload = self._get_json(
            "version",
            f"/api/v1/skills/{slug}/versions/{version}",
            [("ownerHandle", owner)],
        )
        skill = _required_object(payload, "skill")
        response_slug = _required_string(skill, "slug")
        if response_slug != slug:
            raise _RegistryPayloadError("version skill identity mismatch")
        version_data = payload.get("version")
        if not isinstance(version_data, dict):
            raise _RegistryPayloadError("version must be an object")
        response_version = _required_string(version_data, "version")
        if response_version != version:
            raise _RegistryPayloadError("explicit version identity mismatch")
        published_at = version_data.get("createdAt")
        if type(published_at) is not int or published_at < 0:
            raise _RegistryPayloadError("version createdAt must be a non-negative integer")
        files = _parse_files(version_data.get("files"))
        security = version_data.get("security")
        if security is None:
            return None
        if not isinstance(security, dict):
            raise _RegistryPayloadError("security must be an object")
        status = security.get("status")
        if status is not None and not isinstance(status, str):
            raise _RegistryPayloadError("security status must be a string or null")
        for boolean_key in ("hasWarnings", "hasScanResult"):
            if boolean_key in security and type(security[boolean_key]) is not bool:
                raise _RegistryPayloadError(f"security {boolean_key} must be a boolean")
        if "scanners" in security and not isinstance(security["scanners"], dict):
            raise _RegistryPayloadError("security scanners must be an object")
        if status != "clean":
            return None

        stable_manifest = {
            "owner_handle": owner,
            "slug": slug,
            "version": version,
            "published_at": published_at,
            "files": [
                {
                    "content_type": item.content_type,
                    "path": item.path,
                    "sha256": item.sha256,
                    "size": item.size,
                }
                for item in files
            ],
        }
        canonical = json.dumps(
            stable_manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return RegistryResolution(
            claim_id=claim_id,
            claim=claim,
            owner_handle=owner,
            owner_id=owner_id,
            slug=slug,
            version=version,
            published_at=published_at,
            canonical_url=f"{self.spec.base_url}/{owner}/skills/{slug}",
            version_metadata_sha256=hashlib.sha256(canonical).hexdigest(),
            files=files,
            security=copy_json_object(security),
        )

    def _get_json(self, endpoint: str, path: str, query):
        response = self._request(path, query)
        if response.status != 200:
            raise _RegistryHttpError(endpoint, response.status)
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise _RegistryPayloadError("registry response is not valid JSON") from error
        if not isinstance(payload, dict):
            raise _RegistryPayloadError("registry response must be an object")
        return payload

    def _request(self, path: str, query) -> HttpResponse:
        encoded_query = urllib.parse.urlencode(query)
        url = self.spec.base_url + path
        if encoded_query:
            url += "?" + encoded_query
        request = HttpRequest("GET", url, ("clawhub.ai",))
        last_error = None
        for attempt in range(self.spec.max_attempts):
            try:
                response = self.transport(
                    request,
                    self.spec.request_timeout_seconds,
                    self.spec.max_download_bytes,
                )
                if not _allowed_https_url(response.final_url, request.allowed_final_hosts):
                    raise RegistryTransportError(
                        "registry final response target is not allowed"
                    )
            except RegistryTransportError as error:
                last_error = error
                if attempt + 1 >= self.spec.max_attempts:
                    break
                self.sleeper(retry_delay({}, attempt, self.clock()))
                continue
            if response.status not in _RETRYABLE_STATUSES:
                return response
            if attempt + 1 >= self.spec.max_attempts:
                last_error = RegistryTransportError("registry retries exhausted")
                break
            self.sleeper(retry_delay(response.headers, attempt, self.clock()))
        raise RegistryTransportError("registry request retries exhausted") from last_error


def sync_claims(
    spec: RegistrySpec,
    claims: Sequence[RegistryClaim],
    client: ClawHubClient,
) -> RegistryResolutionResult:
    """Resolve claims concurrently while returning only stable, redacted outputs."""

    results = []
    with ThreadPoolExecutor(max_workers=spec.max_workers) as executor:
        pending = {executor.submit(client.resolve, claim): claim for claim in claims}
        for future in as_completed(pending):
            claim = pending[future]
            try:
                result = future.result()
                if not isinstance(result, RegistryResolveResult):
                    raise TypeError("unexpected result")
            except Exception:
                result = _failure_result(
                    claim,
                    registry_claim_id(claim),
                    "api-failure",
                    True,
                    "resolve",
                )
            results.append(result)

    resolutions = tuple(
        sorted(
            (item.resolution for item in results if item.resolution is not None),
            key=lambda item: item.claim_id,
        )
    )
    unresolved_entries = tuple(
        sorted(
            (
                item.unresolved_lock_entry
                for item in results
                if item.unresolved_lock_entry is not None
            ),
            key=lambda item: item.claim_id,
        )
    )
    unresolved = tuple(
        {
            "claim_id": entry.claim_id,
            "status": entry.status,
            "failure": dict(sorted(entry.failure.items())),
        }
        for entry in unresolved_entries
    )
    blocking_failures = sum(1 for item in results if item.blocking)
    stats = {
        "blocking_failures": blocking_failures,
        "normalized_claims": len(claims),
        "resolved": len(resolutions),
        "unresolved": len(unresolved_entries),
    }
    for entry in unresolved_entries:
        key = str(entry.failure.get("reason", "api-failure")).replace("-", "_")
        stats[key] = stats.get(key, 0) + 1
    return RegistryResolutionResult(
        resolutions=resolutions,
        unresolved_lock_entries=unresolved_entries,
        unresolved=unresolved,
        blocking_failures=blocking_failures,
        stats=dict(sorted(stats.items())),
    )


def _parse_files(value) -> Tuple[RegistryFile, ...]:
    if not isinstance(value, list) or not value:
        raise _RegistryPayloadError("version files must be a non-empty array")
    files = []
    paths = set()
    for item in value:
        if not isinstance(item, dict):
            raise _RegistryPayloadError("version file must be an object")
        path = _required_string(item, "path")
        _validate_manifest_path(path)
        if path in paths:
            raise _RegistryPayloadError("version file paths must be unique")
        paths.add(path)
        size = item.get("size")
        if type(size) is not int or size < 0:
            raise _RegistryPayloadError("version file size must be a non-negative integer")
        sha256 = _required_string(item, "sha256")
        if _SHA256.fullmatch(sha256) is None:
            raise _RegistryPayloadError("version file sha256 must be lowercase")
        content_type = item.get("contentType")
        if content_type is not None and not isinstance(content_type, str):
            raise _RegistryPayloadError("version file contentType must be a string or null")
        files.append(RegistryFile(path, size, sha256, content_type))
    if "SKILL.md" not in paths:
        raise _RegistryPayloadError("version manifest must contain root SKILL.md")
    return tuple(sorted(files, key=lambda item: item.path))


def _validate_manifest_path(path: str) -> None:
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or "\x00" in path
        or any(ord(character) < 32 for character in path)
    ):
        raise _RegistryPayloadError("version file path is unsafe")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise _RegistryPayloadError("version file path is unsafe")
    if len(parts[0]) >= 2 and parts[0][1] == ":":
        raise _RegistryPayloadError("version file path is unsafe")
    if PurePosixPath(path).as_posix() != path:
        raise _RegistryPayloadError("version file path is not canonical")


def _moderation_failure(moderation) -> Optional[str]:
    if moderation is None:
        return None
    if moderation.get("isSuspicious") is True:
        return "moderation-blocked"
    if moderation.get("isMalwareBlocked") is True:
        return "moderation-blocked"
    verdict = moderation.get("verdict")
    if verdict not in (None, "clean"):
        return "moderation-blocked"
    return None


def _validate_moderation(moderation) -> None:
    if moderation is None:
        return
    for name in ("isSuspicious", "isMalwareBlocked"):
        if name in moderation and type(moderation[name]) is not bool:
            raise _RegistryPayloadError(f"moderation {name} must be a boolean")
    if "verdict" in moderation and moderation["verdict"] is not None:
        if not isinstance(moderation["verdict"], str):
            raise _RegistryPayloadError("moderation verdict must be a string or null")


def _http_failure_result(
    claim: RegistryClaim,
    claim_id: str,
    error: _RegistryHttpError,
) -> RegistryResolveResult:
    if error.status == 403:
        return _failure_result(
            claim, claim_id, "moderation-blocked", False, error.endpoint, 403
        )
    if error.status == 404:
        return _failure_result(
            claim, claim_id, "unavailable-or-hidden", False, error.endpoint, 404
        )
    if error.status == 409:
        return _failure_result(
            claim, claim_id, "api-conflict", True, error.endpoint, 409
        )
    return _failure_result(
        claim, claim_id, "api-failure", True, error.endpoint, error.status
    )


def _failure_result(
    claim: RegistryClaim,
    claim_id: str,
    reason: str,
    blocking: bool,
    endpoint: str,
    status: Optional[int] = None,
) -> RegistryResolveResult:
    failure = _failure(reason, endpoint, status)
    unresolved = UnresolvedRegistryLockEntry(
        claim_id=claim_id,
        status="unresolved",
        claim=claim,
        failure=failure,
    )
    return RegistryResolveResult(
        resolution=None,
        unresolved_lock_entry=unresolved,
        failure=failure,
        blocking=blocking,
    )


def _failure(reason: str, endpoint: str, status: Optional[int] = None):
    failure = {"endpoint": endpoint, "reason": reason}
    if status is not None:
        failure["status"] = status
    return failure


def _required_object(payload: Dict[str, object], name: str):
    value = payload.get(name)
    if not isinstance(value, dict):
        raise _RegistryPayloadError(f"{name} must be an object")
    return value


def _required_string(payload: Dict[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise _RegistryPayloadError(f"{name} must be a non-empty string")
    return value


def _require_component(value: str, name: str) -> None:
    if not isinstance(value, str) or _COMPONENT.fullmatch(value) is None:
        raise _RegistryPayloadError(f"{name} is not canonical")


def _require_version(value: str) -> None:
    if not isinstance(value, str) or _VERSION.fullmatch(value) is None:
        raise _RegistryPayloadError("version is not canonical")


def _header(headers: Mapping[str, str], name: str) -> Optional[str]:
    lower_name = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lower_name:
            return str(value).strip()
    return None


def _nonnegative_number(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed < 0 or parsed == float("inf") or parsed != parsed:
        return None
    return parsed


def _allowed_https_url(url: str, allowed_hosts: Tuple[str, ...]) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError):
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname in set(allowed_hosts)
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
    )


def copy_json_object(value: Dict[str, object]) -> Dict[str, object]:
    """Copy JSON data without retaining mutable transport-owned containers."""

    return json.loads(json.dumps(value, ensure_ascii=False))

"""HTTP helper tests. All traffic goes through ``httpx.MockTransport``; no real network."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from mayortracker import __version__
from mayortracker.util.config import Settings, load_settings
from mayortracker.util.http import (
    HttpGiveUp,
    HttpStatusError,
    MissingContactEmail,
    PoliteClient,
    RawFileConflict,
    RedirectNotAllowed,
    RobotsDisallowed,
    RobotsUnavailable,
    filename_from_url,
)

EMAIL = "TEST@example.invalid"
HOST = "https://test.invalid"
DAY1 = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)

Handler = Callable[[httpx.Request], httpx.Response]


class FakeTime:
    """Deterministic clock: ``sleep`` advances ``clock`` and is recorded."""

    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []
        self.wall = DAY1

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds

    def clock(self) -> float:
        return self.t

    def now(self) -> datetime:
        return self.wall + timedelta(seconds=self.t)


class Server:
    """Routes requests by full URL to queued responses; records every request."""

    def __init__(self, fake_time: FakeTime) -> None:
        self.routes: dict[str, list[Handler | httpx.Response | Exception]] = {}
        self.requests: list[tuple[str, float, httpx.Request]] = []
        self.fake_time = fake_time

    def add(self, url: str, *responses: httpx.Response | Exception | Handler) -> None:
        self.routes.setdefault(url, []).extend(responses)

    def calls(self, url: str) -> int:
        return sum(1 for u, _, _ in self.requests if u == url)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append((url, self.fake_time.t, request))
        queue = self.routes.get(url)
        if not queue:
            return httpx.Response(404, text="TEST not found")
        item = queue.pop(0) if len(queue) > 1 else queue[0]  # last response repeats
        if isinstance(item, Exception):
            raise item
        if callable(item) and not isinstance(item, httpx.Response):
            return item(request)
        return item


@pytest.fixture
def settings(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("CONTACT_EMAIL", EMAIL)
    return load_settings(project_dir / "config" / "settings.yaml")


@pytest.fixture
def fake_time() -> FakeTime:
    return FakeTime()


@pytest.fixture
def server(fake_time: FakeTime) -> Server:
    srv = Server(fake_time)
    srv.add(f"{HOST}/robots.txt", httpx.Response(404))  # default: no robots.txt
    return srv


@pytest.fixture
def client(settings: Settings, server: Server, fake_time: FakeTime) -> PoliteClient:
    with PoliteClient(
        settings,
        transport=httpx.MockTransport(server),
        sleep=fake_time.sleep,
        clock=fake_time.clock,
        now=fake_time.now,
        rng=random.Random(0),
    ) as c:
        yield c


def ok(body: bytes = b"TEST body", content_type: str = "text/plain") -> httpx.Response:
    return httpx.Response(200, content=body, headers={"Content-Type": content_type})


# ---- identity -----------------------------------------------------------------------


def test_refuses_without_contact_email(project_dir: Path) -> None:
    settings = load_settings(project_dir / "config" / "settings.yaml")
    assert settings.contact_email is None
    with pytest.raises(MissingContactEmail):
        PoliteClient(settings, transport=httpx.MockTransport(lambda r: ok()))


def test_user_agent_header(client: PoliteClient, server: Server) -> None:
    server.add(f"{HOST}/a", ok())
    client.get(f"{HOST}/a")
    ua = server.requests[-1][2].headers["User-Agent"]
    assert ua == f"mayor-tracker-ro/{__version__} (+research; contact: {EMAIL})"


def test_real_network_is_blocked_in_tests() -> None:
    with pytest.raises(RuntimeError, match="Real network access"), httpx.Client() as c:
        c.get("https://test.invalid/")


# ---- rate limiting --------------------------------------------------------------------


def test_rate_limit_per_host(client: PoliteClient, server: Server) -> None:
    other = "https://other.test.invalid"
    server.add(f"{other}/robots.txt", httpx.Response(404))
    for path in ("/a", "/b", "/c"):
        server.add(f"{HOST}{path}", ok())
    server.add(f"{other}/x", ok())

    client.get(f"{HOST}/a")
    client.get(f"{HOST}/b")
    client.get(f"{HOST}/c")
    client.get(f"{other}/x")

    host_times = [t for u, t, _ in server.requests if u.startswith(HOST)]
    gaps = [b - a for a, b in zip(host_times, host_times[1:], strict=False)]
    assert len(host_times) == 4  # robots.txt + 3 pages
    assert all(1.0 <= g <= 1.2 for g in gaps), gaps

    other_first = next(t for u, t, _ in server.requests if u.startswith(other))
    assert other_first == host_times[-1]  # different host: no wait


# ---- retries --------------------------------------------------------------------------


def test_retries_5xx_with_exponential_backoff(
    client: PoliteClient, server: Server, fake_time: FakeTime
) -> None:
    url = f"{HOST}/flaky"
    server.add(url, httpx.Response(503), httpx.Response(502), ok(b"TEST finally"))
    result = client.get(url)
    assert result.content == b"TEST finally"
    assert server.calls(url) == 3
    throttle, backoff1, backoff2 = fake_time.sleeps
    assert 1.0 <= throttle <= 1.2
    assert 2.0 <= backoff1 <= 2.2
    assert 4.0 <= backoff2 <= 4.4


def test_retries_timeouts(client: PoliteClient, server: Server) -> None:
    url = f"{HOST}/slow"
    server.add(url, httpx.ConnectTimeout("TEST timeout"), ok())
    assert client.get(url).status_code == 200
    assert server.calls(url) == 2


def test_honours_retry_after_seconds(
    client: PoliteClient, server: Server, fake_time: FakeTime
) -> None:
    url = f"{HOST}/limited"
    server.add(url, httpx.Response(429, headers={"Retry-After": "7"}), ok())
    client.get(url)
    assert fake_time.sleeps[-1] == 7.0


def test_honours_retry_after_http_date(
    client: PoliteClient, server: Server, fake_time: FakeTime
) -> None:
    url = f"{HOST}/limited-date"
    # Request happens at fake t≈1.0s after DAY1 10:00:00; Retry-After is 10:00:31 GMT.
    retry_at = "Tue, 02 Jan 2024 10:00:31 GMT"
    server.add(url, httpx.Response(503, headers={"Retry-After": retry_at}), ok())
    client.get(url)
    request_t = [t for u, t, _ in server.requests if u == url][0]
    assert fake_time.sleeps[-1] == pytest.approx(31.0 - request_t)


def test_4xx_not_retried(client: PoliteClient, server: Server) -> None:
    url = f"{HOST}/missing"
    server.add(url, httpx.Response(404))
    with pytest.raises(HttpStatusError) as excinfo:
        client.get(url)
    assert excinfo.value.status_code == 404
    assert server.calls(url) == 1


def test_gives_up_after_max_attempts(client: PoliteClient, server: Server) -> None:
    url = f"{HOST}/down"
    server.add(url, httpx.Response(500))
    with pytest.raises(HttpGiveUp):
        client.get(url)
    assert server.calls(url) == 5


def test_follows_redirects_manually(client: PoliteClient, server: Server) -> None:
    url = f"{HOST}/old"
    server.add(url, httpx.Response(301, headers={"Location": "/new"}))
    server.add(f"{HOST}/new", ok(b"TEST moved"))
    result = client.get(url)
    assert result.content == b"TEST moved"
    assert result.final_url == f"{HOST}/new"


# ---- robots.txt -----------------------------------------------------------------------


def robots(text: str) -> httpx.Response:
    return httpx.Response(200, text=text, headers={"Content-Type": "text/plain"})


@pytest.fixture
def robots_server(server: Server) -> Server:
    server.routes[f"{HOST}/robots.txt"] = [
        robots(
            "User-agent: *\nDisallow: /private/\n\n"
            "User-agent: mayor-tracker-ro\nDisallow: /no-mt/\n"
        )
    ]
    server.add(f"{HOST}/public/page", ok())
    server.add(f"{HOST}/private/page", ok())
    server.add(f"{HOST}/no-mt/page", ok())
    return server


def test_robots_allowed(client: PoliteClient, robots_server: Server) -> None:
    assert client.get(f"{HOST}/public/page").status_code == 200
    # A specific group exists for our token, so the "*" group does not apply.
    assert client.get(f"{HOST}/private/page").status_code == 200
    assert robots_server.calls(f"{HOST}/robots.txt") == 1  # cached per host


def test_robots_disallowed(client: PoliteClient, robots_server: Server) -> None:
    with pytest.raises(RobotsDisallowed):
        client.get(f"{HOST}/no-mt/page")
    assert robots_server.calls(f"{HOST}/no-mt/page") == 0


def test_robots_404_allows_everything(client: PoliteClient, server: Server) -> None:
    server.add(f"{HOST}/anything", ok())
    assert client.get(f"{HOST}/anything").status_code == 200


def test_robots_403_allows_everything(client: PoliteClient, server: Server) -> None:
    server.routes[f"{HOST}/robots.txt"] = [httpx.Response(403)]
    server.add(f"{HOST}/anything", ok())
    assert client.get(f"{HOST}/anything").status_code == 200


def test_robots_5xx_disallows_host(client: PoliteClient, server: Server) -> None:
    server.routes[f"{HOST}/robots.txt"] = [httpx.Response(503)]
    server.add(f"{HOST}/page", ok())
    with pytest.raises(RobotsUnavailable):
        client.get(f"{HOST}/page")
    robots_calls = server.calls(f"{HOST}/robots.txt")
    assert robots_calls == 5  # retried as a transient error, then given up
    with pytest.raises(RobotsUnavailable):
        client.get(f"{HOST}/page")
    assert server.calls(f"{HOST}/robots.txt") == robots_calls  # failure cached for session
    assert server.calls(f"{HOST}/page") == 0


def test_robots_unreachable_disallows_host(client: PoliteClient, server: Server) -> None:
    server.routes[f"{HOST}/robots.txt"] = [httpx.ConnectError("TEST unreachable")]
    with pytest.raises(RobotsUnavailable):
        client.get(f"{HOST}/page")


def test_robots_disallowed_is_checked_on_redirect_target(
    client: PoliteClient, robots_server: Server
) -> None:
    robots_server.add(f"{HOST}/go", httpx.Response(302, headers={"Location": "/no-mt/page"}))
    with pytest.raises(RobotsDisallowed):
        client.get(f"{HOST}/go")


# ---- cache ----------------------------------------------------------------------------


def test_cache_hit_avoids_network(
    client: PoliteClient, server: Server, fake_time: FakeTime
) -> None:
    url = f"{HOST}/cached"
    server.add(url, ok(b"TEST cached"))
    first = client.get(url)
    sleeps_before = len(fake_time.sleeps)
    second = client.get(url)
    assert server.calls(url) == 1
    assert not first.from_cache and second.from_cache
    assert second.content == b"TEST cached"
    assert second.retrieved_at == first.retrieved_at.replace(microsecond=0)
    assert len(fake_time.sleeps) == sleeps_before

    third = client.get(url, use_cache=False)
    assert server.calls(url) == 2
    assert not third.from_cache


def test_errors_are_not_cached(client: PoliteClient, server: Server) -> None:
    url = f"{HOST}/err"
    server.add(url, httpx.Response(404))
    for _ in range(2):
        with pytest.raises(HttpStatusError):
            client.get(url)
    assert server.calls(url) == 2


# ---- raw saving -----------------------------------------------------------------------


def test_download_writes_file_and_manifest(
    client: PoliteClient, server: Server, settings: Settings
) -> None:
    url = f"{HOST}/files/TEST%20data.csv"
    body = b"siruta,name\n900001,TEST Comuna Exemplu\n"
    server.add(url, ok(body, "text/csv"))

    entry = client.download(url, "test_source")

    folder = settings.data_dirs()["raw"] / "test_source" / "2024-01-02"
    target = folder / "TEST_data.csv"
    assert target.read_bytes() == body
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == [entry.model_dump()]
    assert manifest[0] == {
        "url": url,
        "final_url": url,
        "filename": "TEST_data.csv",
        "retrieved_at": "2024-01-02T10:00:01Z",
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "http_status": 200,
        "content_type": "text/csv",
    }


def test_download_is_idempotent(client: PoliteClient, server: Server, settings: Settings) -> None:
    url = f"{HOST}/f.csv"
    server.add(url, ok(b"TEST v1"))
    first = client.download(url, "test_source")
    second = client.download(url, "test_source")
    assert first == second
    assert server.calls(url) == 1
    folder = settings.data_dirs()["raw"] / "test_source" / "2024-01-02"
    assert len(json.loads((folder / "manifest.json").read_text())) == 1


def test_download_refuses_to_overwrite_different_content(
    client: PoliteClient, server: Server, settings: Settings
) -> None:
    url = f"{HOST}/f.csv"
    server.add(url, ok(b"TEST v1"), ok(b"TEST v2"))
    client.download(url, "test_source")
    with pytest.raises(RawFileConflict):
        client.download(url, "test_source", use_cache=False)
    target = settings.data_dirs()["raw"] / "test_source" / "2024-01-02" / "f.csv"
    assert target.read_bytes() == b"TEST v1"


def test_download_from_cache_uses_original_retrieval_time(
    client: PoliteClient, server: Server, settings: Settings, fake_time: FakeTime
) -> None:
    url = f"{HOST}/report.pdf"
    server.add(url, ok(b"TEST pdf v1", "application/pdf"), ok(b"TEST pdf v2", "application/pdf"))
    client.get(url)  # populates the cache on 2024-01-02

    fake_time.wall = DAY1 + timedelta(days=3)  # it is now 2024-01-05
    entry = client.download(url, "test_source")
    raw = settings.data_dirs()["raw"] / "test_source"
    assert server.calls(url) == 1
    assert entry.retrieved_at.startswith("2024-01-02T")
    assert (raw / "2024-01-02" / "report.pdf").read_bytes() == b"TEST pdf v1"
    assert not (raw / "2024-01-05").exists()

    refetched = client.download(url, "test_source", use_cache=False)
    assert server.calls(url) == 2
    assert refetched.retrieved_at.startswith("2024-01-05T")
    assert (raw / "2024-01-05" / "report.pdf").read_bytes() == b"TEST pdf v2"


@pytest.mark.parametrize("bad", ["../x", "a/b", "", "Upper", "x y"])
def test_download_rejects_bad_source_id(client: PoliteClient, bad: str) -> None:
    with pytest.raises(ValueError):
        client.download(f"{HOST}/f.csv", bad)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (f"{HOST}/a/b/file.zip", "file.zip"),
        (f"{HOST}/a/Raport%20anual%202023.pdf", "Raport_anual_2023.pdf"),
        (f"{HOST}/", "download"),
        (f"{HOST}/dir/", "dir"),
    ],
)
def test_filename_from_url(url: str, expected: str) -> None:
    assert filename_from_url(url) == expected


# ---- T001a hardening tests -----------------------------------------------------------


def test_retry_after_above_cap_gives_up_without_sleeping(
    client: PoliteClient, server: Server, fake_time: FakeTime
) -> None:
    url = f"{HOST}/limited-long"
    server.add(url, httpx.Response(429, headers={"Retry-After": "301"}), ok())
    sleeps_before = list(fake_time.sleeps)
    with pytest.raises(HttpGiveUp, match="301.0s") as excinfo:
        client.get(url)
    assert "exceeding cap of 300.0s" in str(excinfo.value)
    new_sleeps = fake_time.sleeps[len(sleeps_before):]
    assert not any(s >= 300.0 for s in new_sleeps)
    assert server.calls(url) == 1


def test_retry_after_at_cap_is_honoured(
    client: PoliteClient, server: Server, fake_time: FakeTime
) -> None:
    url = f"{HOST}/limited-at-cap"
    server.add(url, httpx.Response(429, headers={"Retry-After": "300"}), ok(b"TEST honoured"))
    result = client.get(url)
    assert result.content == b"TEST honoured"
    assert fake_time.sleeps[-1] == 300.0
    assert server.calls(url) == 2


def test_cross_host_redirect_raises(client: PoliteClient, server: Server) -> None:
    url = f"{HOST}/cross"
    cross_url = "https://other.invalid/target"
    server.add(url, httpx.Response(302, headers={"Location": cross_url}))
    server.add(cross_url, ok())
    with pytest.raises(RedirectNotAllowed) as excinfo:
        client.get(url)
    assert excinfo.value.target_host == "other.invalid"
    assert server.calls(cross_url) == 0
    assert server.calls("https://other.invalid/robots.txt") == 0


def test_cross_host_redirect_to_allowed_host_succeeds(
    client: PoliteClient, server: Server
) -> None:
    url = f"{HOST}/cross-allowed"
    cross_url = "https://allowed.invalid/target"
    server.add(url, httpx.Response(302, headers={"Location": cross_url}))
    server.add("https://allowed.invalid/robots.txt", httpx.Response(404))
    server.add(cross_url, ok(b"TEST allowed cross"))

    # Case-insensitive check: "ALLOWED.INVALID" matches "allowed.invalid"
    res = client.get(url, allowed_hosts={"ALLOWED.INVALID"})
    assert res.content == b"TEST allowed cross"
    assert res.final_url == cross_url


def test_cross_host_redirect_exact_match_no_wildcards(
    client: PoliteClient, server: Server
) -> None:
    url = f"{HOST}/subdomain"
    cross_url = "https://sub.other.invalid/target"
    server.add(url, httpx.Response(302, headers={"Location": cross_url}))
    with pytest.raises(RedirectNotAllowed):
        client.get(url, allowed_hosts={"other.invalid"})


def test_same_host_redirect_works(client: PoliteClient, server: Server) -> None:
    url = f"{HOST}/same-1"
    target = f"{HOST}/same-2"
    server.add(url, httpx.Response(302, headers={"Location": target}))
    server.add(target, ok(b"TEST same host"))
    res = client.get(url)
    assert res.content == b"TEST same host"
    assert res.final_url == target


def test_robots_redirect_to_another_host_is_followed_and_rules_applied(
    client: PoliteClient, server: Server
) -> None:
    foreign_robots = "https://foreign.invalid/robots.txt"
    server.routes[f"{HOST}/robots.txt"] = [
        httpx.Response(302, headers={"Location": foreign_robots})
    ]
    server.routes[foreign_robots] = [
        robots("User-agent: mayor-tracker-ro\nDisallow: /blocked/\n")
    ]
    server.add(f"{HOST}/blocked/secret", ok())
    server.add(f"{HOST}/public/doc", ok(b"TEST allowed doc"))

    with pytest.raises(RobotsDisallowed):
        client.get(f"{HOST}/blocked/secret")

    res = client.get(f"{HOST}/public/doc")
    assert res.content == b"TEST allowed doc"


def test_download_respects_allowed_hosts(
    client: PoliteClient, server: Server, settings: Settings
) -> None:
    url = f"{HOST}/data.csv"
    target = "https://files.invalid/data.csv"
    server.add(url, httpx.Response(302, headers={"Location": target}))
    server.add("https://files.invalid/robots.txt", httpx.Response(404))
    server.add(target, ok(b"TEST csv", "text/csv"))

    # Without files.invalid in allowed_hosts, raises RedirectNotAllowed
    with pytest.raises(RedirectNotAllowed):
        client.download(url, "test_source")

    # With allowed_hosts, succeeds and saves file
    entry = client.download(url, "test_source", allowed_hosts={"files.invalid"})
    assert entry.final_url == target
    raw_file = settings.data_dirs()["raw"] / "test_source" / "2024-01-02" / "data.csv"
    assert raw_file.read_bytes() == b"TEST csv"


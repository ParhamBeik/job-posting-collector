"""The capture script, run offline against a fake site."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "capture_fixtures.py"
spec = importlib.util.spec_from_file_location("capture_fixtures", SCRIPT)
capture_fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture_fixtures)


def card(post_id: str, href: str) -> str:
    return (
        f'<article class="typology-post post-{post_id}">'
        f'<h2 class="entry-title"><a href="{href}">t</a></h2></article>'
    )


def fake_site(pages: dict[str, str], requested: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if str(request.url) in pages:
            return httpx.Response(200, text=pages[str(request.url)])
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


BASE = "https://eng-estekhdam.com"


def test_refresh_replaces_old_files_instead_of_mixing_them(tmp_path):
    out = tmp_path / "snapshot"
    out.mkdir()
    (out / "posting-111.html").write_text("stale posting from an older capture")
    site = {
        f"{BASE}/": card("222", f"{BASE}/1405/07/15/new/"),
        f"{BASE}/page/99999/": "",
        f"{BASE}/1405/07/15/new/": "posting",
    }

    capture_fixtures.capture(fake_site(site, []), out, max_page=1, sleep=lambda s: None)

    manifest = json.loads((out / "manifest.json").read_text())
    assert {p.name for p in out.glob("*.html")} == {e["file"] for e in manifest["pages"]}
    assert not (out / "posting-111.html").exists()


def test_failed_capture_leaves_existing_snapshot_untouched(tmp_path):
    out = tmp_path / "snapshot"
    out.mkdir()
    (out / "manifest.json").write_text("previous manifest")
    site = {f"{BASE}/": card("222", f"{BASE}/1405/07/15/missing/"), f"{BASE}/page/99999/": ""}

    with pytest.raises(RuntimeError):
        capture_fixtures.capture(fake_site(site, []), out, max_page=1, sleep=lambda s: None)

    assert (out / "manifest.json").read_text() == "previous manifest"


@pytest.mark.parametrize(
    "href",
    [
        "http://169.254.169.254/latest/meta-data/",
        "https://evil.example/eng-estekhdam.com/",
        "javascript:alert(1)",
        "https://eng-estekhdam.com:8080/1405/07/15/x/",
        "http://[::1/1405/07/15/x/",
    ],
)
def test_never_requests_urls_outside_the_source(tmp_path, href):
    requested = []
    site = {f"{BASE}/": card("222", href), f"{BASE}/page/99999/": ""}

    with pytest.raises(ValueError):
        capture_fixtures.capture(fake_site(site, requested), tmp_path / "s", max_page=1, sleep=lambda s: None)

    assert all(url.startswith(f"{BASE}/") for url in requested)


def test_redirect_is_not_followed_and_stops_the_capture(tmp_path):
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://elsewhere.example/"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    with pytest.raises(RuntimeError):
        capture_fixtures.capture(client, tmp_path / "s", max_page=1, sleep=lambda s: None)

    assert requested == [f"{BASE}/"]

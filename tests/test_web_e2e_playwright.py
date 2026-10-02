from __future__ import annotations

import socket
from typing import Generator
from urllib.parse import urlparse
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, expect

from vi_dubber.runtime import WORK_DIR
from vi_dubber import web


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def gradio_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[str, None, None]:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    # Loading the real job archive can reconcile jobs and extract review audio;
    # these layout/reload checks must never depend on retained media or a login.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(web, "WORK_DIR", tmp_path_factory.mktemp("gradio-work"))
        patch.setenv("GRADIO_ANALYTICS_ENABLED", "False")
        patch.setattr(web, "webgpt_route_info", lambda: {
            "ready": False, "reason": "Offline browser fixture; no provider probe",
        })
        patch.setattr(web.translation_runtime, "translation_model_catalog", lambda: {
            "models": [
                {"id": "chatgpt-web/gpt-5.6-sol", "display_name": "Fixture Sol",
                 "reasoning_efforts": ["medium", "high"], "default_effort": "high"},
                {"id": "chatgpt-web/gpt-5.6-sol-instant", "display_name": "Fixture Instant",
                 "reasoning_efforts": ["low"], "default_effort": "low"},
            ],
            "default_model": "chatgpt-web/gpt-5.6-sol",
            "revision": "offline-browser-fixture-r1",
        })
        demo = web.build_app()
        try:
            # launch already owns a server thread and returns when startup ends.
            demo.launch(
                server_name="127.0.0.1", server_port=port,
                prevent_thread_lock=True, show_error=False, quiet=True,
                share=False, css=web.APP_CSS,
            )
            with urlopen(f"{base_url}/config", timeout=5) as response:
                assert response.status == 200
            yield base_url
        finally:
            demo.close()


@pytest.fixture(autouse=True)
def loopback_browser(context) -> None:
    def allow_local(route) -> None:
        parsed = urlparse(route.request.url)
        if parsed.hostname in {"127.0.0.1", "localhost"} or parsed.scheme in {"data", "blob"}:
            route.continue_()
        else:
            route.abort()
    context.route("**/*", allow_local)


def test_playwright_studio_title_and_layout(page: Page, gradio_server: str) -> None:
    page.goto(gradio_server, timeout=20000, wait_until="domcontentloaded")
    expect(page).to_have_title("VI Dubber Studio")

    # Step heading checks
    expect(page.locator("text=BƯỚC 01")).to_be_visible()
    expect(page.locator("text=Nguồn video")).to_be_visible()
    expect(page.get_by_label("Model dịch", exact=True)).to_have_value("Fixture Sol")
    expect(page.get_by_label("Effort", exact=True)).to_have_value("high")

    # Capture visual verification screenshot
    out_dir = WORK_DIR / "artifacts" / "ui-qa"
    out_dir.mkdir(parents=True, exist_ok=True)
    shot_path = out_dir / "playwright_layout_check.png"
    page.screenshot(path=str(shot_path), full_page=True)
    assert shot_path.exists() and shot_path.stat().st_size > 0


def test_playwright_model_catalog_live_dropdown(page: Page, gradio_server: str) -> None:
    """Exercise catalog binding with a fixture, without a live provider request."""
    page.goto(gradio_server, timeout=20000, wait_until="domcontentloaded")

    # Label for translation model dropdown
    model_label = page.locator("text=Model dịch").first
    expect(model_label).to_be_visible(timeout=10000)

    # Effort dropdown label
    effort_label = page.locator("text=Effort").first
    expect(effort_label).to_be_visible(timeout=10000)

    # Check that the catalog banner reflects the dedicated runtime connection.
    status_banner = page.locator("text=17850").first
    expect(status_banner).to_be_visible(timeout=10000)
    expect(page.get_by_text("offline-browser-fixture-r1", exact=False)).to_be_visible()

    model_input = page.get_by_label("Model dịch", exact=True)
    effort_input = page.get_by_label("Effort", exact=True)
    expect(model_input).to_have_value("Fixture Sol")
    expect(effort_input).to_have_value("high")
    model_input.click()
    page.get_by_role("option", name="Fixture Instant", exact=True).click()
    expect(model_input).to_have_value("Fixture Instant")
    expect(effort_input).to_have_value("low")


def test_playwright_browser_reload_preserves_ui(page: Page, gradio_server: str) -> None:
    page.goto(gradio_server, timeout=20000, wait_until="domcontentloaded")
    expect(page.locator("text=BƯỚC 01")).to_be_visible()

    # Perform full browser page reload
    page.reload(wait_until="domcontentloaded")
    expect(page).to_have_title("VI Dubber Studio")
    expect(page.locator("text=BƯỚC 01")).to_be_visible()
    expect(page.locator("text=17850").first).to_be_visible(timeout=10000)
    expect(page.get_by_label("Model dịch", exact=True)).to_have_value("Fixture Sol")
    expect(page.get_by_label("Effort", exact=True)).to_have_value("high")

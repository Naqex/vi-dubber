from __future__ import annotations

import json
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Generator

import pytest
import uvicorn
from playwright.sync_api import Page, expect

import vi_dubber.api as api_mod
from vi_dubber.api import create_app
from vi_dubber.artifacts import atomic_write_json
from vi_dubber.catalog_store import CatalogItem, CatalogStore, UserState
from vi_dubber.jobs import update_job_state
from vi_dubber.longform import MacroChunk
from vi_dubber.longform_state import commit_chunk_stage
from vi_dubber.runtime import PROJECT_ROOT, WORK_DIR


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _ffmpeg_path() -> Path:
    candidates = sorted((PROJECT_ROOT / "tools" / "ffmpeg").rglob("ffmpeg.exe"))
    if not candidates:
        pytest.skip("Bundled ffmpeg.exe is required for the M3 product fixture")
    return candidates[0]


def _write_valid_preview(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(_ffmpeg_path()),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=navy:s=640x360:d=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=10",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _write_valid_voice_track(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(_ffmpeg_path()),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _seed_m3_fixture(work: Path) -> tuple[str, str]:
    target_id = "job-m3-watch-review"
    target = work / target_id
    target.mkdir(parents=True, exist_ok=True)

    segments = [
        {
            "id": 0,
            "start": 1.0,
            "end": 2.0,
            "text": "The first source sentence.",
            "vi": "Câu dịch đầu tiên.",
            "speaker": "SPEAKER_00",
            "review_status": "unreviewed",
        },
        {
            "id": 1,
            "start": 4.0,
            "end": 5.0,
            "text": "The second ready sentence.",
            "vi": "Câu dịch thứ hai vẫn tua được.",
            "speaker": "SPEAKER_00",
            "review_status": "unreviewed",
        },
        {
            "id": 2,
            "start": 11.0,
            "end": 12.0,
            "text": "The blocked chunk stays unavailable.",
            "vi": "Phần bị chặn vẫn chưa thể dùng.",
            "speaker": "SPEAKER_00",
            "review_status": "needs_review",
        },
        {
            "id": 3,
            "start": 21.0,
            "end": 22.0,
            "text": "The current chunk is still processing.",
            "vi": "Phần hiện tại vẫn đang xử lý.",
            "speaker": "SPEAKER_00",
            "review_status": "unreviewed",
        },
    ]
    atomic_write_json(target / "segments_vi.json", segments)

    chunks = []
    for index in range(4):
        start = float(index * 10)
        chunks.append(
            {
                "chunk_id": f"chunk_{index + 1:04d}",
                "index": index,
                "source_start": start,
                "source_end": start + 10.0,
                "context_start": start,
                "context_end": start + 10.0,
                "boundary_reason": "m3_ui_fixture",
            }
        )
    atomic_write_json(target / "chunks" / "plan.json", {"version": 1, "chunks": chunks})

    preview_path = target / "chunks" / "chunk_0001" / "preview" / "PREVIEW_chunk_0001.mp4"
    _write_valid_preview(preview_path)
    _write_valid_voice_track(target / "voice_track.wav")
    preview_meta = target / "chunks" / "chunk_0001" / "preview.json"
    atomic_write_json(
        preview_meta,
        {
            "version": 1,
            "kind": "preview",
            "label": "PREVIEW",
            "final": False,
            "stale": False,
            "chunk_id": "chunk_0001",
            "index": 0,
            "start": 0.0,
            "end": 10.0,
            "duration": 10.0,
            "qa_status": "passed",
            "artifact": "chunks/chunk_0001/preview/PREVIEW_chunk_0001.mp4",
        },
    )
    commit_chunk_stage(
        target,
        MacroChunk(
            chunk_id="chunk_0001",
            index=0,
            source_start=0.0,
            source_end=10.0,
            context_start=0.0,
            context_end=10.0,
            boundary_reason="m3_ui_fixture",
        ),
        "preview",
        inputs={"fixture": "m3-react-ui"},
        artifacts=[preview_path, preview_meta],
        versions={"policy": 1},
    )

    update_job_state(
        target,
        status="paused",
        stage="tts",
        progress=0.62,
        message="M3 representative UI proof fixture",
        metadata={
            "input_name": "M3 Watch Review Fixture",
            "profile": "balanced_fast",
            "translation_model": "product-fixture",
            "source_mode": "Local",
            "longform": {
                "enabled": True,
                "phase": "tts",
                "current_chunk": "chunk_0003",
                "completed_chunks": 2,
                "completed_tts_chunks": 1,
                "total_chunks": 4,
                "preview_total_chunks": 4,
                "preview_ready_chunks": ["chunk_0001"],
                "preview_stale_chunks": [],
                "preview_blocked_chunks": ["chunk_0002"],
                "preview_policy_version": 1,
                "eta_seconds": 145.0,
            },
        },
    )

    # A newer job keeps the target out of the default selection so the browser
    # must exercise the real job archive selector before entering Watch/Review.
    decoy_id = "job-m3-library-entry"
    decoy = work / decoy_id
    decoy.mkdir(parents=True, exist_ok=True)
    _write_valid_preview(decoy / "output.mp4")
    _write_valid_voice_track(decoy / "voice_track.wav")
    time.sleep(0.01)
    update_job_state(
        decoy,
        status="completed",
        stage="complete",
        progress=1.0,
        message="Library entry used to prove job selection",
        metadata={
            "input_name": "M3 Library Entry",
            "profile": "balanced_fast",
            "translation_model": "product-fixture",
            "source_mode": "Local",
        },
    )
    atomic_write_json(decoy / "segments_vi.json", [])

    # M5 catalog rows are seeded independently from the job archive so this
    # browser proof exercises the durable metadata projection and the real
    # CatalogPanel API path. The source fingerprints are fixture identities;
    # no media bytes or provider state are involved in the UI acceptance.
    catalog = CatalogStore(work / "catalog.sqlite3")
    catalog.rebuild(
        [
            CatalogItem(
                item_id=target_id,
                title="M3 Watch Review Fixture",
                source_fingerprint="c" * 64,
                revision="catalog-m3-target-r1",
                availability="available",
                segment_count=len(segments),
                source_ref=f"jobs/{target_id}/source/fixture.mp4",
                metadata={"fixture": "m5-catalog-browser"},
            ),
            CatalogItem(
                item_id=decoy_id,
                title="M3 Library Entry",
                source_fingerprint="d" * 64,
                revision="catalog-m3-decoy-r1",
                availability="missing",
                segment_count=0,
                source_ref=f"jobs/{decoy_id}/source/fixture.mp4",
                metadata={"fixture": "m5-catalog-browser"},
            ),
        ]
    )
    catalog.set_user_state(
        UserState(
            item_id=target_id,
            revision="catalog-m3-target-r1",
            review_state="in_review",
            watch_position_seconds=4.0,
        )
    )
    return target_id, decoy_id


@pytest.fixture
def m3_react_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[str, str, Path], None, None]:
    work = tmp_path / "work"
    work.mkdir(parents=True, exist_ok=True)
    target_id, _ = _seed_m3_fixture(work)
    monkeypatch.setattr(api_mod, "WORK_DIR", work)

    port = _find_free_port()
    app = create_app()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=2)
        pytest.fail(f"M3 React fixture server did not start at {base_url}")

    try:
        yield base_url, target_id, work
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _layout_metrics(page: Page) -> dict[str, int | bool]:
    return page.evaluate(
        """() => ({
          innerWidth: window.innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
          innerHeight: window.innerHeight,
          scrollHeight: document.documentElement.scrollHeight,
          bodyOverflowX: document.body.scrollWidth > window.innerWidth,
        })"""
    )


@pytest.mark.parametrize("passed", [False, True, None])
def test_final_processing_artifact_reports_qa_verdict_separately(
    page: Page, m3_react_server: tuple[str, str, Path], passed: bool | None,
) -> None:
    base_url, target_id, work = m3_react_server
    page.context.route("**/*", lambda route: route.continue_()
                       if route.request.url.startswith(base_url + "/")
                       or route.request.url.startswith(("data:", "blob:")) else route.abort())
    page.route("**/api/system", lambda route: route.fulfill(
        status=200, content_type="application/json", body="{}"))
    page.add_init_script("localStorage.setItem('vi_dubber_lang', 'en')")
    qa = {"similarity": 0.98, "passed": passed, "global_passed": None,
          "full_track_skipped": True, "mode": "risk_segments",
          "segment_summary": {"final_failed": 122 if passed is False else 0}}
    final_path = work / target_id / "output.mp4"
    shutil.copyfile(work / target_id / "chunks/chunk_0001/preview/PREVIEW_chunk_0001.mp4", final_path)
    update_job_state(work / target_id, status="completed", stage="complete", progress=1.0,
                     result={"output": str(final_path), "duration_seconds": 10.0, "qa": qa}, message="Final QA fixture")
    page.goto(base_url, wait_until="networkidle")
    verdict = {False: "QA failed", True: "QA passed", None: "QA unverified"}[passed]
    final_badge = {
        False: "FINAL · QA FAILED",
        True: "FINAL · QA PASSED",
        None: "FINAL · QA UNVERIFIED",
    }[passed]
    completed_badge = {
        False: "COMPLETED · QA FAILED",
        True: "COMPLETED · QA PASSED",
        None: "COMPLETED · QA UNVERIFIED",
    }[passed]
    expect(page.get_by_text(verdict, exact=True)).to_be_visible()
    expect(page.get_by_text("Full track not checked", exact=True)).to_be_visible()
    expect(page.get_by_text(final_badge, exact=True)).to_have_count(2)
    expect(page.get_by_text(completed_badge, exact=True).locator("visible=true")).to_have_count(1)
    expect(page.get_by_text("FINAL READY", exact=True)).to_have_count(0)
    if passed is not True:
        expect(page.get_by_text("FINAL · QA PASSED", exact=True)).to_have_count(0)
        expect(page.get_by_text("COMPLETED · QA PASSED", exact=True)).to_have_count(0)
    # Header job dropdown must also expose the QA-distinguished completed badge.
    header = page.get_by_role("banner")
    selector = header.get_by_role("button", name="M3 Watch Review Fixture", exact=True)
    selector.focus()
    selector.press("Enter")
    menu = header.get_by_role("menu")
    target_item = menu.get_by_role("menuitem", name="M3 Watch Review Fixture")
    expect(target_item.get_by_text(completed_badge, exact=True)).to_be_visible()
    page.keyboard.press("Escape")
    expect(menu).to_be_hidden()
    # Processing completion still exposes the artifact for review; a QA flag
    # must neither become a pass badge nor silently deny review downloads.
    expect(page.locator("video[src$='/download']")).to_have_count(1)
    expect(page.get_by_role("region", name="Media Monitor & Telemetry Rack").get_by_title("Download Video")).to_be_visible()
    assert page.request.get(f"{base_url}/api/jobs/{target_id}/download").status == 200
    page.get_by_role("button", name="Engineer Telemetry").click()
    page.get_by_role("button", name="[Tokens]", exact=True).click()
    expect(page.get_by_text(verdict, exact=True)).to_have_count(2)
    if passed is False:
        expect(page.get_by_text("122 segments failed", exact=True)).to_be_visible()


def test_waveform_uses_bounded_server_peaks_without_full_wav_fetch(
    page: Page, m3_react_server: tuple[str, str, Path],
) -> None:
    base_url, target_id, work = m3_react_server
    requested_urls: list[str] = []
    page.on("request", lambda req: requested_urls.append(req.url))
    page.context.route("**/*", lambda route: route.continue_()
                       if route.request.url.startswith(base_url + "/")
                       or route.request.url.startswith(("data:", "blob:")) else route.abort())
    page.route("**/api/system", lambda route: route.fulfill(
        status=200, content_type="application/json", body="{}"))
    page.add_init_script("localStorage.setItem('vi_dubber_lang', 'en')")
    update_job_state(work / target_id, message="Bounded waveform fixture")

    page.goto(base_url, wait_until="networkidle")
    canvas = page.locator("canvas[data-waveform-status]")
    expect(canvas).to_have_attribute("data-waveform-status", "ready", timeout=10000)
    expect(canvas).to_have_attribute("data-waveform-bars", "64")
    expect(canvas).to_have_attribute("data-waveform-mode", "streaming_full")

    # Switching to Track A (absent vocals.wav) degrades cleanly via 404 without fetching /work/*.wav.
    page.get_by_role("button", name="Original Vocal (A)").click()
    expect(canvas).to_have_attribute("data-waveform-status", "unavailable", timeout=10000)
    page.get_by_role("button", name="Dubbed Vietnamese (B)").click()
    expect(canvas).to_have_attribute("data-waveform-status", "ready", timeout=10000)

    assert any(f"/api/jobs/{target_id}/waveform?track=b&bars=64" in url for url in requested_urls), requested_urls
    assert not any("/work/" in url and url.endswith(".wav") for url in requested_urls), (
        f"Waveform must never fetch raw full WAV files from /work/: {requested_urls}"
    )


@pytest.mark.parametrize("code", [403, 500])
@pytest.mark.parametrize("status", ["paused", "completed"])
def test_preview_fetch_failure_clears_playback_and_can_retry(
    page: Page, m3_react_server: tuple[str, str, Path], code: int, status: str,
) -> None:
    base_url, target_id, work = m3_react_server
    page.context.route("**/*", lambda route: route.continue_()
                       if route.request.url.startswith(base_url + "/")
                       or route.request.url.startswith(("data:", "blob:")) else route.abort())
    page.route("**/api/system", lambda route: route.fulfill(
        status=200, content_type="application/json", body="{}"))
    page.add_init_script("localStorage.setItem('vi_dubber_lang', 'en')")
    result = None
    if status == "completed":
        final_path = work / target_id / "output.mp4"
        shutil.copyfile(work / target_id / "chunks/chunk_0001/preview/PREVIEW_chunk_0001.mp4", final_path)
        result = {"output": str(final_path), "duration_seconds": 10.0, "qa": {"passed": False}}
    update_job_state(work / target_id, status=status, result=result, message="Preview error fixture")
    page.goto(base_url, wait_until="networkidle")
    ready = page.locator("button:has-text('#0001'):has-text('READY')")
    expect(ready).to_be_enabled()
    ready.click()
    expect(page.locator("video[src*='/previews/']")).to_have_count(1)
    preview_route = f"**/api/jobs/{target_id}/previews"
    page.route(preview_route, lambda route: route.fulfill(status=code, body="fixture error"))
    update_job_state(work / target_id, message=f"Preview denied {code}")
    expect(page.get_by_role("alert").filter(has_text="Could not load previews")).to_be_visible(timeout=10000)
    expect(page.locator("video")).to_have_count(0)
    plays = page.get_by_title("Play / Pause", exact=True)
    expect(plays).to_have_count(2)
    for play in plays.all():
        expect(play).to_be_disabled()
    page.locator("body").press("Space")
    assert page.locator("audio").evaluate("el => el.paused")
    expect(ready).to_have_count(0)
    expect(page.get_by_title("Tải preview chunk")).to_have_count(0)
    if status == "completed":
        page.get_by_title("Chuyển sang bản Final", exact=True).click()
        expect(page.locator("video[src$='/download']")).to_have_count(1)
        expect(page.get_by_text("QA failed", exact=True)).to_be_visible()
    page.unroute(preview_route)
    page.get_by_role("button", name="Retry previews", exact=True).click()
    expect(ready).to_be_enabled()
    ready.click()
    expect(page.locator("video[src*='/previews/']")).to_have_count(1)
    expect(page.get_by_role("alert").filter(has_text="Could not load previews")).to_have_count(0)
    if status == "completed":
        page.get_by_title("Chuyển sang bản Final", exact=True).click()
        page.route(preview_route, lambda route: route.fulfill(status=code, body="fixture error"))
        update_job_state(work / target_id, message=f"Final selected; previews denied {code}")
        expect(page.get_by_role("alert").filter(has_text="Could not load previews")).to_be_visible(timeout=10000)
        expect(page.locator("video[src$='/download']")).to_have_count(1)
        header = page.get_by_role("banner")
        selector = header.get_by_role("button", name="M3 Watch Review Fixture", exact=True)
        selector.focus()
        selector.press("Enter")
        page.get_by_role("menuitem", name="M3 Library Entry").click()
        expect(header.get_by_role("button", name="M3 Library Entry", exact=True)).to_be_visible()
        expect(page.locator("video")).to_have_attribute("src", "/api/jobs/job-m3-library-entry/download")
        expect(page.get_by_role("alert").filter(has_text="Could not load previews")).to_have_count(0)


@pytest.mark.parametrize("readiness", ["blocked", "stale", "queued"])
@pytest.mark.parametrize("status", ["paused", "completed"])
def test_persisted_preview_readiness_overrides_existing_artifact(
    page: Page,
    m3_react_server: tuple[str, str, Path],
    readiness: str,
    status: str,
) -> None:
    base_url, target_id, work = m3_react_server
    page.context.route(
        "**/*",
        lambda route: route.continue_()
        if route.request.url.startswith(base_url + "/")
        or route.request.url.startswith(("data:", "blob:"))
        else route.abort(),
    )
    page.route(
        "**/api/system",
        lambda route: route.fulfill(status=200, content_type="application/json", body="{}"),
    )
    if status == "completed":
        final_path = work / target_id / "output.mp4"
        shutil.copyfile(work / target_id / "chunks/chunk_0001/preview/PREVIEW_chunk_0001.mp4", final_path)
        update_job_state(work / target_id, status=status,
                         result={"output": str(final_path), "duration_seconds": 10.0, "qa": {"passed": False}})
    page.goto(base_url, wait_until="networkidle", timeout=30000)
    if status == "paused":
        page.get_by_text("M3 Library Entry", exact=True).first.hover()
        page.get_by_text("M3 Watch Review Fixture", exact=True).first.click()
    ready = page.locator("button:has-text('#0001'):has-text('READY')")
    expect(ready).to_be_enabled()
    ready.click()
    expect(page.locator("video").first).to_have_attribute(
        "src", f"/api/jobs/{target_id}/previews/chunk_0001",
    )
    cached_previews = page.request.get(f"{base_url}/api/jobs/{target_id}/previews").json()
    page.route(
        f"**/api/jobs/{target_id}/previews",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(cached_previews),
        ),
    )

    state = json.loads((work / target_id / "state.json").read_text(encoding="utf-8"))
    metadata = state["metadata"]
    metadata["longform"]["preview_ready_chunks"] = []
    if readiness in {"blocked", "stale"}:
        metadata["longform"][f"preview_{readiness}_chunks"].append("chunk_0001")
    update_job_state(work / target_id, metadata=metadata)
    # Model a lagging preview response while readiness arrives from the real
    # persisted jobs endpoint. The newer state must win on refresh and reload.
    assert (work / target_id / "chunks/chunk_0001/manifests/preview.json").is_file()
    label = {"blocked": "QA BLOCK", "stale": "STALE", "queued": "QUEUED"}[readiness]
    chunk = page.locator(f"button:has-text('#0001'):has-text('{label}')")
    expect(chunk).to_be_disabled(timeout=10000)
    expect(page.locator("video")).to_have_count(0)
    expect(page.get_by_title("Tải preview chunk")).to_have_count(0)
    expect(page.get_by_text("1080p DUB READY", exact=True)).to_have_count(0)

    page.evaluate(
        "job => localStorage.setItem(`vi_dubber_preview_${job}`, 'chunk_0001')",
        target_id,
    )
    page.reload(wait_until="networkidle", timeout=30000)
    expect(chunk).to_be_disabled(timeout=10000)
    expect(page.locator("video")).to_have_count(0)
    expect(page.get_by_title("Tải preview chunk")).to_have_count(0)


def test_narrow_monitor_scroll_and_timeline_keyboard_remain_usable(
    page: Page, m3_react_server: tuple[str, str, Path],
) -> None:
    base_url, target_id, work = m3_react_server
    page.context.route("**/*", lambda route: route.continue_()
                       if route.request.url.startswith(base_url + "/")
                       or route.request.url.startswith(("data:", "blob:")) else route.abort())
    page.route("**/api/system", lambda route: route.fulfill(
        status=200, content_type="application/json", body="{}"))
    page.add_init_script("localStorage.setItem('vi_dubber_lang', 'en')")
    page.set_viewport_size({"width": 390, "height": 900})
    update_job_state(work / target_id, message="Narrow scroll fixture")
    page.goto(base_url, wait_until="networkidle")
    monitor = page.get_by_role("region", name="Media Monitor & Telemetry Rack")
    waveform = monitor.get_by_role("button", name="Dubbed Vietnamese (B)")
    waveform.scroll_into_view_if_needed()
    bounds = monitor.evaluate("el => ({top:el.getBoundingClientRect().top,bottom:el.getBoundingClientRect().bottom,scroll:el.scrollTop})")
    box = waveform.bounding_box()
    assert bounds["scroll"] > 0 and box and bounds["top"] <= box["y"] and box["y"] + box["height"] <= bounds["bottom"]
    slider = monitor.get_by_role("slider", name="Video seek bar")
    slider.scroll_into_view_if_needed()
    expect(slider.get_by_role("button")).to_have_count(0)
    slider.focus()
    slider.press("ArrowRight")
    page.wait_for_function("() => document.querySelector('video').currentTime > 0")
    segment = monitor.get_by_role("button", name="Segment 1: SPEAKER_00", exact=True)
    segment.focus()
    segment.press("Enter")
    page.wait_for_function("() => Math.abs(document.querySelector('video').currentTime - 4) < 0.1")
    expect(page.get_by_role("combobox", name="Speaker for segment 0", exact=True)).to_have_value("SPEAKER_00")
    assert page.evaluate("scrollX") == 0


@pytest.mark.parametrize("width", [390, 768, 1440])
def test_system_ribbon_sections_do_not_overlap(
    page: Page,
    m3_react_server: tuple[str, str, Path],
    width: int,
) -> None:
    base_url, _target_id, _work = m3_react_server
    page.context.route(
        "**/*",
        lambda route: route.continue_()
        if route.request.url.startswith(base_url + "/")
        or route.request.url.startswith(("data:", "blob:"))
        else route.abort(),
    )
    page.route(
        "**/api/system",
        lambda route: route.fulfill(status=200, content_type="application/json", body="{}"),
    )
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(base_url, wait_until="networkidle", timeout=30000)
    page.get_by_text("M3 Library Entry", exact=True).first.hover()
    page.get_by_text("M3 Watch Review Fixture", exact=True).first.click()
    for language in ("vi", "en"):
        title = "Xem chi tiết bước xử lý" if language == "vi" else "Click to view stage details"
        stage = page.get_by_title(title, exact=True)
        expect(stage).to_contain_text("62%")
        ribbon = stage.locator("xpath=../..")
        geometry = ribbon.evaluate("""bar => {
          const sections = [...bar.children].slice(0, 3).map(el => {
            const r = el.getBoundingClientRect();
            return {left:r.left, right:r.right, top:r.top, bottom:r.bottom,
                    overflow:el.scrollWidth > el.clientWidth + 1};
          });
          return {sections, width:innerWidth};
        }""")
        for index, left in enumerate(geometry["sections"]):
            assert not left["overflow"], geometry
            assert 0 <= left["left"] < left["right"] <= width, geometry
            for right in geometry["sections"][index + 1:]:
                assert left["right"] <= right["left"] or right["right"] <= left["left"] \
                    or left["bottom"] <= right["top"] or right["bottom"] <= left["top"], geometry
        # Opening details by keyboard must remain usable after the layout wraps.
        stage.focus()
        stage.press("Enter")
        expect(page.get_by_role("dialog")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.get_by_role("dialog")).to_have_count(0)
        artifact_dir = WORK_DIR / "artifacts" / "vi-narrow-ticker-proof"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(artifact_dir / f"{width}-{language}.png"), full_page=True)
        if language == "vi":
            # Seed the existing preference for the second fixture language.
            # The separate header overflow is outside this ticker geometry test.
            page.evaluate("localStorage.setItem('vi_dubber_lang', 'en')")
            page.reload(wait_until="networkidle", timeout=30000)
            page.get_by_text("M3 Library Entry", exact=True).first.hover()
            page.get_by_text("M3 Watch Review Fixture", exact=True).first.click()


@pytest.mark.parametrize("width", [390, 768, 1440])
def test_header_controls_stay_reachable_without_page_horizontal_scroll(
    page: Page,
    m3_react_server: tuple[str, str, Path],
    width: int,
) -> None:
    base_url, _target_id, _work = m3_react_server
    page.context.route(
        "**/*",
        lambda route: route.continue_()
        if route.request.url.startswith(base_url + "/")
        or route.request.url.startswith(("data:", "blob:"))
        else route.abort(),
    )
    page.route(
        "**/api/system",
        lambda route: route.fulfill(status=200, content_type="application/json", body="{}"),
    )
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(base_url, wait_until="networkidle", timeout=30000)
    header = page.get_by_role("banner")

    def assert_controls_fit() -> None:
        bounds = header.locator("button:visible, a:visible").evaluate_all("""els => ({
          scrollX, controls: els.map(el => {
            const r = el.getBoundingClientRect();
            return {name: el.getAttribute('aria-label') || el.textContent,
                    left:r.left, right:r.right, top:r.top, bottom:r.bottom};
          })
        })""")
        assert bounds["scrollX"] == 0, bounds
        assert all(0 <= box["left"] < box["right"] <= width for box in bounds["controls"]), bounds

    expect(header.get_by_role("button", name="M3 Library Entry")).to_be_visible()
    assert_controls_fit()
    language = header.get_by_role("button", name="Switch language")
    language.click()
    expect(language).to_have_text("EN")
    assert_controls_fit()
    theme = header.get_by_role("button", name="Light Mode")
    language.focus()
    language.press("Tab")
    expect(theme).to_be_focused()
    theme.press("Enter")
    expect(page.locator("html")).not_to_have_class("dark")
    assert_controls_fit()

    for control in (
        header.get_by_role("button", name="Catalog", exact=True),
        header.get_by_role("button", name="Import Video / YouTube", exact=True),
    ):
        control.focus()
        control.press("Enter")
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        assert dialog.evaluate("el => el.contains(document.activeElement)")
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(control).to_be_focused()
        assert_controls_fit()

    job_selector = header.get_by_role("button", name="M3 Library Entry")
    job_selector.focus()
    job_selector.press("Enter")
    menu = header.get_by_role("menu")
    expect(menu).to_be_visible()
    menu_box = menu.bounding_box()
    assert menu_box and 0 <= menu_box["x"] and menu_box["x"] + menu_box["width"] <= width
    menu.get_by_role("menuitem", name="M3 Watch Review Fixture").click()
    expect(header.get_by_role("button", name="M3 Watch Review Fixture")).to_be_visible()
    assert_controls_fit()
    artifact_dir = WORK_DIR / "artifacts" / "vi-narrow-header-proof"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(artifact_dir / f"{width}-en-light.png"), full_page=True)


def test_m3_library_watch_review_edit_stale_flow(
    page: Page,
    m3_react_server: tuple[str, str, Path],
) -> None:
    base_url, target_id, work = m3_react_server
    artifact_dir = WORK_DIR / "artifacts" / "m3-vi-ui-proof-r2"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(
            f"{msg.text} @ {(msg.location or {}).get('url', '')}"
        )
        if msg.type == "error"
        else None,
    )
    page.add_init_script("localStorage.clear()")
    page.route(
        "**/api/system",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "gpu_name": "M3 isolated fixture",
                    "gpu_vram_used_bytes": 0,
                    "gpu_vram_total_bytes": 0,
                    "gpu_utilization_pct": 0,
                    "cpu_utilization_pct": 0,
                    "active_jobs_count": 0,
                    "webgpt_connected": False,
                    "webgpt_model": "fixture",
                    "webgpt_port": 17850,
                    "server_uptime_seconds": 0,
                    "websocket_connected": True,
                }
            ),
        ),
    )
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(base_url, wait_until="networkidle", timeout=30000)

    shared_control = page.locator("button.ui-button.ui-button--neutral").first
    expect(shared_control).to_be_visible()
    shared_control_style = page.evaluate(
        """(el) => {
          const style = getComputedStyle(el);
          return {
            focus: style.getPropertyValue('--ui-focus').trim(),
            background: style.backgroundColor,
            borderStyle: style.borderStyle,
          };
        }""",
        shared_control.element_handle(),
    )
    assert shared_control_style["focus"] in {"#2563eb", "#60a5fa"}
    assert shared_control_style["background"] != "rgba(0, 0, 0, 0)"
    assert shared_control_style["borderStyle"] == "solid"

    # Library-like archive selector: prove the target is chosen from persisted jobs.
    archive_trigger = page.get_by_text("M3 Library Entry", exact=True).first
    expect(archive_trigger).to_be_visible(timeout=10000)
    archive_trigger.hover()
    target_choice = page.get_by_text("M3 Watch Review Fixture", exact=True).first
    expect(target_choice).to_be_visible(timeout=5000)
    target_choice.click()
    expect(page.get_by_text("M3 Watch Review Fixture", exact=True).first).to_be_visible()

    # Watch: persisted bilingual transcript and all representative preview states.
    expect(page.get_by_text("The first source sentence.", exact=True)).to_be_visible(timeout=10000)
    expect(page.locator("button:has-text('#0001'):has-text('READY')")).to_be_enabled()
    expect(page.locator("button:has-text('#0002'):has-text('QA BLOCK')")).to_be_disabled()
    expect(page.locator("button:has-text('#0003'):has-text('TTS')")).to_be_disabled()
    expect(page.locator("button:has-text('#0004'):has-text('QUEUED')")).to_be_disabled()
    page.locator("button:has-text('#0001'):has-text('READY')").click()
    expect(page.get_by_text("PREVIEW · Part 1/4", exact=False)).to_be_visible(timeout=5000)
    video = page.locator("video").first
    expect(video).to_be_visible()
    page.wait_for_function(
        "el => el.readyState >= 1",
        arg=video.element_handle(),
        timeout=10000,
    )
    download_link = page.get_by_title("Tải preview chunk")
    expect(download_link).to_be_visible()
    assert download_link.get_attribute("href") == (
        f"/api/jobs/{target_id}/previews/chunk_0001?download=true"
    )

    # Native fullscreen -> Import must await fullscreen exit before the dialog
    # takes focus, then keep keyboard focus contained and restore it on close.
    fullscreen_button = page.get_by_title("Fullscreen")
    fullscreen_button.click()
    page.wait_for_function("document.fullscreenElement !== null", timeout=5000)
    import_button = page.locator('button[title="Import Video / YouTube"]').first
    import_button.click()
    page.wait_for_function("document.fullscreenElement === null", timeout=5000)
    dialog = page.locator('[role="dialog"][aria-modal="true"]')
    expect(dialog).to_be_visible()
    assert page.evaluate(
        "(el) => el.contains(document.activeElement)",
        dialog.element_handle(),
    )
    page.keyboard.press("Tab")
    assert page.evaluate(
        "(el) => el.contains(document.activeElement)",
        dialog.element_handle(),
    )
    page.keyboard.press("Shift+Tab")
    assert page.evaluate(
        "(el) => el.contains(document.activeElement)",
        dialog.element_handle(),
    )
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    assert page.evaluate(
        "(el) => document.activeElement === el",
        import_button.element_handle(),
    )

    # Intentional segment navigation must seek even while media is playing.
    page.evaluate("(el) => el.play()", video.element_handle())
    page.wait_for_function(
        "el => !el.paused && el.currentTime > 0.2",
        arg=video.element_handle(),
        timeout=5000,
    )
    page.get_by_text("The second ready sentence.", exact=True).click()
    page.wait_for_function(
        "el => Math.abs(el.currentTime - 4.0) < 0.75 && !el.paused",
        arg=video.element_handle(),
        timeout=5000,
    )
    page.screenshot(path=str(artifact_dir / "01-1440-watch-ready.png"), full_page=True)

    # Review: use the real PATCH endpoint. The product backend must invalidate
    # only the edited chunk and the UI must stop advertising its old preview.
    editor = page.locator("textarea").first
    expect(editor).to_have_value("Câu dịch đầu tiên.")
    editor.fill("Câu dịch M3 đã chỉnh.")
    with page.expect_response(
        lambda response: response.request.method == "PATCH"
        and f"/api/jobs/{target_id}/segments/0" in response.url
    ) as response_info:
        page.get_by_title("Lưu").first.click()
    response = response_info.value
    assert response.status == 200
    receipt = response.json()["receipt"]
    assert receipt["kind"] == "content_edit"
    assert receipt["longform_chunk_id"] == "chunk_0001"

    expect(page.get_by_text("chunk stale sau edit", exact=False)).to_be_visible(timeout=10000)
    stale_chunk = page.locator("button:has-text('#0001'):has-text('STALE')")
    expect(stale_chunk).to_be_disabled()
    expect(page.get_by_text("PREVIEW · Part 1/4", exact=False)).to_have_count(0)

    state = json.loads((work / target_id / "state.json").read_text(encoding="utf-8"))
    longform = state["metadata"]["longform"]
    assert longform["preview_ready_chunks"] == []
    assert longform["preview_stale_chunks"] == ["chunk_0001"]
    assert longform["preview_blocked_chunks"] == ["chunk_0002"]
    assert not (
        work
        / target_id
        / "chunks"
        / "chunk_0001"
        / "manifests"
        / "preview.json"
    ).exists()
    page.screenshot(path=str(artifact_dir / "02-1440-review-stale.png"), full_page=True)

    # Accessibility/responsive proof: keyboard focus is visible, Vietnamese glyphs
    # survive, and the product page itself does not overflow at M3 target widths.
    editor.focus()
    assert page.evaluate("(el) => document.activeElement === el", editor.element_handle())
    editor.press("Tab")
    assert page.evaluate("document.activeElement !== document.body")

    responsive: dict[str, dict[str, int | bool]] = {}
    for width, height in ((768, 1024), (390, 844), (360, 800)):
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(250)
        expect(editor).to_be_visible()
        expect(editor).to_have_value("Câu dịch M3 đã chỉnh.")
        responsive[str(width)] = _layout_metrics(page)
        assert responsive[str(width)]["scrollWidth"] <= width
        page.screenshot(
            path=str(artifact_dir / f"0{3 if width == 768 else 4}-{width}-review-stale.png"),
            full_page=True,
        )

    # Both themes must preserve the same stale state and interaction contract.
    page.set_viewport_size({"width": 1440, "height": 900})
    page.get_by_label("Chế độ Sáng").click()
    expect(page.locator("html")).not_to_have_class("dark")
    expect(stale_chunk).to_be_disabled()
    page.screenshot(path=str(artifact_dir / "05-1440-light-stale.png"), full_page=True)

    # Media decode/network failures would be console errors in this proof. Ignore
    # React DevTools notices; they are not console.error.
    assert console_errors == [], "\n".join(console_errors)
    (artifact_dir / "receipt.json").write_text(
        json.dumps(
            {
                "scope": "M3 VI representative Library -> Watch -> Review edit/stale product fixture",
                "backend": "FastAPI create_app with isolated persisted WORK_DIR",
                "frontend": "built React/Vite dist from current HEAD",
                "target_job": target_id,
                "states_proved": ["ready", "qa-blocked", "processing", "queued", "stale-after-edit"],
                "responsive": responsive,
                "console_errors": console_errors,
                "screenshots": sorted(p.name for p in artifact_dir.glob("*.png")),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_m5_catalog_panel_search_filter_select_and_reload(
    page: Page,
    m3_react_server: tuple[str, str, Path],
) -> None:
    """Prove the local catalog survives browser reopen and drives job selection."""

    base_url, _target_id, _work = m3_react_server
    console_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(
            f"{msg.text} @ {(msg.location or {}).get('url', '')}"
        )
        if msg.type == "error"
        else None,
    )
    page.add_init_script("localStorage.clear()")
    page.route(
        "**/api/system",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "gpu_name": "M5 catalog fixture",
                    "gpu_vram_used_bytes": 0,
                    "gpu_vram_total_bytes": 0,
                    "gpu_utilization_pct": 0,
                    "cpu_utilization_pct": 0,
                    "active_jobs_count": 0,
                    "webgpt_connected": False,
                    "webgpt_model": "fixture",
                    "webgpt_port": 17850,
                    "server_uptime_seconds": 0,
                    "websocket_connected": True,
                }
            ),
        ),
    )
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(base_url, wait_until="networkidle", timeout=30000)

    open_catalog = page.get_by_role("button", name="Catalog")
    expect(open_catalog).to_be_visible(timeout=10000)
    open_catalog.click()
    dialog = page.get_by_role("dialog", name="Catalog cục bộ")
    expect(dialog).to_be_visible(timeout=5000)
    target_row = dialog.get_by_role("button", name="M3 Watch Review Fixture")
    decoy_row = dialog.get_by_role("button", name="M3 Library Entry")
    search = dialog.get_by_placeholder("Tìm theo tên hoặc nguồn...")
    close_button = dialog.get_by_role("button", name="Đóng")
    expect(search).to_have_attribute("maxlength", "256")
    expect(search).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(close_button).to_be_focused()
    page.keyboard.press("Shift+Tab")
    assert page.evaluate(
        "(el) => el.contains(document.activeElement)",
        dialog.element_handle(),
    )
    search.focus()
    expect(target_row).to_be_visible(timeout=5000)
    expect(decoy_row).to_be_visible(timeout=5000)
    expect(target_row).to_contain_text("Review: in_review")
    expect(target_row).to_contain_text("catalog-m3-target-r1")

    # The availability filter is backed by the API query, not a client-side
    # guess; selecting available removes the missing decoy row.
    dialog.locator("#catalog-availability").select_option("available")
    expect(target_row).to_be_visible(timeout=5000)
    expect(decoy_row).to_have_count(0)

    search.fill("M3 Watch Review Fixture")
    expect(target_row).to_be_visible(timeout=5000)
    target_row.click()
    expect(dialog).to_have_count(0)
    assert page.evaluate(
        "(el) => document.activeElement === el",
        open_catalog.element_handle(),
    )

    # Selection updates the same persisted job state used by Watch/Review.
    expect(page.get_by_role("button", name="M3 Watch Review Fixture").first).to_be_visible()
    page.reload(wait_until="networkidle", timeout=30000)
    page.get_by_role("button", name="Catalog").click()
    dialog = page.get_by_role("dialog", name="Catalog cục bộ")
    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog.get_by_role("button", name="M3 Watch Review Fixture")).to_be_visible(timeout=5000)
    expect(dialog.get_by_text("M3 Library Entry", exact=True)).to_be_visible(timeout=5000)
    expect(dialog.locator("#catalog-availability")).to_have_value("")
    assert page.url == base_url + "/"
    assert console_errors == [], "\n".join(console_errors)


def test_status_honesty_polling_and_single_request_accept_all(
    page: Page,
    m3_react_server: tuple[str, str, Path],
) -> None:
    """Verify honest transport/QA/terminal statuses and single-POST Accept All."""
    base_url, target_id, work = m3_react_server
    console_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(
            f"{msg.text} @ {(msg.location or {}).get('url', '')}"
        )
        if msg.type == "error"
        else None,
    )
    page.context.route(
        "**/*",
        lambda route: route.continue_()
        if route.request.url.startswith(base_url + "/")
        or route.request.url.startswith(("data:", "blob:"))
        else route.fulfill(status=200, content_type="text/css", body="")
        if "fonts.googleapis.com" in route.request.url
        else route.abort(),
    )
    page.route(
        "**/api/system",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "gpu_name": "PR4 status fixture",
                    "gpu_vram_used_bytes": 0,
                    "gpu_vram_total_bytes": 0,
                    "gpu_utilization_pct": 0,
                    "cpu_utilization_pct": 0,
                    "active_jobs_count": 0,
                    "webgpt_connected": False,
                    "webgpt_model": "fixture",
                    "webgpt_port": 17850,
                    "server_uptime_seconds": 10,
                    "websocket_connected": False,
                    "transport_mode": "http_polling",
                }
            ),
        ),
    )
    page.add_init_script("localStorage.setItem('vi_dubber_lang', 'en')")

    # Seed multiple unreviewed segments + completed QA-failed state (Job12 pattern).
    segments = [
        {
            "id": idx,
            "start": float(idx) * 2.0,
            "end": float(idx) * 2.0 + 1.5,
            "text": f"Source sentence {idx}",
            "vi": f"Ban dich {idx}",
            "speaker": "SPEAKER_00",
            "review_status": "unreviewed",
        }
        for idx in range(5)
    ]
    (work / target_id / "segments_vi.json").write_text(
        json.dumps(segments, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    final_path = work / target_id / "output.mp4"
    shutil.copyfile(
        work / target_id / "chunks/chunk_0001/preview/PREVIEW_chunk_0001.mp4",
        final_path,
    )
    update_job_state(
        work / target_id,
        status="completed",
        stage="complete",
        progress=1.0,
        result={
            "output": str(final_path),
            "duration_seconds": 10.0,
            "elapsed_seconds": 5.0,
            "qa": {"similarity": 0.91, "passed": False},
        },
        message="Completed with QA failure",
    )

    batch_posts: list[str] = []
    segment_patches: list[str] = []

    def _track_request(req) -> None:
        if req.method == "POST" and "/review/accept-all" in req.url:
            batch_posts.append(req.url)
        elif req.method == "PATCH" and "/segments/" in req.url:
            segment_patches.append(req.url)

    page.on("request", _track_request)
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(base_url, wait_until="networkidle", timeout=30000)

    # 1. Honest transport indicator: http_polling renders POLLING 2s (never WS LIVE).
    transport = page.locator('[data-transport-mode="http_polling"]')
    expect(transport).to_be_visible(timeout=10000)
    expect(transport).to_contain_text("POLLING 2s")
    expect(page.get_by_text("WS LIVE", exact=True)).to_have_count(0)

    # 2. Honest SystemBar badge for completed-with-QA-failed job.
    status_badge = page.locator('[data-job-status="completed"][data-qa-state="failed"]')
    expect(status_badge).to_be_visible(timeout=10000)
    expect(status_badge).to_contain_text("COMPLETED · QA FAILED")

    # 3. Single-POST Accept All: must send exactly 1 batch POST and 0 per-segment PATCH calls.
    accept_all_btn = page.get_by_role("button", name="Accept All (5)")
    expect(accept_all_btn).to_be_enabled(timeout=10000)
    accept_all_btn.click()
    expect(accept_all_btn).to_be_disabled(timeout=10000)
    assert len(batch_posts) == 1
    assert segment_patches == []
    persisted = json.loads((work / target_id / "segments_vi.json").read_text(encoding="utf-8"))
    assert all(seg["review_status"] == "accepted" for seg in persisted)

    # 4. Verify completed QA-unverified and QA-passed states in SystemBar.
    update_job_state(
        work / target_id,
        status="completed",
        stage="complete",
        progress=1.0,
        result={
            "output": str(final_path),
            "duration_seconds": 10.0,
            "elapsed_seconds": 5.0,
            "qa": {"similarity": 0.95, "passed": None},
        },
        message="Completed with unverified QA",
    )
    unverified_badge = page.locator('[data-job-status="completed"][data-qa-state="unverified"]')
    expect(unverified_badge).to_be_visible(timeout=10000)
    expect(unverified_badge).to_contain_text("COMPLETED · QA UNVERIFIED")

    update_job_state(
        work / target_id,
        status="completed",
        stage="complete",
        progress=1.0,
        result={
            "output": str(final_path),
            "duration_seconds": 10.0,
            "elapsed_seconds": 5.0,
            "qa": {"similarity": 0.99, "passed": True},
        },
        message="Completed with QA passed",
    )
    passed_badge = page.locator('[data-job-status="completed"][data-qa-state="passed"]')
    expect(passed_badge).to_be_visible(timeout=10000)
    expect(passed_badge).to_contain_text("COMPLETED · QA PASSED")

    # 5. Terminal failed & cancelled jobs render honest badges in SystemBar (never green COMPLETED).
    update_job_state(
        work / target_id,
        status="failed",
        stage="translation",
        progress=0.5,
        message="Fixture failure",
    )
    expect(page.locator('[data-job-status="failed"]')).to_be_visible(timeout=10000)
    expect(page.locator('[data-job-status="failed"]')).to_contain_text("FAILED")

    update_job_state(
        work / target_id,
        status="cancelled",
        stage="translation",
        progress=0.5,
        message="Fixture cancelled",
    )
    expect(page.locator('[data-job-status="cancelled"]')).to_be_visible(timeout=10000)
    expect(page.locator('[data-job-status="cancelled"]')).to_contain_text("CANCELLED")

    assert console_errors == [], "\n".join(console_errors)


def test_10k_segment_12h_job_virtualizes_reviewer_and_bounds_timeline_markers(
    page: Page,
    m3_react_server: tuple[str, str, Path],
) -> None:
    """Prove a synthetic 10,000-segment 12h job renders cleanly with bounded DOM nodes."""
    base_url, target_id, work = m3_react_server
    console_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(
            f"{msg.text} @ {(msg.location or {}).get('url', '')}"
        )
        if msg.type == "error"
        else None,
    )
    page.context.route(
        "**/*",
        lambda route: route.continue_()
        if route.request.url.startswith(base_url + "/")
        or route.request.url.startswith(("data:", "blob:"))
        else route.fulfill(status=200, content_type="text/css", body="")
        if "fonts.googleapis.com" in route.request.url
        else route.abort(),
    )
    page.route(
        "**/api/system",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "gpu_name": "10k virtualization fixture",
                    "gpu_vram_used_bytes": 0,
                    "gpu_vram_total_bytes": 0,
                    "gpu_utilization_pct": 0,
                    "cpu_utilization_pct": 0,
                    "active_jobs_count": 0,
                    "webgpt_connected": False,
                    "webgpt_model": "fixture",
                    "webgpt_port": 17850,
                    "server_uptime_seconds": 10,
                    "websocket_connected": False,
                    "transport_mode": "http_polling",
                }
            ),
        ),
    )
    page.add_init_script("localStorage.setItem('vi_dubber_lang', 'en')")

    segment_count = 10_000
    duration_seconds = 43_200.0  # 12 hours
    step = duration_seconds / segment_count
    segments = [
        {
            "id": idx,
            "start": round(idx * step, 3),
            "end": round((idx + 1) * step - 0.1, 3),
            "text": f"Longform English sentence {idx}",
            "vi": f"Cau tieng Viet so {idx}",
            "speaker": "SPEAKER_00" if idx % 2 == 0 else "SPEAKER_01",
            "review_status": "needs_review" if idx % 500 == 0 else "unreviewed",
            "flagged": idx % 250 == 0,
            "overflow": idx % 1000 == 0,
        }
        for idx in range(segment_count)
    ]
    (work / target_id / "segments_vi.json").write_text(
        json.dumps(segments, ensure_ascii=False),
        encoding="utf-8",
    )
    update_job_state(
        work / target_id,
        status="paused",
        stage="review",
        progress=0.95,
        metadata={
            "input_name": "12h_master.mp4",
            "profile": "balanced_fast",
            "source_mode": "Local",
            "longform": {"enabled": False},
        },
        result={
            "duration_seconds": duration_seconds,
            "elapsed_seconds": 7200.0,
        },
        message="10k 12h virtualization fixture",
    )

    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(base_url, wait_until="networkidle", timeout=30000)

    expect(page.get_by_text("10000 TOTAL", exact=True)).to_be_visible(timeout=15000)

    # 1. SegmentReviewer must mount only a bounded visible window (< 100 cards) for 10,000 segments.
    cards = page.locator('[data-segment-card="true"]')
    expect(cards.first).to_be_visible(timeout=10000)
    mounted_cards_initial = cards.count()
    assert 1 <= mounted_cards_initial < 100, f"expected < 100 mounted cards, got {mounted_cards_initial}"

    # 2. VideoPlayer scrub bar must mount bounded bucketed markers (<= 120 < 400) with flagged highlight.
    markers = page.locator('[data-timeline-marker="true"][data-bucketed="true"]')
    expect(markers.first).to_be_visible(timeout=10000)
    marker_count = markers.count()
    assert 60 <= marker_count <= 120, f"expected 60..120 bucketed timeline markers, got {marker_count}"
    flagged_markers = page.locator('[data-timeline-marker="true"][data-flagged="true"]')
    assert flagged_markers.count() > 0

    # 3. Clicking a deep timeline bucket must jump and mount a high-index segment while staying < 100 cards.
    deep_marker = markers.nth(marker_count - 5)
    deep_seg_id = deep_marker.get_attribute("data-segment-id")
    assert deep_seg_id is not None and int(deep_seg_id) > 8000, f"expected deep segment > 8000, got {deep_seg_id}"
    deep_marker.click()
    expect(page.locator(f'[data-segment-card="true"][data-segment-id="{deep_seg_id}"]')).to_be_visible(
        timeout=10000
    )
    assert cards.count() < 100

    # 4. Search filter finds segment #9876 cleanly without rendering all 10k cards.
    search_input = page.get_by_placeholder("Filter segments by text, speaker, or keywords...")
    search_input.fill("9876")
    target_card = page.locator('[data-segment-card="true"][data-segment-id="9876"]')
    expect(target_card).to_be_visible(timeout=10000)
    assert cards.count() == 1
    expect(target_card).to_contain_text("Longform English sentence 9876")

    # 5. Clear search and verify keyboard navigation advances cleanly while remaining virtualized.
    search_input.fill("")
    expect(page.locator('[data-virtualized-list="true"]')).to_have_attribute("data-total-segments", "10000")
    assert cards.count() < 100
    print(f"DOM_PROOF_10K: cards={mounted_cards_initial} markers={marker_count} deep_seg={deep_seg_id}")

    assert console_errors == [], "\n".join(console_errors)

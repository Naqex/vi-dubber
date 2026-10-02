"""Bounded loopback UI audit; synthetic media only, no provider or retained job."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tests"))
from test_m3_react_ui_playwright import _find_free_port, _seed_m3_fixture
import vi_dubber.api as api_mod
from vi_dubber.api import create_app
from vi_dubber.jobs import update_job_state

AXE = REPO.parents[1] / ".artifacts/wm-integration-quality-tools/node_modules/axe-core/axe.min.js"
MATRIX = [(390, "vi", "light"), (390, "en", "dark"),
          (768, "vi", "dark"), (768, "en", "light"),
          (1440, "vi", "light"), (1440, "en", "dark")]


def run(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    records = []
    def source_identity() -> str:
        digest = hashlib.sha256()
        paths = [*sorted((REPO / "frontend/src").rglob("*")),
                 *sorted((REPO / "frontend/dist").rglob("*")),
                 REPO / "tests/test_m3_react_ui_playwright.py", Path(__file__)]
        for path in paths:
            if path.is_file():
                digest.update(path.relative_to(REPO).as_posix().encode())
                digest.update(b"\0")
                digest.update(path.read_bytes())
        return digest.hexdigest()
    source_before = source_identity()
    original_work = api_mod.WORK_DIR
    with tempfile.TemporaryDirectory(prefix="vi-ui-audit-") as folder:
        work = Path(folder) / "work"
        work.mkdir()
        target_id, _ = _seed_m3_fixture(work)
        target = work / target_id
        state = json.loads((target / "state.json").read_text(encoding="utf-8"))
        metadata = state["metadata"]
        metadata["longform"]["preview_stale_chunks"] = ["chunk_0004"]
        shutil.copyfile(target / "chunks/chunk_0001/preview/PREVIEW_chunk_0001.mp4", target / "output.mp4")
        api_mod.WORK_DIR = work
        port = _find_free_port()
        base = f"http://127.0.0.1:{port}"
        server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port,
                                             log_level="error", access_log=False))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("Synthetic server startup failed")
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                for width, lang, theme in MATRIX:
                    update_job_state(target, status="paused", stage="tts", result=None,
                                     metadata=metadata, message="audit ready")
                    context = browser.new_context(viewport={"width": width, "height": 900},
                                                  reduced_motion="reduce")
                    context.route("**/*", lambda route: route.continue_()
                                  if route.request.url.startswith(base + "/")
                                  or route.request.url.startswith(("data:", "blob:")) else route.abort())
                    page = context.new_page()
                    page.route("**/api/system", lambda route: route.fulfill(
                        status=200, content_type="application/json", body="{}"))
                    page.add_init_script(f"localStorage.setItem('vi_dubber_lang', '{lang}');"
                                         f"localStorage.setItem('vi_dubber_theme', '{theme}');")
                    page.goto(base, wait_until="networkidle")
                    expect(page.get_by_role("banner").get_by_role("button", name="M3 Watch Review Fixture")).to_be_visible()
                    page.wait_for_function("theme => document.documentElement.classList.contains('dark') === (theme === 'dark')", arg=theme)
                    page.add_style_tag(content="*,*::before,*::after{animation:none!important;transition:none!important}")
                    stable_style = page.evaluate("async () => {const read=()=>[getComputedStyle(document.body).backgroundColor,getComputedStyle(document.querySelector('main')).color];const before=read();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));return {before,after:read()}}")
                    assert stable_style["before"] == stable_style["after"], stable_style

                    def capture(name: str, scan: bool = False) -> None:
                        # Settle two animation frames after state/style updates.
                        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                        entry = {"width": width, "language": lang, "theme": theme, "state": name,
                                 "preview_video": page.locator("video[src*='/previews/']").count(),
                                 "final_video": page.locator("video[src$='/download']").count(),
                                 "body_text": page.locator("body").inner_text(),
                                 "geometry": page.evaluate("() => ({scrollX, width:innerWidth, scrollWidth:document.documentElement.scrollWidth})"),
                                 "stable_theme_style": stable_style}
                        if scan:
                            page.add_script_tag(path=str(AXE))
                            entry["axe"] = page.evaluate("async () => {const r = await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}}); return {version:r.testEngine.version, violations:r.violations.map(v=>({id:v.id,impact:v.impact,description:v.description,nodes:v.nodes.map(n=>({target:n.target,html:n.html,failureSummary:n.failureSummary}))})), incomplete:r.incomplete.map(v=>({id:v.id,nodes:v.nodes.length}))}}")
                        page.screenshot(path=str(output / f"{width}-{lang}-{theme}-{name}.png"), full_page=True)
                        records.append(entry)
                        (output / "report.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

                    expect(page.locator("button:has-text('#0001'):has-text('READY')")).to_be_enabled()
                    expect(page.locator("button:has-text('#0002'):has-text('QA BLOCK')")).to_be_disabled()
                    expect(page.locator("button:has-text('#0004'):has-text('STALE')")).to_be_disabled()
                    capture("preview-matrix", scan=True)
                    for code in (403, 500):
                        preview_route = f"**/api/jobs/{target_id}/previews"
                        page.route(preview_route, lambda route, request, code=code: route.fulfill(status=code, body="denied" if code == 403 else "fixture error"))
                        with page.expect_response(lambda response: response.url.endswith(f"/{target_id}/previews") and response.status == code):
                            update_job_state(target, metadata=metadata, message=f"audit preview {code}")
                        expect(page.get_by_role("alert")).to_be_visible()
                        expect(page.locator("video[src*='/previews/']")).to_have_count(0)
                        capture(f"preview-{code}")
                        page.unroute(preview_route)
                        with page.expect_response(lambda response: response.url.endswith(f"/{target_id}/previews") and response.status == 200):
                            update_job_state(target, metadata=metadata, message=f"audit recovered {code}")
                        expect(page.locator("button:has-text('#0001'):has-text('READY')")).to_be_enabled()

                    qa = {"similarity": 0.98, "threshold": 0.78, "passed": False,
                          "mode": "risk_segments", "global_passed": None, "full_track_skipped": True,
                          "segment_summary": {"final_failed": 122}}
                    final_metadata = json.loads(json.dumps(metadata))
                    final_metadata["longform"]["preview_ready_chunks"] = []
                    final_metadata["longform"]["preview_blocked_chunks"].append("chunk_0001")
                    update_job_state(target, status="completed", stage="complete", progress=1.0,
                                     result={"output": str(target / "output.mp4"), "duration_seconds": 10.0, "qa": qa},
                                     metadata=final_metadata, message="audit Final QA failed")
                    final_choice = page.get_by_title("Chuyển sang bản Final", exact=True)
                    expect(final_choice).to_be_visible()
                    final_choice.click()
                    expect(page.locator("video[src$='/download']")).to_have_count(1)
                    page.reload(wait_until="networkidle")
                    expect(page.locator("video[src$='/download']")).to_have_count(1)
                    page.get_by_role("button", name="[Tokens]", exact=True).count()
                    drawer = page.get_by_role("button", name="Bảng kỹ thuật" if lang == "vi" else "Engineer Telemetry")
                    drawer.click()
                    page.get_by_role("button", name="[Tokens]", exact=True).click()
                    expect(page.get_by_text("QA chưa đạt" if lang == "vi" else "QA failed", exact=True)).to_have_count(2)
                    expect(page.get_by_text("122 đoạn chưa đạt" if lang == "vi" else "122 segments failed", exact=True)).to_be_visible()
                    capture("final-qa-failed", scan=True)

                    page.route("**/api/jobs", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
                    page.reload(wait_until="networkidle")
                    expect(page.locator("video")).to_have_count(0)
                    capture("empty", scan=True)
                    context.close()
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError("Synthetic server did not stop")
            api_mod.WORK_DIR = original_work
    source_after = source_identity()
    failures = [r for r in records if r.get("axe", {}).get("violations")
                or r["geometry"]["scrollX"] != 0
                or r["geometry"]["scrollWidth"] > r["geometry"]["width"]]
    receipt = {"records": len(records), "axe_scans": sum("axe" in r for r in records),
               "failures": len(failures), "source_before": source_before,
               "source_after": source_after, "synthetic_server_stopped": True,
               "scope": "loopback synthetic fixture; no provider, retained job or full WCAG acceptance"}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    assert len(records) == 30 and source_before == source_after and not failures, receipt
    print(json.dumps({"records": len(records), "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)

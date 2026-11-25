from __future__ import annotations

from pathlib import Path

import pytest

from vi_dubber.preflight import PreflightCheck, raise_for_preflight, run_preflight


def _config() -> dict:
    return {
        "profile": "balanced_best",
        "reliability": {"min_free_disk_gb": 0.0},
        "tts": {"device": "cpu"},
        "asr": {"device": "cpu"},
        "qa": {"semantic": {"enabled": False}},
    }


def test_preflight_local_provider_reports_missing_input(tmp_path: Path, monkeypatch) -> None:
    import vi_dubber.preflight as preflight

    model = tmp_path / "models" / "llm" / "Qwen--Qwen3-14B-GGUF" / "Qwen3-14B-Q4_K_M.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"model")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(preflight, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(preflight, "WORK_DIR", work)
    monkeypatch.setattr(preflight, "configure_runtime", lambda: None)
    monkeypatch.setattr(
        preflight,
        "webgpt_route_info",
        lambda: (_ for _ in ()).throw(AssertionError("local preflight must not probe WebGPT")),
    )

    checks = run_preflight(
        _config(),
        translation_provider="local",
        input_path=tmp_path / "missing.mp4",
    )
    by_name = {item.name: item for item in checks}
    assert by_name["input"].status == "error"
    assert by_name["translation"].status == "ok"
    assert by_name["retry_policy"].status == "ok"


def test_preflight_strict_typesafe_requires_key(tmp_path: Path, monkeypatch) -> None:
    import vi_dubber.preflight as preflight

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(preflight, "WORK_DIR", work)
    monkeypatch.setattr(preflight, "configure_runtime", lambda: None)
    monkeypatch.setattr(preflight, "webgpt_route_info", lambda _config=None: {"ready": True, "model": "test"})
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    config = _config()
    config["profile"] = "max_quality"
    config["qa"]["semantic"]["enabled"] = True

    checks = run_preflight(config, translation_provider="webgpt")
    assert {item.name: item.status for item in checks}["typesafe"] == "error"


def test_raise_for_preflight_only_blocks_errors() -> None:
    raise_for_preflight([PreflightCheck("warn", "warning", "degraded")])
    with pytest.raises(RuntimeError, match="disk"):
        raise_for_preflight([PreflightCheck("disk", "error", "low")])


def test_preflight_hybrid_warns_when_local_fallback_is_missing(tmp_path: Path, monkeypatch) -> None:
    import vi_dubber.preflight as preflight

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(preflight, "WORK_DIR", work)
    monkeypatch.setattr(preflight, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(preflight, "configure_runtime", lambda: None)
    monkeypatch.setattr(preflight, "webgpt_route_info", lambda _config=None: {"ready": True, "model": "test"})

    checks = run_preflight(_config(), translation_provider="hybrid")
    translation = {item.name: item for item in checks}["translation"]

    assert translation.status == "warning"
    assert "thiếu local fallback" in translation.detail


def test_preflight_turns_route_probe_failure_into_actionable_error(tmp_path: Path, monkeypatch) -> None:
    import vi_dubber.preflight as preflight

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(preflight, "WORK_DIR", work)
    monkeypatch.setattr(preflight, "configure_runtime", lambda: None)
    monkeypatch.setattr(
        preflight,
        "webgpt_route_info",
        lambda _config=None: (_ for _ in ()).throw(RuntimeError("route probe failed")),
    )

    checks = run_preflight(_config(), translation_provider="webgpt")
    translation = {item.name: item for item in checks}["translation"]

    assert translation.status == "error"
    assert "route probe failed" in translation.detail


def test_preflight_rejects_unbounded_retry_budget(tmp_path: Path, monkeypatch) -> None:
    import vi_dubber.preflight as preflight

    work = tmp_path / "work"
    work.mkdir()
    model = tmp_path / "models" / "llm" / "Qwen--Qwen3-14B-GGUF" / "Qwen3-14B-Q4_K_M.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"model")
    monkeypatch.setattr(preflight, "WORK_DIR", work)
    monkeypatch.setattr(preflight, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(preflight, "configure_runtime", lambda: None)
    config = _config()
    config["reliability"]["retry_budget"] = 99

    checks = run_preflight(config, translation_provider="local")
    retry = {item.name: item for item in checks}["retry_policy"]

    assert retry.status == "error"
    with pytest.raises(RuntimeError, match="retry_policy"):
        raise_for_preflight(checks)


def test_preflight_disk_requirement_scales_with_media_duration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections import namedtuple
    import vi_dubber.preflight as preflight

    DiskUsage = namedtuple("DiskUsage", ["total", "used", "free"])
    gib = 1024**3
    work = tmp_path / "work"
    work.mkdir()
    model = tmp_path / "models" / "llm" / "Qwen--Qwen3-14B-GGUF" / "Qwen3-14B-Q4_K_M.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"model")
    media_1h = tmp_path / "one_hour.mp4"
    media_12h = tmp_path / "twelve_hours.mp4"
    media_bad = tmp_path / "not_media.bin"
    media_1h.write_bytes(b"1h")
    media_12h.write_bytes(b"12h")
    media_bad.write_bytes(b"stub")

    def fake_duration(path: Path) -> float:
        if path == media_1h:
            return 3600.0
        if path == media_12h:
            return 12 * 3600.0
        raise RuntimeError("ffprobe cannot parse stub")

    monkeypatch.setattr(preflight, "WORK_DIR", work)
    monkeypatch.setattr(preflight, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(preflight, "configure_runtime", lambda: None)
    monkeypatch.setattr(preflight, "media_duration", fake_duration)

    cfg = _config()
    cfg["reliability"]["min_free_disk_gb"] = 2.0

    req_1h, hours_1h = preflight.required_free_disk_gib(cfg, input_path=media_1h)
    req_12h, hours_12h = preflight.required_free_disk_gib(cfg, input_path=media_12h)
    req_bad, hours_bad = preflight.required_free_disk_gib(cfg, input_path=media_bad)
    assert req_1h == pytest.approx(3.5)
    assert hours_1h == pytest.approx(1.0)
    assert req_12h == pytest.approx(42.0)
    assert hours_12h == pytest.approx(12.0)
    assert req_bad == pytest.approx(2.0)
    assert hours_bad is None

    # 20 GiB free is enough for 1h (3.5 GiB required) but MUST fail for 12h (42.0 GiB required).
    monkeypatch.setattr(
        preflight.shutil,
        "disk_usage",
        lambda _path: DiskUsage(100 * gib, 80 * gib, 20 * gib),
    )
    checks_1h = run_preflight(cfg, translation_provider="local", input_path=media_1h)
    disk_1h = {c.name: c for c in checks_1h}["disk"]
    assert disk_1h.status == "ok"
    assert "3.5 GiB" in disk_1h.detail

    checks_12h = run_preflight(cfg, translation_provider="local", input_path=media_12h)
    disk_12h = {c.name: c for c in checks_12h}["disk"]
    assert disk_12h.status == "error"
    assert "42.0 GiB" in disk_12h.detail
    assert "12.0h" in disk_12h.detail

    # 50 GiB free passes 12h preflight.
    monkeypatch.setattr(
        preflight.shutil,
        "disk_usage",
        lambda _path: DiskUsage(100 * gib, 50 * gib, 50 * gib),
    )
    checks_12h_ok = run_preflight(cfg, translation_provider="local", input_path=media_12h)
    assert {c.name: c for c in checks_12h_ok}["disk"].status == "ok"

    # Explicit min_free_disk_gb <= 0 disables scaling for isolated unit tests.
    disabled = _config()
    disabled["reliability"]["min_free_disk_gb"] = 0.0
    assert preflight.required_free_disk_gib(disabled, input_path=media_12h) == (0.0, None)

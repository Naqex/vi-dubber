from __future__ import annotations

import json

import pytest

import vi_dubber.jobs as jobs_mod
from vi_dubber.jobs import EVENTS_FILE, append_job_event, load_job_events, update_job_state


def test_job_events_are_monotonic_and_state_updates_are_observable(tmp_path) -> None:
    job = tmp_path / "job-events"

    update_job_state(job, status="running", stage="asr", progress=0.25, metadata={"attempt": 2})
    record = append_job_event(
        job,
        "checkpoint.saved",
        stage="asr",
        progress=0.5,
        attempt=2,
        payload={"output": r"output=C:\private\secret.wav", "api_key": "do-not-store"},
    )

    events = load_job_events(job)
    assert [item["seq"] for item in events] == [1, 2]
    assert events[-1] == record
    assert events[0]["event"] == "state.updated"
    assert events[-1]["payload"] == {
        "api_key": "[redacted]",
        "output": "[redacted-path]",
    }
    assert json.loads((job / "state.json").read_text(encoding="utf-8"))["status"] == "running"


def test_partial_last_event_is_discarded_before_resume_append(tmp_path) -> None:
    job = tmp_path / "job-recovery"
    job.mkdir()
    path = job / EVENTS_FILE
    first = append_job_event(job, "started", stage="extract", progress=0.0)
    with path.open("ab") as handle:
        handle.write(b'{"version": 1, "seq": 999, "event": "partial"')

    resumed = append_job_event(job, "resumed", stage="extract", progress=0.1)
    events = load_job_events(job)
    assert [item["seq"] for item in events] == [first["seq"], resumed["seq"]]
    assert resumed["seq"] == 2
    assert path.read_bytes().endswith(b"\n")


def test_event_loader_skips_corrupt_complete_lines_and_limit_is_recent(tmp_path) -> None:
    job = tmp_path / "job-corrupt"
    job.mkdir()
    path = job / EVENTS_FILE
    first = append_job_event(job, "one")
    with path.open("ab") as handle:
        handle.write(b"not-json\n")
    second = append_job_event(job, "two")

    assert [item["event"] for item in load_job_events(job)] == ["one", "two"]
    assert load_job_events(job, limit=1) == [second]
    assert first["seq"] == 1


def test_append_job_event_1000_entries_uses_o1_tail_seek_not_full_reread(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = tmp_path / "job-1000-events"
    job.mkdir()

    # Prove append_job_event never falls back to O(N) full-file _valid_event_records scans.
    monkeypatch.setattr(
        jobs_mod,
        "_valid_event_records",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("append_job_event must not re-read full journal")),
    )
    # Stub fsync in the 1,000-event loop so test measures O(1) tail seek without OS disk flush jitter.
    monkeypatch.setattr(jobs_mod.os, "fsync", lambda _fd: None)

    for idx in range(1, 1001):
        rec = append_job_event(job, "segment.done", stage="tts", progress=idx / 1000.0, payload={"i": idx})
        assert rec["seq"] == idx

    # Verify multi-chunk tail seek works even when a single event line exceeds 8 KiB.
    big = append_job_event(job, "large.payload", stage="qa", payload={"blob": "x" * 12_000})
    assert big["seq"] == 1001
    after_big = append_job_event(job, "after.large", stage="qa")
    assert after_big["seq"] == 1002

    # Restore full loader and confirm all 1,002 records are intact and strictly monotonic.
    monkeypatch.undo()
    events = load_job_events(job)
    assert len(events) == 1002
    assert events[0]["seq"] == 1
    assert events[-1]["seq"] == 1002
    assert events[-1]["event"] == "after.large"


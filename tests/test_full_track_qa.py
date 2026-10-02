from __future__ import annotations

import json
import os
import sys
import types
import weakref
from pathlib import Path

import numpy as np
import pytest

from vi_dubber import asr, full_track_qa
from vi_dubber.artifacts import atomic_write_json
from vi_dubber.jobs import claim_job
from vi_dubber.longform import MacroChunk
from vi_dubber.types import Segment


def test_windowed_asr_bounds_audio_reuses_model_and_owns_overlap(tmp_path, monkeypatch):
    calls = []
    live_audio = []

    class Model:
        def transcribe(self, audio, batch_size):
            index = int(audio[0])
            assert batch_size == 4
            return {"segments": [
                {"start": 0.5, "end": 1.5, "text": f"owned-{index}"},
                {"start": 2.5, "end": 3.5, "text": "next-window"},
            ]} if index == 1 else {"segments": [{"start": 1.5, "end": 2.5, "text": "owned-2"}]}

    model = Model()

    def load_model(*args, **kwargs):
        assert kwargs["local_files_only"] is True
        assert kwargs["language"] == "vi"
        calls.append("model")
        return model

    def load_audio(path):
        assert all(reference() is None for reference in live_audio)
        audio = np.array([int(Path(path).parent.name[-1])])
        live_audio.append(weakref.ref(audio))
        calls.append(path)
        return audio

    def clip(_source, output, start, duration):
        assert duration <= 4
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"window")
        return output

    monkeypatch.setitem(sys.modules, "whisperx", types.SimpleNamespace(load_model=load_model, load_audio=load_audio))
    monkeypatch.setattr(asr, "configure_runtime", lambda: None)
    monkeypatch.setattr(asr, "_release_cuda", lambda *objects: calls.append(objects))
    monkeypatch.setattr(asr, "clip_audio", clip)
    chunks = [MacroChunk("chunk_0001", 0, 0, 3, 0, 4, "cut"), MacroChunk("chunk_0002", 1, 3, 6, 2, 6, "end")]
    observed = []
    result = asr.transcribe_text_chunks(tmp_path / "12h.wav", chunks, tmp_path / "windows", {},
                                        max_window_seconds=4, on_chunk=lambda chunk, rows: observed.append(chunk.chunk_id))
    assert calls.count("model") == 1
    assert [row.text for row in result["chunk_0001"]] == ["owned-1"]
    assert [row.text for row in result["chunk_0002"]] == ["owned-2"]
    assert result["chunk_0002"][0].start == 3.5
    assert observed == ["chunk_0001", "chunk_0002"]
    assert not list((tmp_path / "windows").rglob("*.wav"))
    assert calls[-1] == (model,)


def test_windowed_asr_invalid_bound_rejected_before_model(tmp_path, monkeypatch):
    monkeypatch.setattr(asr, "configure_runtime", lambda: pytest.fail("model runtime must not start"))
    chunks = [MacroChunk("chunk_0001", 0, 0, 12 * 3600, 0, 12 * 3600, "end")]
    with pytest.raises(ValueError, match="exceeds"):
        asr.transcribe_text_chunks(tmp_path / "12h.wav", chunks, tmp_path, {})


def test_complete_resume_skips_audio_and_model(tmp_path, monkeypatch):
    monkeypatch.setattr(asr, "configure_runtime", lambda: pytest.fail("completed resume must not start a model"))
    chunks = [MacroChunk("chunk_0001", 0, 0, 2, 0, 2, "end")]
    assert asr.transcribe_text_chunks(tmp_path / "voice.wav", chunks, tmp_path, {}, skip_chunk_ids={"chunk_0001"}) == {}


@pytest.mark.parametrize("failure", ["model", "audio", "callback", "timestamps"])
def test_windowed_asr_failure_releases_model_and_own_temporary_audio(tmp_path, monkeypatch, failure):
    model = object()
    released = []

    class FakeModel:
        def transcribe(self, audio, batch_size):
            return {"segments": [{"start": 0, "end": float("nan") if failure == "timestamps" else 1, "text": "hello"}]}
    model = FakeModel()

    def load_model(*args, **kwargs):
        if failure == "model":
            raise RuntimeError("fixture failure")
        return model

    def load_audio(path):
        if failure == "audio":
            raise RuntimeError("fixture failure")
        return "audio"

    def clip(_source, output, *_args):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"window")
        return output

    def callback(*_args):
        if failure == "callback":
            raise RuntimeError("fixture failure")

    monkeypatch.setitem(sys.modules, "whisperx", types.SimpleNamespace(load_model=load_model, load_audio=load_audio))
    monkeypatch.setattr(asr, "configure_runtime", lambda: None)
    monkeypatch.setattr(asr, "_release_cuda", lambda *objects: released.extend(objects))
    monkeypatch.setattr(asr, "clip_audio", clip)
    chunks = [MacroChunk("chunk_0001", 0, 0, 2, 0, 2, "end")]
    with pytest.raises((RuntimeError, ValueError)):
        asr.transcribe_text_chunks(tmp_path / "voice.wav", chunks, tmp_path / "windows", {}, on_chunk=callback)
    assert released == [None if failure == "model" else model]
    assert not list((tmp_path / "windows").rglob("*.wav"))


@pytest.fixture
def retained_job(tmp_path, monkeypatch):
    job = tmp_path / "job-retained"
    job.mkdir()
    (job / "voice_vi.wav").write_bytes(b"unchanged voice")
    atomic_write_json(job / "resolved_config.json", {"asr": {"model": "large-v3", "batch_size": 4}, "qa": {"min_similarity": 0.78}})
    (job / "segments_vi.json").write_text(json.dumps([
        {"id": 0, "start": 0, "end": 2, "vi": "first"},
        {"id": 1, "start": 2, "end": 4, "vi": "second"},
    ]))
    atomic_write_json(job / "qa.json", {"passed": False, "segment_summary": {"final_failed": 122}})
    monkeypatch.setattr(full_track_qa, "audio_duration", lambda _: 4)
    monkeypatch.setattr(full_track_qa, "_cached_model_identity", lambda _: {"revision": "fixture"})
    return job


def fake_inference(calls):
    def run(_source, chunks, _out, _config, *, skip_chunk_ids, max_chunks, on_chunk, **kwargs):
        pending = [chunk for chunk in chunks if chunk.chunk_id not in skip_chunk_ids]
        if max_chunks is not None:
            pending = pending[:max_chunks]
        for chunk in pending:
            calls.append(chunk.chunk_id)
            on_chunk(chunk, [Segment(chunk.index, chunk.source_start + 0.1, chunk.source_end - 0.1, "first" if chunk.index == 0 else "second")])
        return {}
    return run


def test_full_track_partial_has_no_score_and_resume_never_promotes_retained_qa(retained_job, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(full_track_qa, "transcribe_text_chunks", fake_inference(calls))
    output = tmp_path / "diagnostic"
    partial = full_track_qa.run_full_track_check(retained_job, output, window_seconds=2, context_seconds=0)
    assert partial["status"] == "partial_diagnostic"
    assert partial["similarity"] is None
    assert partial["diagnostic_threshold_met"] is None
    completed = full_track_qa.run_full_track_check(retained_job, output, window_seconds=2, context_seconds=0)
    assert calls == ["chunk_0001", "chunk_0002"]
    assert completed["status"] == "complete_diagnostic"
    assert completed["similarity"] == 1
    assert completed["covered_source_seconds"] == 4
    assert completed["retained_qa_passed"] is False
    assert completed["retained_failed_segments"] == 122
    assert completed["canonical_acceptance_promoted"] is False
    assert json.loads((retained_job / "qa.json").read_text())["passed"] is False
    assert not (output / "run.lock").exists()


def test_resume_source_change_and_tamper_rejected_before_inference(retained_job, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(full_track_qa, "transcribe_text_chunks", fake_inference(calls))
    output = tmp_path / "diagnostic"
    full_track_qa.run_full_track_check(retained_job, output, window_seconds=2, context_seconds=0)
    checkpoint = json.loads((output / "checkpoint.json").read_text())
    checkpoint["completed"]["chunk_0001"]["segments"][0]["text"] = "tampered"
    atomic_write_json(output / "checkpoint.json", checkpoint)
    with pytest.raises(ValueError, match="artifact identity"):
        full_track_qa.run_full_track_check(retained_job, output, window_seconds=2, context_seconds=0)
    (retained_job / "voice_vi.wav").write_bytes(b"modified")
    with pytest.raises(ValueError, match="identity changed"):
        full_track_qa.run_full_track_check(retained_job, output, window_seconds=2, context_seconds=0)
    assert calls == ["chunk_0001"]


@pytest.mark.parametrize("changed_identity", ["code", "model"])
def test_resume_code_and_model_change_rejected_before_inference(retained_job, tmp_path, monkeypatch, changed_identity):
    calls = []
    monkeypatch.setattr(full_track_qa, "transcribe_text_chunks", fake_inference(calls))
    output = tmp_path / "diagnostic"
    full_track_qa.run_full_track_check(retained_job, output, window_seconds=2, context_seconds=0)
    if changed_identity == "code":
        monkeypatch.setattr(full_track_qa, "_runtime_identity", lambda: {"source_files": {"asr.py": "changed implementation"}})
    else:
        monkeypatch.setattr(full_track_qa, "_cached_model_identity", lambda _: {"revision": "fixture", "files": {"model.bin": {"sha256": "changed bytes"}}})
    with pytest.raises(ValueError, match="identity changed"):
        full_track_qa.run_full_track_check(retained_job, output, window_seconds=2, context_seconds=0)
    assert calls == ["chunk_0001"]


def test_cached_model_detects_changed_bytes_with_same_size_and_mtime(tmp_path, monkeypatch):
    revision = "a" * 40
    models = tmp_path / "models"
    cache = models / "whisperx/models--Systran--faster-whisper-large-v3"
    (cache / "refs").mkdir(parents=True)
    (cache / "refs/main").write_text(revision)
    snapshot = cache / "snapshots" / revision
    snapshot.mkdir(parents=True)
    for name in ["model.bin", "config.json", "tokenizer.json", "preprocessor_config.json", "vocabulary.json"]:
        (snapshot / name).write_bytes(b"old model")
    vad = tmp_path / ".venv/Lib/site-packages/whisperx/assets/pytorch_model.bin"
    vad.parent.mkdir(parents=True)
    vad.write_bytes(b"cached vad")
    monkeypatch.setattr(full_track_qa, "MODELS_DIR", models)
    monkeypatch.setattr(full_track_qa, "PROJECT_ROOT", tmp_path)
    old = full_track_qa._cached_model_identity("large-v3")
    stat = (snapshot / "model.bin").stat()
    (snapshot / "model.bin").write_bytes(b"new model")
    os.utime(snapshot / "model.bin", ns=(stat.st_atime_ns, stat.st_mtime_ns))
    new = full_track_qa._cached_model_identity("large-v3")
    assert old["files"]["model.bin"]["size_bytes"] == new["files"]["model.bin"]["size_bytes"]
    assert old["files"]["model.bin"]["sha256"] != new["files"]["model.bin"]["sha256"]


def test_offline_cli_fences_every_connection_entrypoint_and_dns(tmp_path, monkeypatch, capsys):
    import importlib.util
    import socket
    script = Path(__file__).resolve().parents[1] / "scripts/check_full_track_qa.py"
    spec = importlib.util.spec_from_file_location("check_full_track_qa", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(sys, "argv", [str(script), "--job-dir", str(tmp_path), "--plan-only"])
    monkeypatch.setattr(full_track_qa, "prepare_full_track_check", lambda *_args, **_kwargs: {"expected": "fixture"})
    for key in ["HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"]:
        monkeypatch.setenv(key, "0")
    for name in ["connect", "connect_ex"]:
        monkeypatch.setattr(socket.socket, name, getattr(socket.socket, name))
    for name in ["create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"]:
        monkeypatch.setattr(socket, name, getattr(socket, name))
    cli.main()
    with socket.socket() as sock:
        for method in [sock.connect, sock.connect_ex]:
            with pytest.raises(OSError, match="denies all"):
                method(("127.0.0.1", 17841))
    for method, arguments in [
        (socket.create_connection, (("127.0.0.1", 17841),)),
        (socket.getaddrinfo, ("example.com", 443)),
        (socket.gethostbyname, ("example.com",)),
        (socket.gethostbyname_ex, ("example.com",)),
        (socket.gethostbyaddr, ("127.0.0.1",)),
    ]:
        with pytest.raises(OSError, match="denies all"):
            method(*arguments)
    assert json.loads(capsys.readouterr().out) == {}


def test_full_track_rejects_retained_output_and_duplicate_worker(retained_job, tmp_path, monkeypatch):
    monkeypatch.setattr(full_track_qa, "transcribe_text_chunks", lambda *_args, **_kwargs: pytest.fail("must not infer"))
    with pytest.raises(ValueError, match="separate"):
        full_track_qa.run_full_track_check(retained_job, retained_job / "qa-diagnostic")
    output = tmp_path / "diagnostic"
    with claim_job(output):
        with pytest.raises(RuntimeError, match="duplicate run"):
            full_track_qa.run_full_track_check(retained_job, output)


def test_input_change_during_inference_retains_resume_but_prevents_publication(retained_job, tmp_path, monkeypatch):
    def infer(*args, **kwargs):
        fake_inference([])(*args, **kwargs)
        (retained_job / "voice_vi.wav").write_bytes(b"source changed during inference")
    monkeypatch.setattr(full_track_qa, "transcribe_text_chunks", infer)
    output = tmp_path / "diagnostic"
    with pytest.raises(ValueError, match="changed during"):
        full_track_qa.run_full_track_check(retained_job, output, window_seconds=2, context_seconds=0)
    checkpoint = json.loads((output / "checkpoint.json").read_text())
    assert checkpoint["status"] == "failed_resume_available"
    assert not (output / "diagnostic.json").exists()

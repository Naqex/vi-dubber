"""Standalone, resumable local ASR diagnostic; never publishes product QA."""
from __future__ import annotations

import json
import os
import re
from importlib.metadata import version
from pathlib import Path
from typing import Any

from .artifacts import atomic_write_json, fingerprint_data, fingerprint_file
from .asr import transcribe_text_chunks
from .jobs import claim_job
from .longform import MacroChunk, MacroChunkPolicy, plan_macro_chunks
from .media import audio_duration
from .qa import transcript_similarity
from .runtime import MODELS_DIR, PROJECT_ROOT
from .types import Segment


def _cached_model_identity(model: str) -> dict[str, Any]:
    if model != "large-v3":
        raise ValueError("This offline diagnostic requires the retained large-v3 model")
    cache = MODELS_DIR / "whisperx/models--Systran--faster-whisper-large-v3"
    revision = (cache / "refs/main").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Cached model revision must be a pinned SHA")
    snapshot = cache / "snapshots" / revision
    files = ["model.bin", "config.json", "tokenizer.json", "preprocessor_config.json", "vocabulary.json"]
    weights = {}
    for name in files:
        artifact = fingerprint_file(snapshot / name)
        if artifact["size_bytes"] <= 0:
            raise ValueError(f"Cached model artifact is empty: {name}")
        weights[name] = artifact
    # WhisperX ships the incumbent pyannote VAD; no align model is requested.
    vad = PROJECT_ROOT / ".venv/Lib/site-packages/whisperx/assets/pytorch_model.bin"
    return {"model": model, "revision": revision, "files": weights, "vad": fingerprint_file(vad)}


def _runtime_identity() -> dict[str, Any]:
    closure = [
        "asr.py", "full_track_qa.py", "qa.py", "longform.py", "media.py",
        "runtime.py", "artifacts.py", "jobs.py", "pronunciation.py", "types.py",
    ]
    files = {f"src/vi_dubber/{name}": fingerprint_file(Path(__file__).parent / name) for name in closure}
    files["scripts/check_full_track_qa.py"] = fingerprint_file(PROJECT_ROOT / "scripts/check_full_track_qa.py")
    return {"source_files": files, "packages": {
        name: version(name) for name in (
            "whisperx", "faster-whisper", "ctranslate2", "torch", "torchaudio",
            "pyannote.audio", "soundfile", "rapidfuzz",
        )
    }}


def prepare_full_track_check(
    job_dir: Path, *, window_seconds: float = 300.0, context_seconds: float = 2.0,
) -> dict[str, Any]:
    job_dir = job_dir.resolve()
    if (job_dir / "run.lock").exists():
        raise RuntimeError("Retained job has a run.lock; reconcile its owner before this diagnostic")
    config = json.loads((job_dir / "resolved_config.json").read_text(encoding="utf-8"))
    segments = json.loads((job_dir / "segments_vi.json").read_text(encoding="utf-8"))
    retained_qa = json.loads((job_dir / "qa.json").read_text(encoding="utf-8"))
    source = job_dir / "voice_vi.wav"
    duration = audio_duration(source)
    policy = MacroChunkPolicy(
        target_seconds=window_seconds, min_seconds=window_seconds, max_seconds=window_seconds,
        boundary_search_seconds=0, context_seconds=context_seconds,
        single_chunk_threshold_seconds=window_seconds,
    )
    if window_seconds > 300 or context_seconds > 2:
        raise ValueError("Offline QA windows must be <=300s with <=2s context")
    if duration / window_seconds > 9999:
        raise ValueError("QA window count exceeds the existing MacroChunk ID contract")
    chunks = plan_macro_chunks(duration, policy=policy)
    expected = " ".join(str(segment["vi"]) for segment in segments)
    identity = {
        "policy": 2, "job_dir": str(job_dir), "source": fingerprint_file(source),
        "duration_seconds": duration, "expected_sha256": fingerprint_data(expected),
        "asr": config["asr"], "language": "vi", "model_cache": _cached_model_identity(config["asr"]["model"]),
        "runtime": _runtime_identity(),
        "threshold": float(config["qa"].get("min_similarity", 0.78)),
        "retained_qa": fingerprint_file(job_dir / "qa.json"),
        "retained_config": fingerprint_file(job_dir / "resolved_config.json"),
        "retained_segments": fingerprint_file(job_dir / "segments_vi.json"),
        "chunks": [chunk.to_dict() for chunk in chunks],
    }
    return {"identity": identity, "fingerprint": fingerprint_data(identity), "expected": expected,
            "retained_qa_passed": retained_qa["passed"],
            "retained_failed_segments": retained_qa.get("segment_summary", {}).get("final_failed"),
            "source_path": str(source), "window_bound_seconds": window_seconds + 2 * context_seconds}


def _read_resume(output_dir: Path, prepared: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checkpoint = output_dir / "checkpoint.json"
    if not checkpoint.exists():
        if output_dir.exists() and any(path.name != "run.lock" for path in output_dir.iterdir()):
            raise ValueError("Diagnostic output directory is nonempty without an owned checkpoint")
        return {}
    cached = json.loads(checkpoint.read_text(encoding="utf-8"))
    if cached["fingerprint"] != prepared["fingerprint"]:
        raise ValueError("QA resume source/config/model/plan identity changed")
    planned = {chunk["chunk_id"]: chunk for chunk in prepared["identity"]["chunks"]}
    complete = cached["completed"]
    if not isinstance(complete, dict) or complete.keys() - planned.keys():
        raise ValueError("QA resume contains unknown chunks")
    for chunk_id, record in complete.items():
        if record["chunk"] != planned[chunk_id] or record["sha256"] != fingerprint_data(record["segments"]):
            raise ValueError("QA resume chunk artifact identity mismatch")
        previous_start = -1.0
        chunk = planned[chunk_id]
        for segment in record["segments"]:
            start, end = float(segment["start"]), float(segment["end"])
            if not start >= previous_start or not end > start or not chunk["source_start"] <= (start + end) / 2 < chunk["source_end"]:
                raise ValueError("QA resume transcript has invalid timestamps/ownership")
            previous_start = start
    return complete


def run_full_track_check(
    job_dir: Path, output_dir: Path, *, window_seconds: float = 300.0,
    context_seconds: float = 2.0, max_chunks: int | None = 1,
) -> dict[str, Any]:
    job_dir, output_dir = job_dir.resolve(), output_dir.resolve()
    if output_dir == job_dir or output_dir.is_relative_to(job_dir) or job_dir.is_relative_to(output_dir):
        raise ValueError("Diagnostic output must be separate from the retained job")
    prepared = prepare_full_track_check(job_dir, window_seconds=window_seconds, context_seconds=context_seconds)
    complete = _read_resume(output_dir, prepared)
    chunks = [MacroChunk.from_dict(row) for row in prepared["identity"]["chunks"]]
    output_dir.mkdir(parents=True, exist_ok=True)

    def save(status: str) -> None:
        atomic_write_json(output_dir / "checkpoint.json", {
            "format": "vi-full-track-qa-diagnostic-v1", "fingerprint": prepared["fingerprint"],
            "identity": prepared["identity"], "status": status, "pid": os.getpid(), "completed": complete,
        })

    def observed(chunk: MacroChunk, segments: list[Segment]) -> None:
        rows = [segment.to_dict() for segment in segments]
        complete[chunk.chunk_id] = {"chunk": chunk.to_dict(), "segments": rows, "sha256": fingerprint_data(rows)}
        save("running")
        print(f"QA diagnostic checkpoint {chunk.chunk_id}: {len(complete)}/{len(chunks)}", flush=True)

    # Existing lease implementation only owns this separate diagnostic folder.
    # It never reconciles or removes the retained job's lease.
    with claim_job(output_dir):
        # Re-read under the lease: another invocation may have completed a
        # window between our preflight and acquiring this folder's ownership.
        complete = _read_resume(output_dir, prepared)
        try:
            save("running")
            transcribe_text_chunks(
                Path(prepared["source_path"]), chunks, output_dir / "windows", prepared["identity"]["asr"],
                language="vi", max_window_seconds=prepared["window_bound_seconds"],
                skip_chunk_ids=set(complete), max_chunks=max_chunks, on_chunk=observed,
            )
            # A producer changing the source/inputs during the run invalidates
            # publication, even if every window callback previously succeeded.
            after = prepare_full_track_check(job_dir, window_seconds=window_seconds, context_seconds=context_seconds)
            if after["fingerprint"] != prepared["fingerprint"]:
                raise ValueError("Retained QA inputs changed during local inference")
            coverage_complete = len(complete) == len(chunks)
            actual = " ".join(
                segment["text"] for chunk in chunks if chunk.chunk_id in complete
                for segment in complete[chunk.chunk_id]["segments"]
            )
            similarity = transcript_similarity(prepared["expected"], actual) if coverage_complete else None
            report = {
                "format": "vi-full-track-qa-diagnostic-v1", "fingerprint": prepared["fingerprint"],
                "status": "complete_diagnostic" if coverage_complete else "partial_diagnostic",
                "completed_windows": len(complete), "total_windows": len(chunks),
                "covered_source_seconds": sum(record["chunk"]["source_end"] - record["chunk"]["source_start"] for record in complete.values()),
                "window_bound_seconds": prepared["window_bound_seconds"], "actual": actual,
                "similarity": similarity, "threshold": prepared["identity"]["threshold"],
                "diagnostic_threshold_met": None if similarity is None else similarity >= prepared["identity"]["threshold"],
                "retained_qa_passed": prepared["retained_qa_passed"],
                "retained_failed_segments": prepared["retained_failed_segments"],
                "canonical_acceptance_promoted": False, "human_listening_performed": False,
            }
            atomic_write_json(output_dir / "diagnostic.json", report)
            save(report["status"])
            return report
        except BaseException:
            save("failed_resume_available")
            raise

"""Read-only completion/identity review; writes only its separate audit receipt."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket

for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
    os.environ[key] = "1"


def deny_network(*args, **kwargs):
    raise RuntimeError("Completion audit is offline")


for key in ("connect", "connect_ex"):
    setattr(socket.socket, key, deny_network)
for key in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
    setattr(socket, key, deny_network)

from vi_dubber.full_track_qa import prepare_full_track_check, _read_resume

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
JOB = ROOT / "work/job-8dc51f8a892aba21"
OUTPUT = ROOT / "work/artifacts/full-track-qa-job12-20261002"
EXPECTED = "0377b44a4f48bf1388fa90ff98302bd9eb830248cdd1ec5a1f8da60de8740b5d"
report = json.loads((OUTPUT / "diagnostic.json").read_text(encoding="utf-8"))
assert report["status"] == "complete_diagnostic"
prepared = prepare_full_track_check(JOB, window_seconds=300, context_seconds=2)
assert prepared["fingerprint"] == report["fingerprint"] == EXPECTED
complete = _read_resume(OUTPUT, prepared)
chunks = prepared["identity"]["chunks"]
assert len(complete) == len(chunks) == report["completed_windows"] == report["total_windows"] == 143
duration = prepared["identity"]["duration_seconds"]
assert abs(report["covered_source_seconds"] - duration) < 1e-6
assert chunks[0]["source_start"] == 0 and chunks[-1]["source_end"] == duration
assert all(left["source_end"] == right["source_start"] for left, right in zip(chunks, chunks[1:]))
actual = " ".join(s["text"] for c in chunks for s in complete[c["chunk_id"]]["segments"])
assert actual == report["actual"]
segment_count = 0
empty_windows = []
context_overlap_boundaries = []
token_overlap_candidates = []
for index, chunk in enumerate(chunks):
    segments = complete[chunk["chunk_id"]]["segments"]
    segment_count += len(segments)
    if not segments:
        empty_windows.append(chunk["chunk_id"])
    for segment in segments:
        assert chunk["context_start"] - 1e-6 <= segment["start"] < segment["end"] <= chunk["context_end"] + 1e-6
    if index and segments:
        previous = complete[chunks[index - 1]["chunk_id"]]["segments"]
        if not previous:
            continue
        overlap = previous[-1]["end"] - segments[0]["start"]
        if overlap > 0:
            context_overlap_boundaries.append({"left": chunks[index - 1]["chunk_id"], "right": chunk["chunk_id"], "seconds": overlap})
        left_words = re.findall(r"\w+", previous[-1]["text"].casefold())
        right_words = re.findall(r"\w+", segments[0]["text"].casefold())
        longest = 0
        for size in range(5, min(len(left_words), len(right_words)) + 1):
            if left_words[-size:] == right_words[:size]:
                longest = size
        if longest:
            token_overlap_candidates.append({"left": chunks[index - 1]["chunk_id"], "right": chunk["chunk_id"], "token_count": longest, "text": " ".join(right_words[:longest])})

retained = json.loads((ROOT / "work/checkpoints/Job12-offline-qa-diagnosis-20261002/diagnosis.json").read_text(encoding="utf-8"))
retained_hashes = {}
for relative, expected in retained["retained_artifact_sha256"].items():
    observed = hashlib.sha256((JOB / relative).read_bytes()).hexdigest()
    assert observed == expected, relative
    retained_hashes[relative] = observed
assert report["retained_qa_passed"] is False and report["retained_failed_segments"] == 122
assert report["canonical_acceptance_promoted"] is False and report["human_listening_performed"] is False

audit = {
    "captured_at": datetime.now(timezone.utc).isoformat(), "status": "complete_diagnostic_verified",
    "fingerprint": EXPECTED, "fresh_identity_recheck": True,
    "completed_windows": 143, "source_seconds": duration, "window_bound_seconds": prepared["window_bound_seconds"],
    "segments": segment_count, "empty_windows": empty_windows,
    "chunk_hashes_timestamps_midpoint_ownership_validated": True,
    "context_bounds_validated": True, "contiguous_source_plan": True,
    "context_overlap_boundary_count": len(context_overlap_boundaries),
    "maximum_context_overlap_seconds": max((item["seconds"] for item in context_overlap_boundaries), default=0),
    "context_overlap_boundary_samples": context_overlap_boundaries[:5],
    "suffix_prefix_overlap_candidates_at_least_5_tokens": token_overlap_candidates,
    "boundary_limit": "Midpoint ownership is validated; endpoint/context overlap is allowed. Token overlaps are advisory leads, not human quality verdicts.",
    "similarity": report["similarity"], "threshold": report["threshold"],
    "diagnostic_threshold_met": report["diagnostic_threshold_met"],
    "retained_artifact_sha256": retained_hashes, "retained_json_hashes_unchanged": True,
    "voice_sha256": prepared["identity"]["source"]["sha256"],
    "retained_qa_passed": False, "retained_failed_segments": 122,
    "canonical_acceptance_promoted": False, "human_listening_performed": False,
    "read_only_audit_network_denied": True,
}
(EVIDENCE / "COMPLETION-AUDIT.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({key: value for key, value in audit.items() if key not in {"retained_artifact_sha256", "suffix_prefix_overlap_candidates_at_least_5_tokens", "context_overlap_boundary_samples"}}, indent=2))

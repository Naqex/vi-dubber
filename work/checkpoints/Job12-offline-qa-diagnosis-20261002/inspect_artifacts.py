"""Read retained Job12 artifacts/headers; write only this new audit packet."""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import soundfile as sf

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
JOB = ROOT / "work/job-8dc51f8a892aba21"
INPUTS = ["state.json", "qa.json", "segment_qa.json", "segments_vi.json",
          "tts_stats.json", "resolved_config.json", "terminology_qa.json",
          "result.json", "mix_metrics.json", "chunks/plan.json"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(path: Path) -> dict:
    binary = next((ROOT / "tools/ffmpeg").rglob("ffprobe.exe"))
    completed = subprocess.run([
        str(binary), "-v", "error", "-show_entries",
        "format=duration,size:stream=index,codec_type,codec_name,sample_rate,channels,duration,width,height",
        "-of", "json", str(path),
    ], capture_output=True, check=True, timeout=20)
    return json.loads(completed.stdout)


def main() -> None:
    before = {name: digest(JOB / name) for name in INPUTS}
    if (OUT / "diagnosis.json").exists():
        retained = json.loads((OUT / "diagnosis.json").read_text(encoding="utf-8"))
        assert before == retained["retained_artifact_sha256"], "Retained artifacts no longer match this frozen audit"
        print(json.dumps({"mode": "verify_existing", "artifact_hashes_unchanged": True}))
        return
    data = {name: json.loads((JOB / name).read_text(encoding="utf-8")) for name in INPUTS}
    qa = data["segment_qa.json"]
    final = qa["final"]
    initial = {row["segment_id"]: row for row in qa["initial"]}
    segments = {row["id"]: row for row in data["segments_vi.json"]}
    stats = {row["segment_id"]: row for row in data["tts_stats.json"]}
    failed = [row for row in final if not row["passed"]]
    assert len(failed) == len({row["segment_id"] for row in failed}) == qa["summary"]["final_failed"] == 122
    assert len(final) == len(segments) == len(stats) == qa["summary"]["segments_checked"] == 4277
    assert set(segments) == {row["segment_id"] for row in final}
    reasons = Counter(reason for row in failed for reason in row["reasons"])

    def entry(row: dict) -> dict:
        segment_id = row["segment_id"]
        segment = segments[segment_id]
        audio = JOB / "tts" / f"{segment_id:05d}.wav"
        info = sf.info(audio)
        return {
            "segment_id": segment_id, "source_start": segment["start"], "source_end": segment["end"],
            "audio_path": str(audio), "expected": row["expected"], "re_asr": row["actual"],
            "acoustic_checked": row["acoustic_checked"], "reasons": row["reasons"],
            "missing_critical": row["missing_critical"], "similarity": row["similarity"],
            "timing_ratio": row["timing_ratio"], "audio_duration": info.duration,
            "qa_duration": row["actual_duration"], "stats_duration": stats[segment_id]["final_duration"],
            "sample_rate": info.samplerate, "channels": info.channels,
            "duration_matches_qa": abs(info.duration - row["actual_duration"]) <= 0.02,
            "human_verdict": None,
        }

    rows = [entry(row) for row in failed]
    chosen = []
    for reason in ["missing_critical", "severe_transcript_mismatch", "transcript_mismatch", "timing_overflow"]:
        candidates = [row for row in failed if reason in row["reasons"]]
        pick = min(candidates, key=lambda row: row["similarity"]) if reason != "timing_overflow" else max(candidates, key=lambda row: row["timing_ratio"])
        if pick["segment_id"] not in {row["segment_id"] for row in chosen}:
            chosen.append(pick)
    # Include an early number flag and both actually repaired IDs, then two
    # acoustic-pass controls. Their outcomes still require a human listener.
    for segment_id in [3, *[row["segment_id"] for row in qa["repairs"]]]:
        row = next(item for item in final if item["segment_id"] == segment_id)
        if segment_id not in {item["segment_id"] for item in chosen}:
            chosen.append(row)
    controls = [row for row in final if row["passed"] and row["acoustic_checked"]]
    chosen += [controls[0], controls[len(controls) // 2]]
    first_listening = [entry(row) for row in chosen]

    result = data["result.json"]
    video = probe(Path(result["output"]))
    voice = probe(JOB / "voice_vi.wav")
    source = probe(JOB / "original.flac")
    last_end = max(row["end"] for row in segments.values())
    subtitle = Path(result["subtitle"])
    subtitle_text = subtitle.read_text(encoding="utf-8-sig")
    subtitle_cues = subtitle_text.count(" --> ")
    subtitle_times = []
    for line in subtitle_text.splitlines():
        if " --> " not in line:
            continue
        timestamp = line.split(" --> ")[1].strip().split()[0]
        hours, minutes, seconds = timestamp.replace(",", ".").split(":")
        subtitle_times.append(int(hours) * 3600 + int(minutes) * 60 + float(seconds))
    duration = float(video["format"]["duration"])
    ordered = list(segments.values())
    timeline = {
        "segments": len(segments), "subtitle_cues": subtitle_cues, "last_segment_end": last_end,
        "last_subtitle_end": max(subtitle_times), "video_duration": duration,
        "segments_start_ordered": all(a["start"] <= b["start"] for a, b in zip(ordered, ordered[1:])),
        "nonpositive_windows": [row["id"] for row in ordered if row["end"] <= row["start"]],
        "segments_after_final": [row["id"] for row in ordered if row["end"] > duration + 0.1],
        "header_duration_mismatches": [row["segment_id"] for row in rows if not row["duration_matches_qa"]],
    }
    repaired = []
    final_by_id = {row["segment_id"]: row for row in final}
    for repair in qa["repairs"]:
        segment_id = repair["segment_id"]
        repaired.append({"segment_id": segment_id, "status": repair["status"],
                         "initial_passed": initial[segment_id]["passed"],
                         "final_passed": final_by_id[segment_id]["passed"],
                         "final_reasons": final_by_id[segment_id]["reasons"]})
    chunks = data["chunks/plan.json"]["chunks"]
    by_chunk = Counter()
    for row in failed:
        start = segments[row["segment_id"]]["start"]
        match = next((chunk["chunk_id"] for chunk in chunks if chunk["source_start"] <= start < chunk["source_end"]), "unmapped")
        by_chunk[match] += 1

    after = {name: digest(JOB / name) for name in INPUTS}
    assert before == after, "Retained artifacts changed during read-only audit"
    report = {
        "format": "vi-job12-readonly-qa-diagnosis-v1", "source_head": "3fc873f",
        "job_id": JOB.name, "retained_artifact_sha256": before, "artifact_hashes_unchanged": True,
        "status": data["state.json"]["status"], "qa_passed": data["qa.json"]["passed"],
        "full_track_skipped": data["qa.json"]["full_track_skipped"], "global_passed": data["qa.json"]["global_passed"],
        "summary_recomputed": {"final_failed": len(failed), "reason_counts_overlap": dict(reasons),
                               "action_counts": dict(Counter(row["action"] for row in failed)),
                               "acoustic_checked": sum(bool(row["acoustic_checked"]) for row in final)},
        "short_target_buckets": {
            str(limit): {"all": sum(row["target_duration"] < limit for row in final),
                         "failed": sum(row["target_duration"] < limit for row in failed),
                         "overflow": sum(row["target_duration"] < limit and "timing_overflow" in row["reasons"] for row in failed)}
            for limit in [0.5, 1.0, 1.2]
        },
        "cached_full_track_qa": {"qa_raw_exists": (JOB / "qa_raw.json").exists(),
                                 "acoustic_qa_manifest_exists": (JOB / "manifests/acoustic_qa.json").exists()},
        "repaired": repaired, "failed_by_chunk": dict(by_chunk),
        "terminology": {key: value for key, value in data["terminology_qa.json"].items() if key != "items"},
        "profile_policy": data["resolved_config.json"]["profile_policy"],
        "media": {"final": video, "voice": voice, "canonical_source_audio": source},
        "timeline": timeline, "listening_priority_ids": [row["segment_id"] for row in first_listening],
        "human_listening_performed": False,
    }
    (OUT / "diagnosis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # The complete local packet contains exact script/re-ASR text for review.
    # It is not a new QA receipt and never modifies the retained job.
    packet = {"format": "vi-job12-listening-packet-v1", "job_id": JOB.name,
              "source_artifact_sha256": before, "final_video": result["output"],
              "first_listening": first_listening, "all_failed": rows,
              "human_listening_performed": False}
    (OUT / "listening-packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Job12 — gói nghe thử từ file đã có", "",
             "Chưa có kết quả nghe của owner. Đây là diagnosis và phiếu review; không công nhận QA pass.", "",
             "Nghe file TTS dưới đây, đối chiếu lời cần đọc và transcript re-ASR. Phân loại: âm thanh đúng / mất-đổi từ thật / ASR nghe sai / không chắc. Với timing_overflow, kiểm tra thêm đúng mốc trong video Final để nhận ra tràn sang câu sau. Ghi segment ID, verdict và điều nghe thấy; chưa tự render lại.", "",
             f"Video Final: [{Path(result['output']).name}]({Path(result['output']).as_posix()})", "",
             "## Lượt đầu — bao phủ nhóm lỗi và hai controls đã được acoustic QA", ""]
    for row in first_listening:
        lines += [f"### Segment #{row['segment_id']} — {row['source_start']:.3f} → {row['source_end']:.3f}s", "",
                  f"[Nghe audio {row['audio_duration']:.2f}s]({Path(row['audio_path']).as_posix()})", "",
                  f"Cần đọc: {row['expected']}", "", f"Re-ASR: {row['re_asr']}", "",
                  f"Flag: {', '.join(row['reasons']) or 'acoustic pass control'}; thiếu: {', '.join(row['missing_critical']) or 'không'}; ratio {row['timing_ratio']:.3f}.", "",
                  "Verdict của owner: chưa có.", ""]
    lines += ["Toàn bộ 122 đoạn, đường dẫn audio, lời cần đọc và oracle nằm trong `listening-packet.json`. Packet này giữ `human_verdict=null`; các controls không thay full-track QA.", ""]
    (OUT / "LISTENING.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"summary": report["summary_recomputed"], "repaired": repaired,
                      "timeline": timeline, "first_listening_ids": report["listening_priority_ids"],
                      "artifact_hashes_unchanged": True}, ensure_ascii=True))


if __name__ == "__main__":
    main()

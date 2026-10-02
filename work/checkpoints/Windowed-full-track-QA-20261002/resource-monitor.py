"""Read-only observer for the separately owned Job12 ASR diagnostic."""

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
LAUNCH = json.loads((EVIDENCE / "full-launch.json").read_text(encoding="utf-8-sig"))
OUTPUT = ROOT / LAUNCH["output"]
INTERVAL = 2.0
MAX_SECONDS = 12 * 3600

spec = importlib.util.spec_from_file_location("p23_readonly_metrics", ROOT / "scripts/verify_p23_real_media.py")
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def now():
    return datetime.now(timezone.utc).isoformat()


def publish(path, data):
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


sampler, gpu_method, gpu_error = metrics._open_gpu_process_memory_sampler()
started = time.monotonic()
previous = started
summary = {
    "started_at": now(), "launcher_pid": LAUNCH["pid"],
    "fingerprint": LAUNCH["fingerprint"], "interval_seconds": INTERVAL,
    "scope": "Observed process-tree RSS and Windows PDH dedicated GPU memory; sampled peaks are lower bounds, not whole-pipeline acceptance.",
    "gpu_method": gpu_method, "gpu_error": gpu_error,
    "samples": 0, "valid_gpu_samples": 0, "peak_rss_bytes": 0,
    "peak_gpu_bytes": None, "maximum_sample_gap_seconds": 0.0,
}
stop_reason = "maximum_observation_duration"
try:
    with (EVIDENCE / "resource-samples.jsonl").open("x", encoding="utf-8") as stream:
        while time.monotonic() - started < MAX_SECONDS:
            current = time.monotonic()
            parents = metrics._windows_process_parent_map()
            pids = metrics._process_tree_pids(int(LAUNCH["pid"])) & parents.keys()
            checkpoint = None
            try:
                checkpoint = json.loads((OUTPUT / "checkpoint.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            if checkpoint and checkpoint.get("fingerprint") == LAUNCH["fingerprint"]:
                worker = int(checkpoint["pid"])
                pids |= metrics._process_tree_pids(worker) & parents.keys()
            rss = sum(metrics._windows_rss_for_pid(pid) for pid in pids)
            gpu = None
            if sampler is not None:
                try:
                    dedicated = sampler.sample()
                    gpu = sum(dedicated.get(pid, 0) for pid in pids)
                    summary["valid_gpu_samples"] += 1
                except OSError as exc:
                    summary["gpu_error"] = str(exc)
            sample = {
                "timestamp": now(), "elapsed_seconds": round(current - started, 3),
                "pids": sorted(pids), "rss_bytes": rss, "gpu_bytes": gpu,
                "completed_windows": len(checkpoint.get("completed", {})) if checkpoint else None,
                "checkpoint_status": checkpoint.get("status") if checkpoint else None,
            }
            stream.write(json.dumps(sample, separators=(",", ":")) + "\n")
            stream.flush()
            summary["samples"] += 1
            summary["peak_rss_bytes"] = max(summary["peak_rss_bytes"], rss)
            if gpu is not None:
                summary["peak_gpu_bytes"] = max(summary["peak_gpu_bytes"] or 0, gpu)
            summary["maximum_sample_gap_seconds"] = max(summary["maximum_sample_gap_seconds"], current - previous)
            summary["last_sample"] = sample
            publish(EVIDENCE / "resource-observation.json", summary)
            previous = current
            if not pids:
                stop_reason = "observed_worker_tree_exited"
                break
            time.sleep(INTERVAL)
except BaseException as exc:
    stop_reason = "observer_error"
    summary["observer_error"] = repr(exc)
    raise
finally:
    if sampler is not None:
        sampler.close()
    summary["ended_at"] = now()
    summary["stop_reason"] = stop_reason
    publish(EVIDENCE / "resource-observation-final.json", summary)

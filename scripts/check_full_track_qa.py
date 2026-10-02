"""Explicit offline QA diagnostic. Default execution is one bounded window."""
from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--window-seconds", type=float, default=300)
    parser.add_argument("--context-seconds", type=float, default=2)
    parser.add_argument("--max-chunks", type=int, default=1)
    parser.add_argument("--all-windows", action="store_true")
    args = parser.parse_args()
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
        os.environ[key] = "1"
    # local_files_only covers the ASR weights; this guard also fences ancillary
    # library probes so a missing cache cannot silently initiate a download.
    def deny_network(*_args, **_kwargs):
        raise OSError("Offline QA diagnostic denies all socket connections and DNS")
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    socket.gethostbyname = deny_network
    socket.gethostbyname_ex = deny_network
    socket.gethostbyaddr = deny_network

    from vi_dubber.full_track_qa import prepare_full_track_check, run_full_track_check
    options = {"window_seconds": args.window_seconds, "context_seconds": args.context_seconds}
    if args.plan_only:
        prepared = prepare_full_track_check(args.job_dir, **options)
        prepared.pop("expected")
        print(json.dumps(prepared, ensure_ascii=True, indent=2))
        return
    if args.output is None:
        parser.error("--output is required for an inference run")
    report = run_full_track_check(args.job_dir, args.output,
                                 max_chunks=None if args.all_windows else args.max_chunks, **options)
    print(json.dumps({key: value for key, value in report.items() if key != "actual"}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

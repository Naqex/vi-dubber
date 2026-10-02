# Windowed full-track QA preparation — 2026-10-02

Current execution pointer: the separate full-track diagnostic was launched at **20:31:35 +07:00 on 02/10/2026**, launcher `10892` → worker `3260`. See [FULL-TRACK-LAUNCH.md](FULL-TRACK-LAUNCH.md) and its exact PID/log/output receipt; read the live checkpoint/process before resume. This preparation receipt below remains historical and does not declare the active run completed.

Preparation status before launch: **SOURCE_READY / SHORT_CACHED_ASR_OBSERVED / FULL_TRACK_NOT_RUN**.
Baseline HEAD: `e2940c1`, clean before slice. Root reviewed the design/source and required the model/code identity and socket fence hardening below before a full-run decision. This packet does not close M0-VI-ready, P23, human listening or Job12 QA.

## Behavior and data flow

`transcribe_text_chunks()` reuses existing MacroChunk coverage validation, audio clipping, timestamp midpoint ownership and conservative CUDA OOM batch fallback. It loads one local cached WhisperX model, reads one <=304s context window at a time, releases that audio before the next window and removes only its own temporary WAV. Alignment/translation/TTS are not invoked. Timestamp validity/order and declared bounds are checked before publication.

The standalone `full_track_qa.py` caller reads retained voice/script/config/QA and writes atomic per-window checkpoints in a separate diagnostic folder. Resume must match source bytes, expected script, configuration, exact chunk plan, all cached model-file bytes/VAD, 11 project implementation hashes and runtime versions. Completed transcript rows also carry a hash and timestamp/ownership validation. The existing single-process lease owns only that diagnostic folder; retained Job12's lock/state/manifests/QA never receive writes. A source change during inference blocks publication.

Partial coverage has `similarity=null` and `diagnostic_threshold_met=null`. Complete coverage may report the existing transcript-similarity formula and retained threshold, but always has `canonical_acceptance_promoted=false`; the original failed=122 and actual human verdict remain separate. This opt-in windowed path is not wired into the product pipeline/profile and has not been promoted over incumbent whole-file inference. Context boundary transcription remains a candidate needing comparison evidence.

## Verification and root review repair

| Check | Result / limit |
|---|---|
| Entire offline suite on initial implementation | **682 passed, 1 skipped**, 2 existing warnings, 70.77s; `full-offline-suite.txt`. External DNS/connect and provider ports blocked by the test wrapper. |
| Final focused suite after identity/socket hardening | **71 passed**, 1.20s; `focused-tests.txt`. Covers ASR/QA prior tests plus memory-window ownership, cleanup/failure, partial score fencing, source/tamper/code/model drift, duplicate worker, complete resume skipping model and every CLI socket/DNS entrypoint. |
| Same-size/mtime model tamper | Byte SHA changes and resume identity rejects it; size/mtime alone is no longer an oracle. |
| Final full-track plan-only preflight | Exit 0; `full-plan-v2.json`, 143 windows, max context304s, fingerprint `0377b44a4f48bf1388fa90ff98302bd9eb830248cdd1ec5a1f8da60de8740b5d`. No model inference. |
| Diff/manual boundary review | `git diff --check` pass; source/cache/output/network boundaries reviewed, no global/service changes, new secrets, dependency install or reverse-toolkit script. |

Only identity/network safeguards changed after the full-suite/canary run; final focused tests and plan-only preflight verify those changes. The previous observed canary remains v1 evidence and its original receipts are preserved. Root explicitly requested avoiding a duplicate inference solely for these safeguards.

Source review used the workspace §10A `code-audit` checklist read-only: file/checkpoint trust, command/path injection, model/cache identity, network reachability and publication. No toolkit/bootstrap/scanner/network/API attack script was run. API security scanning does not apply to this standalone local CLI. No unresolved critical finding was identified in this bounded manual review; no scanner or whole-product security acceptance is claimed.

## Observed cached-ASR canary — v1, not full-track

Exact launch is in `short-launch.json`: hidden detached launcher PID19392, Python worker15312; start `2026-10-02T20:11:32.3248+07:00`. Diagnostic atomic file timestamp `20:12:22`, approximately **49.7s to publication**, including source hashing/model startup. Both owned PIDs later exited. The late `short-process-snapshot.json` contains no processes, so it is **not peak RSS/VRAM evidence**.

Command:

```powershell
& ./.venv/Scripts/python.exe scripts/check_full_track_qa.py --job-dir work/job-8dc51f8a892aba21 --output work/artifacts/full-track-qa-short-20261002 --window-seconds 60 --context-seconds 0 --max-chunks 1
```

Observed: first source0–60s window completed out of714; 3 ASR segments cover0.031–59.971s. Partial diagnostic keeps similarity/threshold verdict null, retained `qa_passed=false/failed_segments=122`, no canonical promotion/human claim. Its own WAV/run.lock are absent after completion. `short-diagnostic.json`, stdout/stderr and preflight are retained; the model/VAD/source/config fingerprints matched after inference. Lightning checkpoint migration and existing pyannote TF32 warnings were in-memory runtime warnings; no permanent checkpoint-upgrade command was run.

The full714-row v1 raw plan is preserved locally at `work/artifacts/full-track-qa-short-20261002/plan-only-v1.json` (SHA-256 `48f147533aff05d7026957c57cad4974e800fcba487d9bdba6f7a8cd414dc1b5`); its compact source/config/first-window projection is checked in as `short-preflight.json`. The authoritative143-window v2 plan is checked in whole at `full-plan-v2.json`.

v1 canary allowed loopback except known provider ports and pinned model size/mtime; that evidence does **not** establish the stronger v2 guard. Final v2 CLI sets `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `HF_HUB_DISABLE_TELEMETRY` then denies **all** `socket.socket.connect`, `connect_ex`, `socket.create_connection`, `getaddrinfo`, `gethostbyname`, `gethostbyname_ex`, `gethostbyaddr`, including loopback/provider17841. Focused tests exercise each route. This is an in-process Python guard, not an OS firewall claim; FFmpeg uses only explicit local file inputs.

## Final cached model/resource preflight

Retained model: `large-v3`, snapshot `edaa852ec7e145841d8ffdb056a99866b5f0a478`; model.bin SHA-256 `69f74147e3334731bc3a76048724833325d2ec74642fb52620eda87352e3d4f1`, 3,087,284,237 bytes. Bundled incumbent pyannote VAD is present/hash-pinned; no align model or fallback model is requested. Runtime versions: WhisperX3.8.6, faster-whisper1.2.1, CTranslate2 4.8.2, torch/torchaudio2.8.0+cu128, pyannote.audio4.0.7, soundfile0.13.1, rapidfuzz3.14.6.

Source voice SHA-256 `95eea540a776bdac9bd6b48c50047abd606dc0934933ac3718e8eb9e3e83ce69`, 4,111,829,900 bytes, 42,831.561s. Resource snapshot before canary: RTX2070SUPER 8GiB with6,722MiB free; D:77.2GB free; no active matching VI/Job12 process/run.lock. Refresh ownership/resources before any full launch. Maximum decoded304s mono16k float32 input is about18.6MiB; temporary48k mono16bit WAV about27.8MiB. These are deterministic window-size estimates, not a measured peak-process-memory acceptance.

## Resume / next action

At the end of the preparation slice, root owned the decision to launch the separate143-window full diagnostic after this commit/review. [FULL-TRACK-RUN.md](FULL-TRACK-RUN.md) gives exact commands/effects/process ownership and resume. It must run hidden detached with PID/log/checkpoints; never start a second worker against that same output. Full run was **not launched during the preparation slice**; the subsequent execution is routed by the current pointer above.

The v1 short directory cannot be silently reused under v2 identity. Preserve it; use the new full directory named in the run packet. Subsequent same-source/config/code/model resumes automatically skip validated complete windows; identity drift rejects resume without deleting data. Canonical Job12 QA, 122 flags and human-listening packet remain unchanged.

Rollback: revert this source/PLAN/checkpoint commit; separate diagnostic output may be retained for investigation. No product-profile or retained Job12 rollback is required.

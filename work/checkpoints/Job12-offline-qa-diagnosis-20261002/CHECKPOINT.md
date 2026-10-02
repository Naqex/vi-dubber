# Job12 read-only QA diagnosis — 2026-10-02

Status: **ARTIFACT_DIAGNOSIS_COMPLETE / MEDIA_QA_NOT_ACCEPTED**.
Source baseline: `3fc873f`. This receipt owns diagnosis and a listening packet; persisted Job12 state/QA/manifests remain their original producers' authority.

## Findings

Direct retained-artifact recomputation confirms **122 distinct failed segments out of 4,277**. Reason counts overlap: missing critical token 71, severe transcript mismatch 17, transcript mismatch 8, timing overflow 43. Action precedence routes 91 to pronunciation retry and 31 to timing rewrite; these are proposed actions from the retained report, not new render authority.

The retained `balanced_fast` policy has `retry_budget=2`. Only #3997 and #4050 were repaired: #3997 remains flagged for missing critical words; #4050 passed after repair. This explains 123 → 122 rather than an interrupted whole-job. It does not justify raising the budget or skipping the remaining flags.

Short timing windows are a concrete diagnostic lead: 28 of the 43 overflows have target windows below 1s; 11 below 0.5s. The packet includes #2298: rendered audio 0.587s against a 0.250s window, ratio 2.349. Tiny windows can raise re-ASR uncertainty and leave insufficient speaking time, but hearing/context is needed to distinguish genuine truncation from ASR false positives. No segmentation promotion, threshold reduction or text/audio repair was made.

Failed IDs map to exactly 26 macro chunks; the two unflagged chunks are #17/#20, agreeing with retained preview readiness. Terminology text QA remains `passed=true`, 0 failed/4,277, 1,205 terms checked; text terminology pass does not clear acoustic flags.

## Read-only media/alignment evidence

Metadata comes from bundled FFprobe with `-show_entries format=duration,size:stream=... -of json`, 20s timeout per file. Audio checks use `soundfile.info`, which reads headers rather than running ASR or decoding the full track.

| Artifact / check | Result |
|---|---|
| Final MP4 | 42,831.550s, 1080p AV1; AAC 48kHz stereo. Video vs audio duration difference 2ms. |
| Existing voice track | 42,831.561s, PCM 48kHz mono. |
| Canonical source audio | FLAC 48kHz stereo, 42,831.5535s. Historical large WAV was not selected. |
| Segment/subtitle timeline | 4,277 segments and 4,277 SRT cues; starts ordered, no nonpositive windows, none extend past Final. Last segment 42,827.744583s; last SRT cue 42,827.745s. |
| Failed audio availability | All 122 TTS WAVs exist; all headers match the retained QA duration within 20ms. |
| Retained JSON identity | SHA-256 unchanged before/after for 10 input artifacts; recorded in `diagnosis.json`. Collector verification again passed. |

These checks establish structural coverage/alignment, not intelligibility, frame continuity, full-track semantic/acoustic quality, or owner approval.

## Concrete listening packet

[LISTENING.md](LISTENING.md) gives 9 existing clips totaling **43.1 seconds**, exact time ranges, expected script, re-ASR text and pending verdicts. IDs: #313, #47, #1542, #2298, #3, #3997, #4050, #0, #2037. They cover every failure category, both repaired segments and two acoustic-pass controls. `listening-packet.json` contains all 122 rows/audio references with `human_verdict=null` and source hashes. No clip extraction, upload or listening claim was performed.

Owner's oracle: compare the existing audio with expected words; mark audio correct / actual lost or changed words / ASR misheard / unsure. For timing overflow, also inspect the exact timestamp in the Final MP4 for overlap or truncation. A first 9-clip ballot only guides triage; it cannot waive all 122 or full-track acceptance.

## Gate sources and next executable work

- **Read-only diagnosis and packet preparation:** permitted by the current offline task and PLAN current-queue/retained-artifact scope. No provider, credits, login or new permission was needed; completed here.
- **Full-track QA:** the retained profile explicitly sets `final_full_qa=false`, so `qa.json` has `full_track_skipped=true/global_passed=null`. `qa_raw.json` and `manifests/acoustic_qa.json` are absent. Source `pipeline.py:2808`–`2899` distinguishes new full-track re-ASR inference from the existing risk report. There is no cached full-track result to read. New local ASR is a separate compute/media job requiring a bounded detached plan, fresh source/config/resource ownership and separate output; a provider is not inherently required for that read-only inference. It was outside this artifact/header-only slice, not technically impossible or blanket-blocked by OAuth.
- **Specific compute gap before a near-12h full-track run:** `asr.py:446`–`484` currently calls `whisperx.load_audio()` for each whole QA file. Installed WhisperX `audio.py:13,25,65` decodes mono 16kHz float32, so this 42,831.561s input alone is approximately 2.55 GiB, before subprocess buffers/copies and model working memory (estimate, not a measured peak). The existing main-ASR chunk path uses windows at `asr.py:328`–`433`; a bounded full-track QA wrapper can reuse that approach. Do not turn this diagnosis into an unbounded whole-file model invocation.
- **Repair/rerender:** PLAN §Job12 requires exact retained-job/config/single-worker preflight and correctly scoped media/provider authority. Pipeline repair (`pipeline.py:2293`–`2372`) builds a translator and runs TTS/re-ASR; do not infer that JSON diagnosis authorizes those calls or mutate original QA/state by hand.
- **Human listening:** the actual human verdict is required by PLAN/P23 and workspace §11–12. Prepared artifacts do not provide that verdict. Parent coordinator can present this concrete packet, then store the real response; no listening score was fabricated.
- **M0-VI-ready / M5:** still lacks required repeated 33m whole-job and full 6h+/provider/QA evidence. Fixture repair and structural Job12 diagnosis do not promote the whole milestone.

Execution: existing `.venv/Scripts/python.exe inspect_artifacts.py`, exit 0, ~1.9s for first collection. Later invocation is read-only verification of the frozen JSON hashes and exits without rewriting this packet. No network, models, GPU inference, render, lock deletion, `--fresh`, provider switch or retained-file write. `git diff --check` passes.

Rollback: revert this evidence/PLAN-pointer commit only. No retained Job12 artifact requires rollback.

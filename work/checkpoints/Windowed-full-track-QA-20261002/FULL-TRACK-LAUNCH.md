# Job12 full-track ASR diagnostic — launched 02/10/2026

Current result: **completed143/143 and independently verified**; producer/observer exited. See [COMPLETION.md](COMPLETION.md). The launch/initial observations below are historical; no new inference resume is required. Canonical acceptance/human listening remain open.

Local cached-model diagnostic is running independently of the retained pipeline. Fresh preflight matched fingerprint `0377b44a4f48bf1388fa90ff98302bd9eb830248cdd1ec5a1f8da60de8740b5d`: 143 source windows cover 42,831.561s, each 300s with 2s context and maximum 304s input. Frozen implementation commit is `fc81a26a0b9426e8e79e0a72efa94612a0f55bc1`.

Launch at 20:31:35 +07:00: launcher PID **10892**, Python worker **3260**. Exact command/output/log locators are in [full-launch.json](full-launch.json). Preflight found no matching producer, retained-job lock or target diagnostic directory; free RAM 19,056,864KiB, GPU 6,922MiB and disk 77,170,794,496 bytes.

## Initial checkpoint and resource evidence

[FIRST-CHECKPOINT.json](FIRST-CHECKPOINT.json) is a stable receipt captured at 20:33:59 +07:00: **8/143 windows**, covering **2,400s**, `status=running`, fingerprint unchanged. The first 0–300s source window produced 12 segments within its 0–302s context. Timestamp midpoint ownership is the boundary rule; segment endpoints may extend into the context.

Observer launcher **21444** → Python **20492** reads only the owned diagnostic process tree. It reuses Windows PDH dedicated GPU and process RSS readers from `scripts/verify_p23_real_media.py`; it does not run that script's media-generation/mux harness. The observer writes separate sample/summary files; its exact command is in [resource-monitor-launch.json](resource-monitor-launch.json), implementation in [resource-monitor.py](resource-monitor.py).

Initial observer receipt: 44 samples at nominal 2s intervals, maximum observed gap 2.047s, no GPU sampling error. Sampled peak process-tree RSS **1,546,485,760 bytes** (~1,475MiB), dedicated GPU **6,470,918,144 bytes** (~6,171MiB). Sampling began approximately 56s after diagnostic launch and misses earlier model-loading/allocation peaks. These are sampled lower bounds in local diagnostic scope, not whole-pipeline memory acceptance. Live `resource-observation.json` and `resource-samples.jsonl` are intentionally not staged while being written; `resource-observation-final.json` is published when observation ends.

## Acceptance and resume

Partial coverage has no score. Retained `qa.passed=false`, 122 failed segments and all canonical files remain unchanged. The run performs no provider/download/translation/TTS/alignment/rerender; source/model/config/code identities remain frozen. Human listening has not occurred. Completing this diagnostic will not close P23 or promote product acceptance.

Read-only monitoring can continue while other lanes work. When the producer exits, inspect `work/artifacts/full-track-qa-job12-20261002/diagnostic.json` and `checkpoint.json`, reconcile all 143 windows and final identity, then review boundaries/resource evidence separately. Preserve any failure/checkpoints. Resume the exact owned output only after proving the old worker is gone, following [FULL-TRACK-RUN.md](FULL-TRACK-RUN.md); do not create a second producer or use `--fresh`.

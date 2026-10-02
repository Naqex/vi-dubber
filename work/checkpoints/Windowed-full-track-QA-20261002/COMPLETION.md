# Job12 full-track local diagnostic — completed 02/10/2026

**Complete diagnostic verified; Job12/product QA remains unaccepted.** The independent offline cached-ASR run completed **143/143 windows**, covering **42,831.561s**, with **1,723 segments** and no empty windows. Similarity is **0.9818206211** against the retained diagnostic threshold0.78. This score does not clear122 segment flags, human listening, P23 or product acceptance.

Publication at **21:06:10 +07:00** took **2,074.26s** (~34.57min) from the detached launch, including startup/hashing/final publication. Other offline UI/build/browser work ran concurrently; this is observed diagnostic wall time, not a paired performance benchmark.

## Identity, exit and retained state

`verify-completion.py` exited0 after a fresh byte-level source/model/config/code/runtime identity recheck matched the original fingerprint `0377b44a4f48bf1388fa90ff98302bd9eb830248cdd1ec5a1f8da60de8740b5d`. It reused `_read_resume` read-only to validate all143 transcript hashes, chunk identities, timestamp order and midpoint ownership; context bounds and contiguous complete coverage also passed. `COMPLETION-AUDIT.json` is the stable receipt.

All **10 retained JSON hashes** from the earlier Job12 diagnosis, including state/QA/segments/config/result, remain unchanged. Source voice SHA remains `95eea540a776bdac9bd6b48c50047abd606dc0934933ac3718e8eb9e3e83ce69`. The CLI does not write retained files or publish canonical QA. Retained `qa.passed=false`, failed122; `canonical_acceptance_promoted=false`, `human_listening_performed=false`.

Producer launcher10892/worker3260 and observer21444/20492 are gone. `EXIT-RECEIPT.json` confirms no retained/diagnostic run.lock and no owned temporary WAV. Logs contain no OOM/Traceback/fallback failure; only the previously observed in-memory Lightning checkpoint/TF32 warnings. No permanent upgrade/model/config command was run.

## Boundary review limitation

Midpoint ownership does not remove duplicated text inside overlapping context. **115/142 adjacent boundaries** have endpoint overlap, maximum **3.952s**, within the4s shared context. **71 boundaries** have an identical normalized suffix/prefix of at least5 tokens: **986 candidate tokens**, maximum22 in one boundary. The first 300s boundary repeats15 words. Candidate pairs are retained in the audit for review; no automatic text deletion or retranscription was performed.

The windowed transcript is therefore an **advisory diagnostic candidate**. The raw similarity includes the context behavior; whole-track coverage and a high score do not establish production stitching correctness, semantic/audio quality, or human approval. Any future stitching change needs a separate bounded oracle/identity rather than modifying this completed evidence.

## Measured resources

`resource-observation-final.json` and the stable `resource-samples.jsonl` retain **989 valid samples**, nominal2s interval, maximum observed gap **2.391s**. Sampled peak process-tree RSS **1,552,506,880 bytes** (~1,480.59MiB), Windows PDH dedicated GPU **6,571,581,440 bytes** (~6,267.15MiB); no PDH errors. Observer stopped when the owned process tree exited.

Sampling began approximately56s after launch and excludes earlier model-loading/allocation peaks. Sampled peaks are lower bounds, include the producer process tree, and cover only local ASR diagnostic work. They do not prove whole-pipeline6h memory acceptance or performance improvements over incumbent inference.

## Resume and remaining gates

No producer or inference resume is needed: the diagnostic is complete. Read-only review uses `work/artifacts/full-track-qa-job12-20261002/diagnostic.json`/`checkpoint.json` and these receipts. Preserve the output, model/config/code identity and prior canary; do not delete/rewrite evidence or create another worker. A changed candidate requires a new explicit scope/output, never silent reuse under a different identity.

The existing [9-clip owner listening packet](../Job12-offline-qa-diagnosis-20261002/LISTENING.md) remains pending. The repeated33m whole-job and whole-pipeline6h+/provider/QA P23 gates also remain open. Completed diagnostic work is not full PLAN completion.

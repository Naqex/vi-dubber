# VI reload harness repair — 2026-10-02

Status: **HARNESS_REPAIRED_OFFLINE / PRODUCT_ACCEPTANCE_OPEN**.

Source baseline: `674eec2` on `main`, clean worktree before this slice. Owned diff: `tests/test_web_e2e_playwright.py` and the existing queue in `PLAN.md`; no product, provider, pipeline or frontend source changed.

## What changed and why

The former module fixture called `build_app()` against the retained project `work/` archive and live provider status/catalog. Source inspection shows page load selects a persisted job, reconciles its state, builds review rows and may extract review audio. That is inappropriate for a deterministic layout/reload test and couples it to user media/session state. The extra launch thread checked only a listening socket and swallowed teardown errors.

The fixture now uses a temporary workspace and a two-model catalog, suppresses Gradio analytics, checks the application's `/config` after its own launch, and closes that exact server in `finally`. Browser requests outside loopback are aborted. Production catalog validation remains unchanged. Switching Sol/high → Instant/low and default values after reload are asserted in the real Gradio DOM; this is fixture binding evidence, not live catalog/provider acceptance.

The exact mechanism of the historical third-test navigation timeout is **unconfirmed**. The unchanged three-test module passed when run under a temporary offline/isolation plugin before the permanent repair; no current production Gradio defect was reproduced or patched. The historical failure stays in the [30/09 audit](../../../../../planning/checkpoints/workspace-next-stage/VI-safe-continuation-20260930/CHECKPOINT.md).

## Verification

All commands use the existing project `.venv/Scripts/python.exe`; no installs, personal browser profiles, provider turn, login or external requests.

| Check | Result | Evidence |
|---|---|---|
| Untouched module under temporary offline isolation | 3 passed, 12.21s; plugin import-order warning | `baseline-isolated.txt` |
| Repaired module | 3 passed, 13.95s | `module-repair.txt` |
| Reload alone | 1 passed, 10.91s | `reload-isolated.txt` |
| Layout + reload | 2 passed, 11.57s | `layout-reload.txt` |
| Catalog + reload | 2 passed, 12.49s | `catalog-reload.txt` |
| Entire offline suite, including existing M3/metadata/catalog contracts | 672 passed, 1 skipped, 2 existing warnings, 69.88s | `full-offline-suite.txt` |
| Final module after adding a loaded-catalog wait before screenshot | 3 passed, 13.37s | `module-final.txt` |

Full-suite wrapper guarded DNS/socket connections: only loopback allowed; provider ports 17850/17842/54005 denied. `GRADIO_ANALYTICS_ENABLED=False`. The full-suite run preceded the final two screenshot-readiness assertions; the final module verifies those assertions. No product source changed between runs. `git diff --check` passes.

Final test source SHA-256: `24c93c608f458101a42227b0a5cd90e9d2f17d975df5dd14dfdf88672a745ffd`.
Loaded fixture screenshot: `layout-loaded.png`, SHA-256 `d33c50d071ca5e25c62afe5ae83737ddb230a446f4be0c4bae79fce6285868c0`. This is a desktop legacy Gradio fixture screenshot, not responsive/current React product acceptance.

## State and next work

Job12 was read directly: `status=completed`, `stage=complete`, `progress=1.0`, `qa.passed=false`, `full_track_skipped=true`, `global_passed=null`, `final_failed=122`; no `run.lock` or VI/Job12-matching python/ffmpeg/node process observed at preflight. No retained job was resumed, rendered or manually marked accepted.

Next independently executable work: inspect existing Job12 QA/media artifacts and prepare a listening packet; complete current React UI i18n/keyboard/contrast/narrow/preview evidence. Repeated whole-job, whole-pipeline 6h/live-provider stress, full-track QA and human listening still lack their required evidence. M0-VI-ready/M5 acceptance does not follow from this harness repair.

Rollback: revert this slice's commit. Retained job/media/cache/receipts, provider config and product sources have no edits in the commit.

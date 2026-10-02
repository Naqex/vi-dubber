# Persisted preview readiness — 02/10/2026

**Focused readiness fix verified; whole-product UI acceptance remains open.** Existing validated preview bytes/manifests could remain available after newer persisted metadata marked their chunk blocked/stale or explicitly removed it from the ready list. The rail labeled `QA BLOCK` but still enabled the button, and remembered selection could restore that preview. API listing/play/download also ignored the newer metadata.

## Reproduction and behavior

The browser fail-before receipt records a selected ready `chunk_0001`, then a disposable persisted state update with `preview_ready_chunks=[]` and `preview_blocked_chunks` containing that chunk while its valid manifest remains. The refreshed button rendered `#0001 QA BLOCK` **enabled**, failing the disabled assertion. The separate API fail-before receipt returned the old preview in the listing under that same blocked state.

The existing backend `_list_chunk_previews` now checks persisted readiness before the existing manifest/hash/path checks; job detail, preview listing, playback and download share that reader. Stale/blocked excludes an artifact; an explicit ready list permits only its members. An absent list retains compatibility with legacy jobs only through the existing verified manifest. No new ledger or pipeline state is introduced.

Frontend `isPreviewReady` centralizes the same rule for rail buttons, restore/default selection, selected download and `VideoPlayer`. The player also derives availability during the render carrying newer metadata, so a lagging old previews response cannot override it. The browser regression deliberately serves that lagging response while job readiness comes from the real disposable backend. Unknown/no media now uses the existing unavailable text instead of the invented `1080p DUB READY` badge; a valid preview retains its own PREVIEW label.

## Validation

- API module: **28 passed, 1 skipped**, 15.32s; two existing Starlette/httpx deprecations. Tests cover legacy manifest availability, blocked/stale/queued denial for listing and direct play/download, restored explicit ready and tamper denial.
- React browser module: **5 passed**, 31.68s. Three readiness cases prove refresh/reload against a lagging preview response and remembered selection; existing ready → edit → stale and catalog selection/reload flows remain valid. Real local synthetic media and FastAPI use temporary WORK_DIR; no retained Job12 writes.
- TypeScript/Vite build passed. Existing UI contract 4 checks and telemetry contract 5 cases passed. Versioned `frontend/dist` is rebuilt because FastAPI serves this repository's checked-in product bundle.
- Screenshots inspected at 1440 ready and 390 stale; responsive metrics have no page-width overflow at 768/390/360, and existing dialog focus/keyboard/theme tests passed. These do not establish full i18n, contrast, touch or narrow-layout acceptance: the top ticker visibly overlaps its timing text at 390 and remains the next bounded finding.
- `git diff --check` passed. The 11-file ASR diagnostic implementation closure is unchanged; producer PID3260 continues against its frozen identity.

## Bounded manual API/source review

Read-only `api-security` and `code-audit` checklist references were applied to this diff: persisted business-state authority, UI/backend differential behavior, artifact data exposure, shared consumer gates and retained path/hash validation. The added state reader is read-only, uses the existing job resolver and does not reconcile/write canonical state. GET/download still run the same manifest verification and job-relative path resolution before FileResponse. No OAuth/account/authentication change, toolkit/bootstrap/scanner or external API attack run occurred. This is a scoped manual review, not whole-product security acceptance.

Evidence: `validation.json`, fail-before and final pytest outputs, retained M3 `receipt.json` and three screenshots in this folder. Rollback reverts the source/bundle/tests/receipt commit; retained media, QA and the independent ASR diagnostic are unaffected.

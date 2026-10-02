# Preview errors, QA verdict and bounded accessibility — 02/10/2026

**SCOPED_FIX_VALIDATED; whole UI and product acceptance remain open.**

The player now stops an unavailable selected preview after listing403/500 instead
of keeping stale playback or silently switching to Final. A typed block is scoped
to the current job; remembered chunk intent survives an error or unavailable200
response. Retry can restore only a currently verified ready chunk. Selecting Final
explicitly clears preview intent, and changing jobs clears the old job's block.
An unrelated preview-list error does not interrupt an already selected Final.
Play buttons and the global Space shortcut respect the block.

Processing completion still exposes an existing Final artifact for review/download.
Its neutral Final badge is separate from QA passed/failed/unverified, failed segment
count and full-track coverage. A98% selected-risk similarity is displayed as a
measurement and cannot stand in for a QA-pass verdict. Persisted Job12 QA and the
pipeline policy are unchanged.

The timeline's segment controls are siblings of its slider so assistive technology
can reach them. Speed/speaker selects have names; review and disabled-chunk scroll
regions can be focused. Contrast repairs reuse the existing light/dark palettes.
The narrow monitor scrolls to its existing rail/audio controls, trading additional
scrolling for reachability. WaveformPlayer only changes the selected-B button color;
its full-file fetch/decode/lifecycle and near12h memory gate are unchanged.

## Executed evidence

- `browser-final-r6.txt`: **22 passed**,100.58s. Includes running/completed403/500,
  retry, explicit Final, an already selected Final, job switch, blocked/stale/queued
  refresh/reload with a lagging response, disabled play/Space, slider/segment Enter,
  QA true/false/null, Header/ticker, edit/catalog and prior M3 regressions.
- `after-r6/report.json`: **30 state captures /18 axe-core4.10.3 scans**, six
  width/language/theme combinations at390/768/1440. Ready/stale/blocked,403/500,
  Final QA-failed and empty states have no automated violations or horizontal page
  overflow/scroll. Only the three main states per combination receive axe scans.
- `after-r6/receipt.json`: before/after raw source identity
  `98e0975eb498da77eeddfaefa8930931279eeba67cfae4890f800c4e18bd17f5`;
  failures0 and temporary server stopped. Identity covers frontend source/dist,
  the regression module and executed audit script. The report SHA256 is
  `154ff6a0dec624cc610216fbcbd11d2e2f328f3a8d6587fdaf28320014bfd857`.
- `build-final-r5.txt`: TypeScript/Vite build passed,1618modules. The same built
  assets are served by FastAPI in the final audit/tests; r6 changed test/audit
  interaction oracles without changing product source.
- `ui-contract-final.txt` and `telemetry-contract-final.txt`:4and5existing contract
  checks passed. Root directly viewed final390VI/light QA-failed and1440EN/dark
  preview screenshots. [Root review](REVIEW.md) records independent findings,
  their regression closure and the final review limitation after interruption.

Incomplete checks remain:18aria-prohibited-attr,18aria-valid-attr-value,
18color-contrast and12video-caption case observations. These are manual follow-up
requirements, not PASS claims. Screenshots at390 initially show only the top of
the scrollable monitor; alert/retry reachability is not an initial-viewport claim.
Full i18n/touch/manual WCAG, captions and near12h audio memory remain open.

## Failed attempts retained

`before/` captures old preview playback surviving403/500 and contrast/select-name/
nested-interactive/scroll failures. `after/` is interrupted partial evidence.
`after-r2/` retains residual contrast/scroll issues; r2/r3 browser17pass did not
cover the independently found completed-preview fallback. `after-r3/` records
30captures/18scans/3contrast failures on unchanged source.

`completed-preview-fail-before.txt` reproduces completed403/500 falling through to
Final:2failed/2passed. `browser-final-r5.txt` has20pass/2fail at a wrong job-menu
role selector; the menu entries use `menuitem`. `audit-final-r5.txt` stops after
18captures because clearing localStorage raced an old pending response. R6 selects
Final through its actual control before reload, and uses keyboard opening plus
the correct menu role. No assertion was relaxed to accept automatic fallback.

All jobs/media/DB state belong to temporary synthetic fixtures. Browser requests
are restricted to that exact loopback origin; system telemetry is intercepted.
No provider, translation/TTS/ASR, retained Job12 mutation, OAuth or upload occurs.
Evidence files retain raw bytes through the scoped `.gitattributes`.
Rollback reverts the coherent source/tests/dist/receipt commit and keeps old
receipts; it does not change retained media or parent-plan acceptance.

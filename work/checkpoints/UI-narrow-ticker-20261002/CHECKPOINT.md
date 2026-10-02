# Narrow processing ticker — 02/10/2026

**Ticker layout fix verified at 390/768/1440, VI and EN.** The old progress section shrank to 200px while its stage label stayed on one line and painted beyond that width. At 390 the timing and control sections continued to x606px; the stage text visibly overlapped timing. `ui-narrow-ticker-fail-before-20261002.txt` records that overflowing section.

`SystemBar` now gives the stage/progress section the full row below the desktop breakpoint, permits the stage label to wrap and keeps an 80px progress control. Timing and job controls wrap in normal flow when necessary. Desktop retains its horizontal strip. Height follows its content so text and controls remain distinct; the trade-off is a taller ribbon at narrow widths. Data/ETA calculations, persisted job state and control handlers are unchanged.

Validation: focused **3 passed**, 13.46s; current full React browser module **8 passed**, 46.66s. Each width checks all three section bounds for overflow/intersection in both languages and opens/closes stage details with Enter/Escape. Existing ready/edit/stale/catalog/readiness flows also pass. TypeScript/Vite build passed, existing UI contract 4 checks and telemetry contract 5 cases passed. Versioned dist was rebuilt for the existing FastAPI static serving path. `git diff --check` passed; frozen ASR implementation closure is untouched.

Screenshots reviewed: `390-vi.png`, `390-en.png`, `768-vi.png`, `1440-en.png`. This is focused ticker evidence; it does not close global responsive, i18n, contrast or touch acceptance.

The first post-fix test also discovered a separate **Header overflow**: clicking the off-screen language control at390 caused browser horizontal scrolling and shifted the whole page (`scrollX=233`). The ticker geometry oracle uses the existing persisted `vi_dubber_lang` preference and reload for EN, so it does not claim narrow-header language switching is usable. Header control reachability/overflow remains the next bounded UI finding. Its failed test output is preserved separately.

All browser work uses temporary fixture jobs/local synthetic media and exact loopback request allowance. No retained Job12, provider, production deployment or inference configuration change occurred. Rollback reverts this UI/bundle/test/receipt commit.

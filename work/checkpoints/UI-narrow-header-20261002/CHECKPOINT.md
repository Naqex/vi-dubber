# Narrow header controls — 02/10/2026

**Header controls are reachable without horizontal page scrolling at390/768/1440.** Previously branding/job selector and all right-side controls stayed in a fixed46px row. At390 controls extended well beyond the viewport; clicking the off-screen language button caused browser scrollX233 and shifted the entire app. The fail-before receipt captures control bounds exceeding viewport390.

The existing Header now permits rows to wrap. Below desktop width, branding/job selection occupy one row and controls flow in the next. The version badge and Final-download text are hidden on the narrowest width; labeled icons remain available. The compact job menu aligns to the selector's right edge to stay inside the viewport. Handlers, job identity, language/theme state and modal focus behavior are unchanged. The trade-off is additional header height at smaller widths.

Validation: focused **3 passed**,8.96s; current full React browser module **11 passed**,55.65s. Every width verifies all visible controls inside the viewport with scrollX0 for completed/paused jobs, actual VI→EN language click, Tab/Enter theme control, keyboard catalog/import modal open/Escape/focus restore, job dropdown bounds/selection, and unchanged readiness/ticker/edit/catalog regressions. TypeScript/Vite build passed; existing UI4 and telemetry5 checks passed. Screenshots at390/768/1440 EN/light are retained;390 was visually inspected. Versioned dist is rebuilt for the existing static serving path. `git diff --check` passed, frozen ASR closure unchanged.

These are focused navigation/header proofs, not global touch/contrast/i18n or product acceptance. Other panels and controls still need their PLAN-level checks. Test media/jobs live only in temporary fixture WORK_DIR; backend telemetry requests are fixture responses and browser network is restricted to the exact loopback test origin. No provider, broker, retained Job12, ASR/model/config or canonical acceptance changes occur.

Evidence: fail-before/focused/full-browser outputs and three screenshots in this folder. Rollback reverts the Header/bundle/tests/receipt commit.

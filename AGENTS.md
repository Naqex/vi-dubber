# Naqex VI Dubber

Standalone-first repository instructions. A standalone checkout uses this file, `README.md`, and `PLAN.md` without requiring the parent workspace; when checked out inside Naqex Workspace, `../../AGENTS.md` also applies.

## Quick Commands

| Task | Command (run from repo root) |
|---|---|
| Setup environment | `.\setup.ps1` or `uv sync --locked --dev` |
| Machine & runtime check | `uv run vi-dubber doctor` |
| Run offline tests | `uv run pytest -q` (CI core: `uv run pytest tests/test_core.py tests/test_artifacts.py -q`) |
| Start web dashboard | `.\start-web.ps1` (`http://127.0.0.1:7860`) |

## Authoritative Docs & Ownership

- `README.md`: Windows setup, CLI/UI entry points, and license summary.
- `docs/development/README.md`: full stack (BS-RoFormer, WhisperX, pyannote, Dedicated Dubber-WebGPT on `127.0.0.1:17850/v1`, TTS/mix/QA) and operational runbook.
- `PLAN.md`: single owner for scope, phase status, and open acceptance gates (`P23` long-form/performance in progress; `Job12` completed processing with QA failed — never treat processing completion or a Final badge as QA pass).
- `frontend/PRODUCT-UI-CONTRACT.md`: media/rendition/attempt identity, shared source-media timebase, stale-preview invalidation, and Library/Watch/Review navigation contract.
- `.agents/skills/vidubber-ui-qa/SKILL.md`: repository-local web UI QA protocol.

## Repository Layout

- `src/vi_dubber/`: backend dubbing pipeline, manifests/resume, QA, and FastAPI server.
- `frontend/`: React/Vite dashboard and UI/telemetry/virtual-list contract verifiers (`frontend/scripts/verify_*_contract.mjs`).
- `tests/`: unit, artifact, fault, and contract tests.
- `scripts/`: offline contract verification and benchmark helpers.
- `work/`: local jobs, caches, outputs, and checkpoints (runtime media/artifacts stay untracked).

## Engineering & Git Hygiene

- Keep `pyproject.toml` and `uv.lock` synchronized (`uv lock` + `uv sync --locked --dev` before committing dependency changes; CI enforces `uv sync --locked --dev`).
- Use short task branches/PRs for coherent changes, preserve existing WIP/worktrees, and include `AI-Tool` + `AI-Model-Requested` trailers on substantive AI commits.
- Preserve manifest/SHA-256 atomic artifact commits and targeted chunk/segment invalidation; preview builds never substitute for final QA acceptance.
- Keep `Dedicated Dubber-WebGPT` (`127.0.0.1:17850`, `VI_DUBBER_WEBGPT_CORE`, bounded concurrency `2`) as the active translation path; never auto-fallback to legacy local/hybrid/Aurora adapters or route through Cockpit `:54005`.

## Safety Boundaries (Media, Credentials & Providers)

- **Credentials & private media**: never commit `.env`, Hugging Face tokens, OAuth/Drive tokens, browser login profiles, cookies, private configs with secrets, or user media/outputs under `work/`.
- **Provider & runtime isolation**: do not modify global Codex/Cockpit routes or launch Cockpit UI; preflight live WebGPT sessions before authorized provider runs.
- **No unapproved heavy runs**: do not trigger live translation calls, YouTube downloads, cloud/Drive exports, or multi-hour GPU renders without explicit task scope and detached checkpointing.
- **Standalone-first**: never hard-code parent-workspace absolute paths in code, scripts, tests, or configs.

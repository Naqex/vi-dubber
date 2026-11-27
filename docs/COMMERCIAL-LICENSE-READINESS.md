# VI Dubber Commercial License Readiness

This document records the exact, honest license-readiness posture of `vi-dubber`
as of `2026-11-27`, separating what is already enforced in first-party code and
CI from what still blocks commercial binary, wheel, container, or hosted
distribution.

See also [licensing](licensing.md) and
[third-party notices](../THIRD_PARTY_NOTICES.md).

## 1. Current Verdict: NOT YET CLEARED FOR COMMERCIAL DISTRIBUTION

- **Personal / non-commercial internal use:** Active and compliant under
  `Naqex Source Available License 1.0.0` and upstream terms.
- **Commercial binary, wheel, container, or paid SaaS distribution:**
  **BLOCKED (P0)** until transitive `diffq` / `diffq-fixed` (`CC-BY-NC-4.0`)
  wheels are removed from `uv.lock` and packaged runtimes.

## 2. What Is Enforced Today (Runtime & CI Controls)

1. **Zero first-party `diffq` / `demucs` imports:**
   - `src/vi_dubber/` contains `0` direct `import` or `from ... import`
     references to `diffq`, `diffq_fixed`, or `demucs`.
   - Enforced on every PR and push to `main` by the AST guard step in
     `.github/workflows/checks.yml` (`Guard against CC-BY-NC diffq/demucs imports in src/vi_dubber`)
     and by `tests/test_commercial_license_guard.py`.
2. **Explicit runtime denylist before model loading (`src/vi_dubber/separation.py`):**
   - `validate_separation_model_license()` runs at the entry of
     `separate_dialogue()` before importing `audio_separator.separator` or
     calling `Separator.load_model()`.
   - Any model filename, path, or loaded separator architecture containing
     `htdemucs`, `demucs`, or `diffq` (case-insensitive substring match) is
     rejected immediately with `CommercialLicenseError` (a `ValueError`
     subclass).
   - Uses an explicit denylist rather than a brittle filename allowlist so
     compatible RoFormer/MDXC checkpoints (for example
     `model_bs_roformer_ep_317_sdr_12.9755.ckpt`) and standard unit-test
     fixtures (`model.ckpt`) remain supported.
3. **Active production separation path:**
   - Default `config.yaml` selects `model_bs_roformer_ep_317_sdr_12.9755.ckpt`
     on the MIT/Apache-safe `MDXC / BS-RoFormer` inference path.
   - Because `audio-separator` loads architectures lazily, importing
     `audio_separator.separator.Separator` and running `MDXC / BS-RoFormer`
     does not import `demucs` or `diffq` at runtime.

## 3. Honest Commercial Boundary (Remaining P0 Blocker)

Although first-party code never imports or invokes `diffq` / `demucs`, the
locked Python dependency graph still resolves non-commercial wheels:

```text
vi-dubber==0.1.0 (pyproject.toml: audio-separator[cpu]>=0.44.2,<0.48)
  -> audio-separator==0.47.0 (MIT; 0.45.0 on macOS arm64)
     -> diffq-fixed==0.2.4 (Windows, CC-BY-NC-4.0)
     -> diffq==0.2.4 (Linux/macOS, CC-BY-NC-4.0)
```

- Both `diffq==0.2.4` and `diffq-fixed==0.2.4` are licensed under
  **Creative Commons Attribution-NonCommercial 4.0 International
  (`CC-BY-NC-4.0`)**, which prohibits commercial use and redistribution.
- Because `audio-separator==0.47.0` declares `diffq` / `diffq-fixed` as
  required package metadata dependencies, `uv.lock` still records them and
  `uv sync --locked` installs them into development `.venv` environments.
- **Hard release boundary:** Before any commercial binary, wheel, container,
  or paid hosted distribution of `vi-dubber`, `audio-separator` MUST be
  replaced (for example with a minimal direct PyTorch/ONNX BS-RoFormer runner)
  or stripped (for example an MIT fork/wheel without `diffq` / `diffq-fixed`
  and without the Demucs branch) so that `uv.lock` and the packaged runtime
  contain **`0` `CC-BY-NC` wheels**.

## 4. Additional Pre-Commercial Release Checklist

Before shipping any commercial build, complete and record all four items:

1. **Zero `CC-BY-NC` lockfile gate:** Replace or strip `audio-separator` so
   `uv.lock` has `0` references to `diffq` or `diffq-fixed`, then tighten CI
   to assert `0` `CC-BY-NC` packages in `uv.lock` and `importlib.util.find_spec("diffq") is None`
   in the commercial build environment.
2. **Weak-copyleft compliance (`LGPL` / `MPL-2.0`):** Retain notices and
   dynamic-linking boundaries for `soxr==1.1.0` (`LGPL-2.1-or-later`),
   `orjson==3.12.0` (`MPL-2.0 AND (Apache-2.0 OR MIT)`), `tqdm==4.70.1`
   (`MPL-2.0 AND MIT`), and `certifi==2026.7.22` (`MPL-2.0`), and document
   the `Artistic License` election for `text-unidecode==1.3`. Exclude dev-only
   `pytest-base-url==2.1.0` from production builds.
3. **AI model weight licensing:** Verify commercial redistribution/inference
   terms individually for every downloaded checkpoint (`BS-RoFormer`,
   `Whisper large-v3`, `VieNeu`, and any local or external translation model).
4. **FFmpeg build compliance:** Either keep FFmpeg user-supplied outside the
   bundle or ship an LGPL-only FFmpeg build without `--enable-gpl` codecs
   (`libx264`/`libx265`) unless complying with GPL obligations.

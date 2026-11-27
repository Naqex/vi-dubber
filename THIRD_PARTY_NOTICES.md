# Third-party components

First-party code and documentation use the
[Naqex Source Available License 1.0.0](LICENSE). See [licensing](docs/licensing.md)
and [commercial license readiness](docs/COMMERCIAL-LICENSE-READINESS.md).
This license does not relicense dependencies, model weights, source media or
external services.

| Component | License handling |
|---|---|
| Python dependencies | Exact versions are recorded in `uv.lock`; retain each component's applicable license and notices |
| `soxr` (`1.1.0`, transitive via `librosa` / `vieneu`) | `LGPL-2.1-or-later`; keep dynamically linked as a separate wheel/shared library (`libsoxr`), retain `COPYING.LGPL`, `LICENSE-libsoxr.txt`, and `LICENSE-PFFFT.txt`, and preserve user relinking rights when distributing |
| `orjson` (`3.12.0`) | `MPL-2.0 AND (Apache-2.0 OR MIT)`; retain `LICENSE-MPL-2.0` alongside the selected `MIT` or `Apache-2.0` notice when distributing |
| `tqdm` (`4.70.1`) | `MPL-2.0 AND MIT`; keep unmodified upstream package and retain `LICENCE` notices when distributing |
| `certifi` (`2026.7.22`) | `MPL-2.0`; keep unmodified Mozilla CA bundle and retain `MPL-2.0` notice when distributing |
| `text-unidecode` (`1.3`, transitive via `python-slugify`) | Dual-licensed `Artistic License OR GPLv2+`; this project elects the permissive `Artistic License` branch |
| `pytest-base-url` (`2.1.0`) | `MPL-2.0`; development/test-only (`dev` dependency group), excluded from production distribution |
| `audio-separator` (`0.47.0` / `0.45.0` on macOS arm64, `MIT`) and transitive `diffq` / `diffq-fixed` (`0.2.4`, `CC-BY-NC-4.0`) | **Commercial distribution boundary:** `audio-separator` declares required transitive dependencies on `diffq-fixed==0.2.4` (Windows) and `diffq==0.2.4` (Linux/macOS), both `CC-BY-NC-4.0` (non-commercial). First-party code in `src/vi_dubber/` has `0` direct imports of `diffq`/`demucs` and blocks `demucs`/`htdemucs`/`diffq` at runtime in `src/vi_dubber/separation.py`, using only the RoFormer/MDXC path. However, because `uv.lock` still resolves `diffq`/`diffq-fixed`, `audio-separator` MUST be replaced or stripped so `uv.lock` contains `0` `CC-BY-NC` wheels before any commercial binary, wheel, container, or paid hosted distribution. See [commercial license readiness](docs/COMMERCIAL-LICENSE-READINESS.md). |
| Speech, separation and translation models | Model weights (`BS-RoFormer`, `Whisper large-v3`, `VieNeu`, translation LLMs) and model-specific terms are separate from the application license and must be audited individually before commercial release |
| FFmpeg and other installed executables | Installed separately; rights and obligations depend on the actual build and enabled components (commercial builds bundling FFmpeg must use an LGPL build rather than GPL-enabled codecs such as `libx264`/`libx265`) |
| User media, voices and generated output | No ownership or third-party permission is supplied by the application license |
| External download and inference services | Provider terms and source-content rights apply separately |

Dependencies and models are not uniformly licensed. Before distributing a
particular build, inventory the actual components and weights included with
it and satisfy their respective terms. This document is an entry point, not a
claim that every transitive dependency or model has been cleared for commercial
redistribution.

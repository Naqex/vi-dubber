# Third-party components

First-party code and documentation use the
[Naqex Source Available License 1.0.0](LICENSE). See [licensing](docs/licensing.md).
This license does not relicense dependencies, model weights, source media or
external services.

| Component | License handling |
|---|---|
| Python dependencies | Exact versions are recorded in `uv.lock`; retain each component's applicable license and notices |
| Speech, separation and translation models | Model weights and model-specific terms are separate from the application license |
| FFmpeg and other installed executables | Installed separately; rights and obligations depend on the actual build and enabled components |
| User media, voices and generated output | No ownership or third-party permission is supplied by the application license |
| External download and inference services | Provider terms and source-content rights apply separately |

Dependencies and models are not uniformly licensed. Before distributing a
particular build, inventory the actual components and weights included with
it and satisfy their respective terms. This document is an entry point, not a
claim that every transitive dependency or model has been audited.

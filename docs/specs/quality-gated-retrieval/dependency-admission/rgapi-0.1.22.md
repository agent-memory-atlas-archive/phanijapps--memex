# Dependency Admission: rgapi 0.1.22

- **Status:** admitted for optional evaluation only
- **Date:** 2026-09-18
- **Owning spec:** [`../spec.md`](../spec.md)
- **Package identity:** `rgapi==0.1.22`
- **Runtime scope:** optional `eval-rgapi` extra; not imported from `src/memex`

## Intended Use

`rgapi` is admitted only as an offline candidate for the quality-gated
retrieval evaluator. SQLite FTS5 remains the default production and base
installation path.

## Provenance

- PyPI release page: `https://pypi.org/project/rgapi/0.1.22/`
- PyPI JSON: `https://pypi.org/pypi/rgapi/0.1.22/json`
- Source repository: `https://github.com/AnswerDotAI/rgapi`
- Verified source tag: `v0.1.22`, commit
  `59f2730c471d4a3debfcb25ffe16d8dc6d2cf8c4`
- PyPI attestation publisher for the 0.1.22 sdist and wheels:
  `ci.yml` on `AnswerDotAI/rgapi`
- PyPI Trusted Publishing: yes for the 0.1.22 sdist and wheels
- Trusted Publishing source permalink:
  `AnswerDotAI/rgapi@59f2730c471d4a3debfcb25ffe16d8dc6d2cf8c4`
- Trusted Publishing tag: `refs/tags/v0.1.22`
- Token issuer: `https://token.actions.githubusercontent.com`
- Runner environment: GitHub-hosted
- Publication workflow:
  `ci.yml@59f2730c471d4a3debfcb25ffe16d8dc6d2cf8c4`
- Trigger event: `push`
- PyPI maintainer account: `fastai`
- Project credits list author metadata as `Jeremy Howard <j@fast.ai>`. This is
  descriptive package metadata, not publisher proof.
- Python requirement: `>=3.10`; Memex requires `>=3.12`
- Direct Python dependency: `fastcore>=1.14.6`, resolved to `fastcore==2.2.28`

## Maintenance Evidence

- `v0.1.22` was uploaded to PyPI on August 21, 2026.
- GitHub release `v0.1.22` was published by `github-actions` on August 21,
  2026 at 16:19 and points at commit
  `59f2730c471d4a3debfcb25ffe16d8dc6d2cf8c4`.
- GitHub showed 16 commits to `main` after `v0.1.22` at the time this
  admission was updated.
- PyPI showed a newer release, `0.1.27`, released on September 17, 2026 at the
  time this admission was updated.
- PyPI showed one open-source maintainer account, `fastai`, for the project.

## Lock Integrity

`uv.lock` pins the optional extra and both Python packages:

- `memex[eval-rgapi]` requires `rgapi==0.1.22`
- `rgapi==0.1.22` sdist hash:
  `sha256:c50e23f7a81a09a1dd32b0d7ae0d309c7f1c17d6cb116d76921b5ea3a5c90e58`
- `rgapi==0.1.22` CPython 3.12 Linux x86_64 wheel hash:
  `sha256:207b35c57f19948ae49291f947f4eec69ace85882d888acfc380f8c9a292c02c`
- `fastcore==2.2.28` wheel hash:
  `sha256:c9fa3364ee32628f0ed77be165573ca0e276ea61e44a20c18da49e6252e082c0`

## License Evidence

Python package metadata reports:

- `rgapi==0.1.22`: Apache-2.0
- `fastcore==2.2.28`: Apache-2.0

`cargo metadata --manifest-path <rgapi-sdist>/Cargo.toml --locked` reported
only permissive Rust license expressions: Apache-2.0, MIT, Unlicense,
BSD-3-Clause, and Unicode-3.0 combinations.

## Vulnerability Scans

Python SCA:

```bash
uv export --extra eval-rgapi --format requirements-txt --no-hashes > "$audit_req"
uvx --from pip-audit pip-audit -r "$audit_req"
```

Result: no known vulnerabilities found. `memex==0.2.4` was skipped because it
is the local unpublished package, not a PyPI dependency.

Rust SCA:

```bash
cargo audit --db "$audit_db" --file <rgapi-sdist>/Cargo.lock
```

Result: passed. The scanner loaded 1,251 RustSec advisories and scanned the
locked `rgapi` Rust dependency tree containing 46 crate dependencies.

## Portability Note

The pinned release provides CPython wheels for macOS arm64 and Linux
x86_64/aarch64, plus an sdist. It does not provide Windows or macOS x86_64
wheels. Because an sdist build may require a Rust toolchain, the dependency is
kept out of the base install and production runtime.

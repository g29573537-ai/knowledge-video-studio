# MANIFEST_ROLLOUT_SUMMARY.md

## Result

All manifest steps 0-7 were implemented in the fork `g29573537-ai/knowledge-video-studio` on branch `main`. Each step received a separate commit. The existing test suite remains green.

## Baseline

- Baseline commit: `53489f7f1013b1122f4e9e7f81a104834a5e7d13` (`chore: freeze baseline before manifest rollout`)
- Baseline report: `baseline_test_report.md`
- Baseline result: 65 passed, 7 skipped, 0 failed
- Final result after all steps: 90 passed, 7 skipped, 0 failed (`python -m pytest -q`)

## Step commits

| Step | Commit | Summary |
|---|---|---|
| 0 | `53489f7f1013b1122f4e9e7f81a104834a5e7d13` | Freeze baseline before manifest rollout |
| 1 | `aed2b09a50277b21e6a960ae5511cae0e6fa8031` | SemanticTimeline v1 layer (`knowledge_video/semantic_timeline.py`), `Block.visual_role`/`semantic_version`, tests |
| 2 | `6aadb46b77db79854bf366fa137287d4ec852d36` | Crash-safe run state (`knowledge_video/run_state.py`), fingerprinted `Workflow.llm` cache, Jobs heartbeat/integration |
| 3 | `55c6b9c6af9814fc55bac7bbbb523be38fc00a98` | Media rights registry (`knowledge_video/media_rights.py`) with stock/generated provenance |
| 4 | `8e83ee6df3e055d239b77f25eb2151d0599f8a26` | Independent media provider routing (`knowledge_video/media_providers/`) |
| 5 | `cb2342385a1b08f7077483d5ed23396cb6b0daa8` | Procedural-first visual policy (`knowledge_video/visuals.py`, `VisualConfig`) |
| 6 | `9c76baf2a4e0238bd2fb6fb8097257ae1e9cd750` | Auto-fill only secondary/bridge/background visuals |
| 7 | `58bb07020a752a6675f2652969c3232fdf732502` | Final QC gate (`narration_video/qc.py`, integrated before `tmp.replace(target)`) |

## Added tests

- `tests/test_semantic_timeline.py` (4 passed)
- `tests/test_run_state.py` (4 passed)
- `tests/test_media_rights.py` (4 passed)
- `tests/test_media_providers.py` (3 passed)
- `tests/test_visuals.py` (2 passed)
- `tests/test_auto_fill.py` (3 passed)
- `tests/test_qc.py` (5 passed)

## Known limitations / TODO

- Remote image/video adapters remain intentionally disabled; only fake and local procedural providers are registered.
- Local diffusion is not installed in this environment; `_diffusion_available` defaults to false and can be overridden for tests or future adapters.
- Semantic timeline is a new additive layer; it is not yet wired into the production render path or `quality.json`.
- Auto-fill helper is implemented and tested, but the full production workflow does not yet call it automatically.
- AI-generated media is never marked commercially allowed by default; manual terms review is required.
- Human/OCR readability review remains separate from technical QC, as required by the manifest.
- QC frame-count validation uses a one-frame tolerance to accommodate encoder/container rounding.
- No real model run or browser/media acceptance test was performed; this rollout is covered by fixture/unit tests only.

## License notes

- AIF-derived and Silicon-derived patterns were reimplemented with attribution in commit messages and module docstrings.
- No Split Node YouTube or anything2explainer code was copied; provider routing is an independent implementation.

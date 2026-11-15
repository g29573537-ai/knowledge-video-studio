# Kaggle ML offload plan (draft, not executed)

## Current state verified

- `df -h /workspaces`: 32G total, 20G used, 9.9G available, 67%.
- No item >=500MB is inside the repository.
- `.runtime/` is absent; heavy ML runtime is not installed in Codespace.
- `HF_TOKEN=` exists in `.env` as a placeholder; the owner must fill it.
- Kilo Gateway external LLM is used for script generation.
- Kaggle CLI is installed and `KAGGLE_API_TOKEN` works.

## Item 1 — Forced alignment on Kaggle (in progress)

- Push `forts845/kvs-align-smoke2` with a short English sentence.
- Poll with explicit timeout; if `QUEUED` longer than 10-15 minutes, report
  `Kaggle queue stuck` and stop. Do not silently fall back to local.
- Fetch `aligned.json`; verify coverage >= 90%.
- Only after 2-3 successful runs, switch `narration_video/alignment.py` callers to Kaggle.

## Item 2 — TTS

- Already proven on Kaggle: Kokoro and CosyVoice3.
- Codespace keeps only `voice_profiles/*.json` and final WAV/MP3.
- No model weights or TTS venv stay in Codespace.

## Item 3 — LLM

- Use Kilo Gateway `kilo-auto/free` (or another configured external provider).
- No local LLM weights or inference runtime in Codespace.

## Item 4 — Render

- Keep ffmpeg, Chrome, Node, and QC local because they are lightweight.
- If render becomes heavy (large batches), move that stage to Kaggle separately.

## Cleanup rule

- Before deleting any directory, add an entry to `deletion_manifest.json`
  with path, size, and reason.
- Never delete a directory that is a dependency of a mandatory step until a
  verified replacement exists.
- Run `df -h /workspaces` before and after every major pipeline step.

## Step 1 result (20261115T162206Z)

- Kernel: forts845/kvs-align-smoke2
- Status: COMPLETE
- Text: "The sun gives energy to plants."
- Duration: 2.76 s
- Aligned characters: 31
- Coverage: 1.0
- Evidence: audit/kaggle_alignment_evidence/20261115T162206Z/aligned.json

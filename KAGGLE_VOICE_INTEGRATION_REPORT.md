# KAGGLE_VOICE_INTEGRATION_REPORT.md

## What was done

- Studied `/tmp/OpenMontage-audit/tools/kaggle_bridge/kaggle_bridge.py` and its tests for the push/poll/fetch pattern, including terminal-status early exit.
- Added `knowledge_video/media_providers/kaggle_voice.py` with `KaggleVoice`, implementing the same `synthesize(text, cache, identity) -> (Path, bool)` contract as `narration_video.voice.OmniVoice`.
- Polling exits immediately on `complete`, and raises on `error`, `failed`, `cancelled`, or `timeout`; it does not loop after a terminal status.
- Added `voice_backend` to `JobRequest` (`omnivoice` default, `kaggle_cosyvoice3` explicit) and propagated it through `Workflow` into `cfg["voice"]["backend"]`.
- `narration_video/cli.py::synthesize` selects `KaggleVoice` only when `voice.backend == "kaggle_cosyvoice3"`; OmniVoice remains the default fallback.
- Added `tests/test_kaggle_voice.py`, which passes with a fake Kaggle CLI (push/poll/fetch and cached reuse; early exit on error).

## Real Kaggle run

Not performed. This Codespace has no Kaggle credentials:

```text
=== env | grep -i kaggle ===
(no output)
```

No `kaggle` executable is installed, and `KAGGLE_USERNAME`/`KAGGLE_KEY` (or `KAGGLE_API_TOKEN`) are not present in the environment. Therefore no kernel was pushed, no CosyVoice3 inference ran, and no test audio file was downloaded.

## What is needed from the user

Add these Codespace Secrets (or environment variables) before a real run:

- `KAGGLE_USERNAME`
- `KAGGLE_KEY`

or, depending on the installed Kaggle CLI version:

- `KAGGLE_API_TOKEN`

Also required for a real CosyVoice3 run:

- a Kaggle kernel slug containing a working CosyVoice3 `run.py` (or the `run_py` text passed through `cfg["voice"]["run_py"]`);
- GPU internet access enabled if the kernel must download model weights;
- an authorized reference voice is not needed for this provider test, but the normal Knowledge Video Studio pipeline still requires an authorized voice recording for production.

## Status of the scaffold

The orchestration path is unit-tested with a fake Kaggle CLI. The CosyVoice3 inference itself is not validated in this environment because Kaggle credentials and a CosyVoice kernel are unavailable.

## Real Kaggle run attempt (2026-11-14)

- Credentials are now available; `KAGGLE_API_TOKEN` works (`kaggle kernels list` succeeded).
- Pushed kernel: `forts845/kvs-cosyvoice3-smoke` with the OpenMontage CosyVoice3 audit script as `run.py`.
- Polling result: kernel remained `KernelWorkerStatus.QUEUED` for more than 18 minutes.
- No output files were produced, so no audio file or ffprobe duration exists.
- Process was stopped after the long queue wait; no partial result is reported as success.

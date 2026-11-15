# Storage policy

1. Codespace disk is for code, configs, and light artifacts only. Heavy ML
   dependencies, model weights, GPU venvs, datasets, and large renders are not
   installed in Codespace by default. Exceptions require explicit owner approval
   with reason and size.

2. GPU/ML computation runs on Kaggle. Codespace orchestrates only.

3. Technical debt: forced alignment currently depends on a local venv. That
   dependency must be moved to Kaggle or replaced with a lightweight alternative;
   it is not a permanent norm.

4. Before any dependency/model/venv installation or download:
   - check disk space first;
   - create a deletion manifest entry before deleting anything;
   - do not delete directories required for mandatory steps such as forced
     alignment; delete only optional components.

5. Verification before cleanup: never clean disk while artifacts from a run are
   still under review. Verify first, cleanup second, never in parallel or reverse.

## Thresholds and reporting

- If available space is below 5 GB or usage is above 80%, stop before installing,
  downloading, or creating environments. Report to the owner and propose cleanup first.
- After every major pipeline step (TTS, alignment, render), run `df -h` again and
  record the result.
- Every final pilot/video report must include `df -h /workspaces` before and after.
- Before deleting anything, verify it is not a dependency of a mandatory step.
  Forced alignment's acoustic model is mandatory; do not delete the environment
  that provides it without a planned replacement.

## Superpowers discipline integration

When Superpowers is installed in OpenCode, apply these skills automatically:

- `systematic-debugging` before changing code for any failed test, Kaggle job, or pipeline stage.
- `verification-before-completion` before claiming any pilot/video/QC result is ready.
- `test-driven-development` before adding new provider/timeline/QC behavior.
- `writing-plans` before multi-step storage or Kaggle migration work.
- `using-git-worktrees` for isolated feature work when needed.

No unverified third-party skills may be installed without explicit owner approval.

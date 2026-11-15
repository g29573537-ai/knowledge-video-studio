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

# Kaggle usage stats (2026-11-15)

Kernels created today by this project:

1. forts845/kvs-omnivoice-voice-candidates — COMPLETE
2. forts845/kvs-cosyvoice3-voice-d — COMPLETE
3. forts845/kvs-cosyvoice3-smoke — COMPLETE
4. forts845/kvs-align-smoke — ERROR (espeak-ng missing in kernel)
5. forts845/kvs-align-smoke2 — COMPLETE (coverage 1.0)
6. forts845/kvs-align-repeat1 — COMPLETE (coverage 1.0)
7. forts845/kvs-align-repeat2 — QUEUED > 10 min, deleted (queue stuck)
8. forts845/kvs-align-repeat3 — QUEUED > 10 min (queue stuck)

Totals:
- attempts: 8
- successful: 5
- errored: 1
- stuck in queue: 2

Alignment-only attempts:
- attempts: 5
- successful: 2
- errored: 1
- stuck in queue: 2

Conclusion: queue instability is a real operational risk. Do not treat one successful run as production-ready; require repeated successful runs before switching the pipeline.

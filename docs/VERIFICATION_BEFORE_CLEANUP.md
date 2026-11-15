# Verification before cleanup

Permanent rule for pilot and production runs:

1. Never run disk cleanup while there is an open request to inspect artifacts from a specific run.
2. First verify and preserve the required evidence (`lesson.json`, raw alignment JSON, QC reports, metrics).
3. Only after verification is complete and explicitly approved may cleanup remove build/output artifacts.
4. Verification and cleanup are never performed in parallel and never in reverse order.

# Baseline Test Report

- Repository HEAD: `cee5973 Add files via upload`
- Frozen HEAD SHA: `cee5973` (full: see `git rev-parse HEAD`)
- Date: 2026-11-14
- Command: `python -m pytest -q`
- Result: **65 passed, 7 skipped, 0 failed**
- Environment notes: ffmpeg and Noto CJK fonts installed for media tests; Python 3.14.2.

Existing public tests at baseline:
- tests/test_export.py
- tests/test_voice.py
- tests/test_timing.py
- tests/test_studio.py
- plus tests/test_alignment_omissions.py, test_lesson_ids.py, test_server.py, test_release.py, test_languages.py, test_retime.py, test_optional_sources.py, test_publishing.py, test_slide_render.py

No donor changes applied before this baseline.

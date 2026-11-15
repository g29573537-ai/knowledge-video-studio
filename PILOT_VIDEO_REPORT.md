# PILOT_VIDEO_REPORT.md

## Status

Ready for owner review: YES for technical QC, NO for publication until owner listens and approves.

## Video

- Path: `previews/first_test_video.mp4`
- Source path: `/workspaces/pilot-kokoro-output/build/video.mp4`
- SHA-256: `4aabf1e4e164c32d2878ae3851c178694ffae4f151eb8a86db3a312020815b6c`
- Duration: 38.266667 s
- Resolution: 1920x1080
- FPS: 30/1
- Video codec: h264
- Audio codec: aac
- Audio duration: 38.25 s

## QC

- `qc_report.json`: passed=true, technical_passed=true, failures=[].
- `quality.json`: technical_passed=true, subtitle_characters_match=true.
- Human listening review: recommended.

## Supporting files

- Project: `/workspaces/pilot-kokoro-output/project.json`
- Lesson: `/workspaces/pilot-kokoro-output/lesson.json`
- Semantic timeline: `/workspaces/pilot-kokoro-output/semantic_timeline.json`
- Media rights: `/workspaces/pilot-kokoro-output/media_rights.json`
- QC report: `/workspaces/pilot-kokoro-output/build/qc_report.json`
- Quality: `/workspaces/pilot-kokoro-output/quality.json`
- Narration: `/workspaces/pilot-kokoro-output/narration.md`
- Slides: `/workspaces/pilot-kokoro-output/slides.html`

## Voice

- Backend: Kokoro `af_heart`
- Language: English
- LLM provider: Kilo Gateway `kilo-auto/free`

## Owner approval points

- Listen to the full 38.3 s video and approve voice quality.
- Confirm English pronunciation and pacing.
- Confirm slide visuals and subtitle coverage.
- Decide whether to publish; no publication was performed.

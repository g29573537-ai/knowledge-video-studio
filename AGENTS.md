# Working in this repository

This repository is a local knowledge-video production application. Start by reading README.md and docs/WORKFLOW.md.

- Use `knowledge-video doctor` to inspect the environment and `knowledge-video serve` to launch the frontend.
- The user chooses their voice recording/profile, topic, model provider and HTML template/deck. Never substitute a different voice or model silently.
- Codex mode uses the user's installed authenticated CLI. Never read, copy or commit auth.json. Do not use a browser session cookie as an API key.
- Keep recordings, generated videos, provider outputs, tokens and local absolute paths out of distributable source. `.studio/` is private runtime data.
- Build jobs through the packaged API/CLI. Do not fabricate successful job states or use fixture media as evidence of model execution.
- Audio is the clock. Preserve the full source waveform and adjust cue/subtitle times together when changing playback_speed.
- Do not weaken alignment gates to make a job pass. Retry bounded failed blocks, then report the concrete failure.
- Preserve existing HTML files. Adapt only the private task copy.
- After code changes, run `pytest -q` and relevant Node syntax checks. A real model run and browser/media checks are separate from fixture tests.
- Do not publish a repository, upload a user's voice or post a video to an external platform without their authorization.

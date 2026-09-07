# Third-party components

The application source and included generic HTML template are MIT licensed. No personal voice recordings, model weights, Zero2Quant logos or user course templates are distributed.

Dependencies retain their own licenses. In particular:

- OmniVoice Studio is an external service: https://github.com/Galest/OmniVoice-Studio . Its application, engine, model and tokenizer licenses are separate from this repository.
- WhisperX and faster-whisper provide local alignment and transcription. The selected alignment/ASR model weights retain their model-card licenses.
- FFmpeg is an external executable. Its build configuration and included codecs determine applicable distribution terms. This repository does not bundle FFmpeg binaries.
- Chrome / Chromium and system fonts are installed separately.
- FastAPI, Uvicorn, Pydantic, jsonschema, requests, NumPy, SoundFile and Pillow are Python dependencies; see their package metadata for licenses.
- Codex is an external user-installed program; OpenAI product terms and account limits apply. External model providers have their own terms and billing.

The media engine was extracted from the author's local NarrationVideoPipeline implementation. Existing user data and generated production artifacts were intentionally excluded.

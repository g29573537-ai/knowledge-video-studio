# Voice candidate QC table

Test text: the photosynthesis passage from the task (same for all candidates).

| Metric | A | B | C | D |
|---|---:|---:|---:|---:|
| Engine | OmniVoice voice-design | OmniVoice voice-design | OmniVoice voice-design | CosyVoice3 (Kokoro af_heart reference) |
| Instruct / reference | male, low pitch, american accent, middle-aged | female, moderate pitch, american accent, young adult | male, moderate pitch, american accent, young adult | Kokoro af_heart 10-15s reference, then CosyVoice3 |
| Duration (s) | 36.08 | 36.08 | 36.08 | 39.64 |
| Sample rate (Hz) | 48000 | 48000 | 48000 | 48000 |
| Channels | 1 | 1 | 1 | 1 |
| Bit depth | 24 | 24 | 24 | 24 |
| WPM | 164.6 | 164.6 | 164.6 | 149.8 |
| Clipping samples at 0 dBFS | 0 | 0 | 0 | 0 |
| Integrated LUFS (after normalization) | -16.24 | -16.75 | -16.34 | -16.10 |
| True peak (dBTP) | -1.00 | -1.00 | -1.00 | -1.00 |
| Shortest silence (s) | 0.205 | 0.260 | 0.216 | 0.217 |
| Longest silence (s) | 0.416 | 0.288 | 0.359 | 0.680 |
| WER (Whisper small, en) | 0.101 | 0.061 | 0.081 | 0.091 |
| chloroplasts recognized | yes | yes | yes | yes |
| photosynthesis recognized | yes | yes | yes | yes |
| photons recognized | yes | yes | yes | yes |
| Numbers | Whisper transcribed digits (4, 2, 130), causing WER; wording "four million", "two billion", "one hundred and thirty billion" was spoken | same | same | same |

WER note: the main WER contribution is number wording vs. Whisper's digit transcription, not missing terms. All three key terms were recognized in every candidate.

SHA-256:
- A: `43e455ba595702abdbc19ff7cc662a104d42d1de3007fa983c57315181a46a08`
- B: `83da3619b3c8eee5646ccae355215e2929f24988a42ef6e0fb6174a4556e8768`
- C: `182dae879ada1d0d1324cfe98f5503917dcd112e798373bbb627da1be7afd71e`
- D: `a08669100afd41795e95dc0f6302afd6f098203923723a5f4d383236a3ae9fe4`

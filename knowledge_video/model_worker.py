"""Download known speech components, verify they load, optionally warm TTS."""

import argparse
import gc
import os
from pathlib import Path

from narration_video.voice import OmniVoice

from .languages import ASR_MODELS, LANGUAGES
from .runtime import atomic_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", choices=LANGUAGES, required=True)
    parser.add_argument("--asr-model", choices=ASR_MODELS, default="small")
    parser.add_argument("--action", choices=["download", "load"], required=True)
    parser.add_argument("--voice-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ["DISABLE_SAFETENSORS_CONVERSION"] = "1"
    import torch
    import torchaudio
    from faster_whisper import WhisperModel
    from huggingface_hub import snapshot_download
    from whisperx.alignment import (
        DEFAULT_ALIGN_MODELS_HF,
        DEFAULT_ALIGN_MODELS_TORCH,
        load_align_model,
    )

    paths = []
    print("STEP 1/4 下载或复用 OmniVoice 多语言克隆权重", flush=True)
    tts = Path(snapshot_download("k2-fsa/OmniVoice"))
    paths.append(str(tts / "config.json"))
    paths.extend(str(p) for p in tts.glob("*.safetensors"))
    tokenizer = tts / "audio_tokenizer"
    if not tokenizer.is_dir():
        tokenizer = Path(snapshot_download("eustlb/higgs-audio-v2-tokenizer"))
    paths.append(str(tokenizer / "config.json"))
    paths.extend(str(p) for p in tokenizer.glob("*.safetensors"))
    print("STEP 2/4 下载并检查多语言语音识别模型", flush=True)
    asr_path = Path(snapshot_download("Systran/faster-whisper-" + args.asr_model))
    asr = WhisperModel(str(asr_path), device="cpu", compute_type="int8", cpu_threads=4)
    paths.append(str(asr_path / "model.bin"))
    del asr
    gc.collect()
    print("STEP 3/4 下载并加载目标语言字幕对齐模型", flush=True)
    torch.set_num_threads(4)
    model, metadata = load_align_model(args.language, "cpu")
    if args.language in DEFAULT_ALIGN_MODELS_HF:
        aligned_path = Path(
            snapshot_download(
                DEFAULT_ALIGN_MODELS_HF[args.language], local_files_only=True
            )
        )
        paths.append(str(aligned_path / "config.json"))
        paths.extend(str(p) for p in aligned_path.glob("*.bin"))
        paths.extend(str(p) for p in aligned_path.glob("*.safetensors"))
        alignment_model = DEFAULT_ALIGN_MODELS_HF[args.language]
    else:
        alignment_model = DEFAULT_ALIGN_MODELS_TORCH[args.language]
        bundle = getattr(torchaudio.pipelines, alignment_model)
        paths.append(
            str(Path(torch.hub.get_dir()) / "checkpoints" / Path(bundle._path).name)
        )
    del model, metadata
    gc.collect()
    if any(not Path(p).is_file() for p in paths):
        raise RuntimeError("Downloaded model files are incomplete")
    print(
        "STEP 4/4 "
        + (
            "载入 OmniVoice 并等待真实就绪状态"
            if args.action == "load"
            else "模型已下载，对齐和识别模型加载检查通过"
        ),
        flush=True,
    )
    if args.action == "load":
        OmniVoice(
            {"base_url": args.voice_url, "warmup_timeout_seconds": 1800}
        ).wait_ready()
    atomic_json(
        args.output,
        {
            "language": args.language,
            "asr_model": args.asr_model,
            "tts_model": "k2-fsa/OmniVoice",
            "alignment_model": alignment_model,
            "files": [
                {"path": p, "size": Path(p).stat().st_size} for p in sorted(set(paths))
            ],
        },
    )
    print("模型准备完成", flush=True)


if __name__ == "__main__":
    main()

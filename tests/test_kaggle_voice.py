import os

from knowledge_video.media_providers.kaggle_voice import KaggleVoice

FAKE_KAGGLE = r"""#!/usr/bin/env python3
import sys, os, json, hashlib
STATE=os.environ.get("FAKE_KAGGLE_STATE","/tmp/fk_state.json")
def load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"mode":"ok","status_seq":["queued","running","complete"],"status_idx":0}
def save(s):
    tmp=STATE+".tmp"
    with open(tmp,"w") as f:
        json.dump(s,f)
    os.replace(tmp,STATE)
def main():
    argv=sys.argv[1:]
    if not argv: return 1
    cmd=argv[0]
    state=load()
    mode=state.get("mode","ok")
    if cmd=="kernels":
        sub=argv[1] if len(argv)>1 else ""
        if sub=="push":
            if mode=="auth_fail":
                print("Authentication required", file=sys.stderr); return 1
            print("Successfully pushed kernel"); return 0
        if sub=="status":
            seq=state.get("status_seq",["queued","running","complete"])
            idx=state.get("status_idx",0)
            st=seq[idx] if idx < len(seq) else seq[-1]
            state["status_idx"]=idx+1
            save(state)
            print(f'foo has status "KernelWorkerStatus.{st.upper() if False else st.capitalize()}"')
            # normalize to lowercase token expected by provider
            print(st)
            return 0
        if sub=="output":
            dest=None
            for i,a in enumerate(argv):
                if a=="-p" and i+1<len(argv): dest=argv[i+1]
            if dest:
                os.makedirs(dest,exist_ok=True)
                wav=b"RIFF....WAVE...."
                open(os.path.join(dest,"job1.wav"),"wb").write(wav)
                with open(os.path.join(dest,"manifest.json"),"w") as f:
                    json.dump({"job_id":"job1","sha256":hashlib.sha256(wav).hexdigest()}, f)
            return 0
    return 1
sys.exit(main())
"""


def write_fake(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    fake = bindir / "kaggle"
    fake.write_text(FAKE_KAGGLE)
    fake.chmod(0o755)
    state_path = str(tmp_path / "state.json")
    import json

    with open(state_path, "w") as f:
        json.dump(
            {
                "mode": "ok",
                "status_seq": ["queued", "running", "complete"],
                "status_idx": 0,
            },
            f,
        )
    os.environ["FAKE_KAGGLE_STATE"] = state_path
    return str(fake), state_path


def test_kaggle_voice_synthesize_with_fake_kaggle(tmp_path):
    fake, _state = write_fake(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    voice = KaggleVoice(
        {
            "kaggle_cmd": fake,
            "kernel_slug": "forts845/test-voice",
            "run_py": "print('ok')\n",
            "poll_backoff": 0.01,
            "total_timeout": 10,
        }
    )
    audio, cached = voice.synthesize("hello world", cache, {"mode": "clone"})
    assert cached is False
    assert audio.exists()
    assert audio.suffix == ".wav"
    # cached reuse
    audio2, cached2 = voice.synthesize("hello world", cache, {"mode": "clone"})
    assert cached2 is True
    assert audio2 == audio


def test_kaggle_voice_poll_early_exit_on_error(tmp_path):
    fake, _state = write_fake(tmp_path)
    # force error status sequence
    import json

    with open(_state, "w") as f:
        json.dump(
            {"mode": "error", "status_seq": ["running", "error"], "status_idx": 0}, f
        )
    cache = tmp_path / "cache2"
    cache.mkdir()
    voice = KaggleVoice(
        {
            "kaggle_cmd": fake,
            "kernel_slug": "forts845/test-voice",
            "run_py": "print('ok')\n",
            "poll_backoff": 0.01,
            "total_timeout": 10,
        }
    )
    # monkeypatch _push to no-op so we can test poll failure
    voice._push = lambda folder: None
    try:
        voice.synthesize("hello", cache, {"mode": "clone"})
    except RuntimeError as exc:
        assert "terminal status" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")

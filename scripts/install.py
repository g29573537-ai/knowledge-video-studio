"""Install a private, pinned OmniVoice checkout and the video workbench."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OMNI_URL = "https://github.com/Galest/OmniVoice-Studio.git"
OMNI_REV = "b8e219e7d1d5cfe14fab1a89673281cf1e7251ae"
NODE_VERSION = "22.16.0"


def commands(root):
    omni = root / ".runtime/omnivoice"
    return [
        (["git", "init", str(omni)], root),
        (["git", "remote", "add", "origin", OMNI_URL], omni),
        (["git", "fetch", "--depth", "1", "origin", OMNI_REV], omni),
        (["git", "checkout", "--detach", "FETCH_HEAD"], omni),
        (["uv", "sync", "--frozen", "--no-dev", "--python", "3.11"], omni),
        (
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(omni / ".venv/bin/python"),
                "-e",
                str(root) + "[media]",
            ],
            root,
        ),
    ]


def run(args, cwd=None):
    print("+ " + " ".join(map(str, args)), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def install_node(runtime):
    current = shutil.which("node")
    if (
        current
        and int(
            subprocess.check_output(
                [current, "-p", 'process.versions.node.split(".")[0]'], text=True
            )
        )
        >= 22
    ):
        return
    machine = {
        "arm64": "arm64",
        "aarch64": "arm64",
        "x86_64": "x64",
        "AMD64": "x64",
    }.get(platform.machine())
    system = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
    if not system or not machine:
        raise RuntimeError("Please install Node.js 22+ for this platform.")
    name = f"node-v{NODE_VERSION}-{system}-{machine}"
    filename = name + ".tar.gz"
    base = f"https://nodejs.org/dist/v{NODE_VERSION}/"
    with tempfile.TemporaryDirectory() as folder:
        archive = Path(folder) / filename
        urllib.request.urlretrieve(base + filename, archive)
        sums = (
            urllib.request.urlopen(base + "SHASUMS256.txt", timeout=60).read().decode()
        )
        expected = next(
            line.split()[0]
            for line in sums.splitlines()
            if line.split()[-1] == filename
        )
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Node download checksum mismatch")
        with tarfile.open(archive) as tar:
            tar.extractall(folder, filter="data")
        shutil.copytree(Path(folder) / name, runtime / "node", dirs_exist_ok=True)


def system_dependencies():
    missing = [name for name in ["git", "ffmpeg"] if not shutil.which(name)]
    chrome = (
        any(shutil.which(x) for x in ["google-chrome", "chromium", "chromium-browser"])
        or Path("/Applications/Google Chrome.app").exists()
        or os.environ.get("CHROME_BIN")
    )
    if platform.system() == "Darwin":
        if (missing or not chrome) and not shutil.which("brew"):
            raise RuntimeError(
                "Install Homebrew, or install Git, FFmpeg and Chrome yourself, then retry."
            )
        if missing:
            run(["brew", "install", *missing])
        if not chrome:
            run(["brew", "install", "--cask", "google-chrome"])
    elif platform.system() == "Linux":
        if missing or not chrome:
            if not shutil.which("apt-get"):
                raise RuntimeError(
                    "Install Git, FFmpeg, Chrome/Chromium and CJK fonts with your package manager."
                )
            prefix = [] if os.geteuid() == 0 else ["sudo"]
            run(prefix + ["apt-get", "update"])
            run(
                prefix
                + [
                    "apt-get",
                    "install",
                    "-y",
                    *missing,
                    "fonts-noto-cjk",
                    *([] if chrome else ["chromium"]),
                ]
            )
    else:
        raise RuntimeError("Use macOS, Linux or WSL for this installer.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print install commands without downloads or changes",
    )
    parser.add_argument("--skip-system-deps", action="store_true")
    args = parser.parse_args()
    plan = commands(ROOT)
    if args.dry_run:
        print(
            "System: Git, FFmpeg, Chrome, CJK fonts; Node.js 22+ (official checksum verified)."
        )
        for argv, cwd in plan:
            print(json.dumps({"cwd": str(cwd), "argv": argv}))
        return
    if not args.skip_system_deps:
        system_dependencies()
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    install_node(runtime)
    omni = runtime / "omnivoice"
    if omni.exists():
        if not (omni / ".git").exists():
            raise RuntimeError(
                f"{omni} already exists and is not a Git checkout; refusing to overwrite it."
            )
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=omni, text=True
        ).strip()
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=omni, text=True
        ).strip()
        if remote != OMNI_URL or revision != OMNI_REV:
            raise RuntimeError(
                "Existing private checkout differs from the pinned source; no files were changed."
            )
        plan = plan[4:]
    for argv, cwd in plan:
        run(argv, cwd)
    # Preflight the installed package; models are selected and downloaded in the UI.
    run([str(omni / ".venv/bin/python"), "-m", "knowledge_video.cli", "doctor"], ROOT)
    print("\nInstalled. Run ./scripts/start, then open http://127.0.0.1:8770/ .")
    print(
        "Select a language in the model panel to download weights and load the model."
    )


if __name__ == "__main__":
    main()

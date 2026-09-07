"""Build a source-only archive. Runtime data and media are never considered."""

import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = [
    "README.md",
    "LICENSE",
    "THIRD_PARTY.md",
    "AGENTS.md",
    "pyproject.toml",
    ".gitignore",
    "MANIFEST.in",
]
for directory in [
    "knowledge_video",
    "narration_video",
    "docs",
    "tests",
    "examples",
    "scripts",
    ".github",
]:
    for path in (root / directory).rglob("*"):
        if (
            path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in (".pyc", ".wav", ".mp4", ".m4a")
        ):
            files.append(str(path.relative_to(root)))
out = root / "dist/knowledge-video-studio-source.zip"
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(set(files)):
        archive.write(root / name, "KnowledgeVideoStudio/" + name)
print(out)

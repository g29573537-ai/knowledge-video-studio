"""Build an audited source-only archive from Git-tracked public files."""

import zipfile
from pathlib import Path

try:
    from .audit_release import audit_worktree
except ImportError:
    from audit_release import audit_worktree


def package(root, out):
    names, errors = audit_worktree(root)
    if errors:
        # Do not include file contents or credential values in errors.
        raise ValueError(f'Release audit failed: {errors}')
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(names):
            archive.write(root / name, 'KnowledgeVideoStudio/' + name)
    return names


def main():
    root = Path(__file__).resolve().parents[1]
    out = root / 'dist/knowledge-video-studio-source.zip'
    names = package(root, out)
    print(f'{out} ({len(names)} tracked public files)')


if __name__ == '__main__':
    main()

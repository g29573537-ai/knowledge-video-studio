"""Check tracked release files and optional Git history without printing secrets."""

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT_FILES = {
    'README.md', 'LICENSE', 'THIRD_PARTY.md', 'AGENTS.md', 'CONTRIBUTING.md',
    'CHANGELOG.md', 'pyproject.toml', '.gitignore', 'MANIFEST.in', '.env.example',
}
PUBLIC_DIRS = {'knowledge_video', 'narration_video', 'docs', 'tests', 'examples', 'scripts', '.github'}
PRIVATE_PARTS = {'.studio', '.runtime', '.venv', '__pycache__', '.git', 'auth.json', 'node_modules'}
MEDIA_SUFFIXES = {'.wav', '.m4a', '.mp4', '.mp3', '.flac', '.mov', '.pem', '.key', '.pkl', '.pt', '.safetensors'}
PATTERNS = {
    'credential-like value': re.compile(rb'(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'),
    'personal home path': re.compile(rb'/Users/(?!example/|your/|test/|name/)[A-Za-z0-9._-]+/'),
}


def public_path(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or any(x in PRIVATE_PARTS for x in p.parts):
        return False
    if p.suffix.lower() in MEDIA_SUFFIXES:
        return False
    if any(x == '.env' or x.startswith('.env.') for x in p.parts) and name != '.env.example':
        return False
    return name in ROOT_FILES or (len(p.parts) > 1 and p.parts[0] in PUBLIC_DIRS)


def findings(name, data):
    return [{'path': name, 'reason': label} for label, pattern in PATTERNS.items() if pattern.search(data)]


def tracked_files(root):
    raw = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root)
    return [x.decode() for x in raw.split(b'\0') if x]


def audit_worktree(root):
    errors = []
    names = tracked_files(root)
    for name in names:
        p = root / name
        if not public_path(name):
            errors.append({'path': name, 'reason': 'file outside public source allowlist'})
        elif p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
            errors.append({'path': name, 'reason': 'symlink or external target'})
        elif not p.is_file():
            errors.append({'path': name, 'reason': 'tracked file missing'})
        else:
            errors.extend(findings(name, p.read_bytes()))
    return names, errors


def audit_history(root):
    commits = subprocess.check_output(['git', 'rev-list', '--all'], cwd=root, text=True).split()
    errors, seen = [], set()
    for commit in commits:
        message = subprocess.check_output(['git', 'show', '-s', '--format=%B', commit], cwd=root)
        errors.extend(dict(x, commit=commit[:12]) for x in findings('(commit message)', message))
        tree = subprocess.check_output(['git', 'ls-tree', '-rz', commit], cwd=root)
        for row in tree.split(b'\0'):
            if not row:
                continue
            meta, filename = row.split(b'\t', 1)
            mode, kind, sha = meta.decode().split()
            name = filename.decode()
            if not public_path(name) or mode == '120000' or kind != 'blob':
                errors.append({'path': name, 'reason': 'non-public historical entry', 'commit': commit[:12]})
            if kind == 'blob' and sha not in seen:
                seen.add(sha)
                data = subprocess.check_output(['git', 'cat-file', 'blob', sha], cwd=root)
                errors.extend(dict(x, commit=commit[:12]) for x in findings(name, data))
    return len(commits), len(seen), errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    names, errors = audit_worktree(root)
    report = {'tracked_files': len(names), 'findings': errors}
    if args.history:
        commits, blobs, more = audit_history(root)
        report.update(commits=commits, unique_blobs=blobs)
        errors.extend(more)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()

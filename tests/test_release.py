import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from knowledge_video.models import JobRequest
from narration_video.core import load_project, parse_script
from scripts.audit_release import audit_history, audit_worktree
from scripts.package_source import package


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL)


def repo(tmp_path):
    git(tmp_path, 'init')
    (tmp_path / 'README.md').write_text('Public source\n')
    git(tmp_path, 'add', 'README.md')
    return tmp_path


def test_archive_ignores_untracked_nested_files(tmp_path):
    root = repo(tmp_path)
    (root / 'docs').mkdir()
    (root / 'docs/notes.json').write_text('{"private":true}')
    (root / '.studio').mkdir()
    (root / '.studio/recording.wav').write_bytes(b'private')
    (root / '.env').write_text('PRIVATE=true')
    target = root / 'dist/source.zip'
    assert package(root, target) == ['README.md']
    with zipfile.ZipFile(target) as z:
        assert z.namelist() == ['KnowledgeVideoStudio/README.md']


def test_tracked_secrets_reject_without_exposing_value(tmp_path):
    root = repo(tmp_path)
    value = 'sk-' + 'a' * 32
    (root / 'README.md').write_text(value)
    _, errors = audit_worktree(root)
    assert errors and value not in json.dumps(errors)
    with pytest.raises(ValueError, match='audit failed'):
        package(root, root / 'dist/source.zip')


def test_symlink_and_private_tracked_file_rejected(tmp_path):
    root = repo(tmp_path)
    (root / 'docs').mkdir()
    (root / 'docs/linked.md').symlink_to(root / 'README.md')
    (root / '.env').write_text('LOCAL=true')
    git(root, 'add', '.')
    _, errors = audit_worktree(root)
    assert {x['path'] for x in errors} == {'docs/linked.md', '.env'}


def test_removed_secret_still_detected_in_history(tmp_path):
    root = repo(tmp_path)
    git(root, 'config', 'user.name', 'Test')
    git(root, 'config', 'user.email', 'test@example.invalid')
    (root / 'README.md').write_text('sk-' + 'b' * 32)
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Initial')
    (root / 'README.md').write_text('Clean now')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Remove')
    assert audit_worktree(root)[1] == []
    count, _, errors = audit_history(root)
    assert count == 2 and any(x['reason'] == 'credential-like value' for x in errors)


def test_public_examples_match_real_parsers():
    root = Path(__file__).resolve().parents[1]
    for path in [root / 'examples/request.json', root / 'examples/external-request.json']:
        JobRequest.model_validate_json(path.read_text())
    config = load_project(root / 'examples/assistant/project.json')
    blocks = parse_script(config['script_path'].read_text())
    assert [b['id'] for b in blocks] == ['opening', 'change']
    assert set(config['cues']) == {'opening', 'change'}

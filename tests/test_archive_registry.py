"""Archive issuance records remain resolvable and can never be written into the live table."""
import json
import subprocess

import pytest

from repo_ledger.cli import main
from repo_ledger.config import LedgerConfig
from repo_ledger.registry import EntityRegistry

HEADER = '<!-- schema: 1.0 -->\n# Registry\n\n| id | name | status | parent | order | anchor | supersedes | date | legacy | note |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'


@pytest.fixture
def project(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / 'ledger.toml').write_text('[ledger]\nregistry_path="main.md"\narchive_registry_paths=["archive.md"]\n[types.DECISION]\nallowed_statuses=["ACTIVE","DORMANT","RETIRED","DRAFT"]\n[legacy_guard]\nenabled=false\n[index]\nout_dir="index"\n', encoding='utf-8')
    (tmp_path / 'main.md').write_text(HEADER + '| DECISION-1 | Current | ACTIVE | | 1 | evidence.md | DECISION-9 | 2026-10-10 | | |\n', encoding='utf-8')
    (tmp_path / 'archive.md').write_text(HEADER + '| DECISION-9 | Old | RETIRED | | 9 | evidence.md | | 2026-10-10 | OLD | |\n', encoding='utf-8')
    (tmp_path / 'evidence.md').write_text('DECISION-9 Old\n', encoding='utf-8')
    subprocess.run(['git', '-C', str(tmp_path), 'add', '.'], check=True)
    return tmp_path


def test_archived_lookup_reference_and_index(project, capsys):
    for token in ('DECISION-9', 'OLD'):
        assert main(['lookup', token, '--root', str(project), '--json']) == 0
        assert json.loads(capsys.readouterr().out)['id'] == 'DECISION-9'
    assert main(['check', '--root', str(project), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'PASS'
    assert main(['index', '--root', str(project)]) == 0
    assert all('DECISION-9' not in p.read_text(encoding='utf-8') for p in (project / 'index').glob('*.md'))


def test_mutations_keep_archived_bytes_and_highwater(project):
    cfg = LedgerConfig.load(project / 'ledger.toml')
    registry = EntityRegistry.load_configured(project, cfg)
    before = (project / 'archive.md').read_bytes()
    registry.update('DECISION-1', note='live change')
    assert registry.lookup('DECISION-9').name == 'Old'
    for expected in ('DECISION-10', 'DECISION-11'):
        assert registry.allocate('DECISION', 'New', status='ACTIVE', anchor='evidence.md').id == expected
        assert registry.sources[expected] == project / 'main.md'
    assert (project / 'archive.md').read_bytes() == before
    assert 'DECISION-9 | Old' not in (project / 'main.md').read_text(encoding='utf-8')


def test_archived_update_is_rejected(project, capsys):
    assert main(['update', 'DECISION-9', '--status', 'ACTIVE', '--root', str(project), '--json']) != 0
    assert 'ERR_ARCHIVE_READONLY' in capsys.readouterr().out


@pytest.mark.parametrize('replacement', [
    '| DECISION-1 | Duplicate | RETIRED | | 1 | evidence.md | | 2026-10-10 | | |\n',
    '| DECISION-9 | Old | RETIRED | | 9 | evidence.md | | 2026-10-10 | DECISION-1 | |\n',
    'corrupt registry\n',
])
def test_corrupt_or_collision_fails_closed(project, capsys, replacement):
    (project / 'archive.md').write_text(HEADER + replacement, encoding='utf-8')
    assert main(['lookup', 'DECISION-1', '--root', str(project), '--json']) != 0


def test_missing_archive_fails_closed(project):
    (project / 'archive.md').unlink()
    assert main(['lookup', 'DECISION-1', '--root', str(project), '--json']) != 0


def test_archive_anchor_failure_names_archive(project, capsys):
    (project / 'archive.md').write_text((project / 'archive.md').read_text(encoding='utf-8').replace('evidence.md', 'missing.md'), encoding='utf-8')
    assert main(['check', '--root', str(project), '--json']) != 0
    result = json.loads(capsys.readouterr().out)
    assert any('archive.md:6:1' in item['location'] for item in result['issues'])


def test_dormant_index_is_name_only_and_hidden_prose_fails(project, capsys):
    with (project / 'main.md').open('a', encoding='utf-8') as stream:
        stream.write('| DECISION-2 | Pause | DORMANT | | 2 | evidence.md | | 2026-10-10 | | secret note |\n')
    assert main(['index', '--root', str(project)]) == 0
    page = (project / 'index/DECISION.md').read_text(encoding='utf-8')
    assert '## DORMANT\n\n- DECISION-2 Pause' in page
    assert 'secret note' not in page
    (project / 'main.md').write_text((project / 'main.md').read_text(encoding='utf-8').replace('| | |\n', '| | see DECISION-9 |\n'), encoding='utf-8')
    assert main(['index', '--root', str(project), '--json']) != 0

"""Exercise startup without a Docker daemon; verify user configuration is preserved."""
import os
from pathlib import Path
import shutil
import subprocess


START = Path(__file__).resolve().parents[2] / 'scripts' / 'start'


def test_start_preserves_env_and_resolves_project_directory(tmp_path):
    project = tmp_path / 'project'
    (project / 'scripts').mkdir(parents=True)
    shutil.copy(START, project / 'scripts/start')
    config = b'SECRET=keep-this-value\nCUSTOM_SETTING=yes\n'
    (project / '.env').write_bytes(config)
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    docker = bindir / 'docker'
    docker.write_text('''#!/bin/sh
case "$1" in
  info) exit 0 ;;
  run) echo 999 ;;
  compose) echo "$PWD|$DOCKER_GID|$*" >> "$DOCKER_TEST_LOG" ;;
esac
''')
    docker.chmod(0o755)
    log = tmp_path / 'docker.log'
    env = dict(os.environ, PATH=f'{bindir}:'+os.environ['PATH'], DOCKER_TEST_LOG=str(log))
    env.pop('DOCKER_GID', None)
    subprocess.run(['bash', str(project / 'scripts/start')], cwd=tmp_path, env=env, check=True)
    assert (project / '.env').read_bytes() == config
    assert f'{project}|999|compose up -d' in log.read_text()
    assert (project / 'workspace').is_dir()

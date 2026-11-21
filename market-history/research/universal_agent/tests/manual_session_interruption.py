"""Pause a new research-only supervisor after index validation, then resume it separately."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from universal_agent import process_supervisor, research_runtime
from universal_agent.engine import write_state
from universal_agent.isolated_codex import PRIVATE_ROOT

GOAL = '한국 급락 전 변동성 신호를 워크포워드로 연구하고 지속 Queue에서 중단 복구하라.'


def start(directory):
    directory.mkdir(mode=0o700, exist_ok=False)
    research_runtime.submit(GOAL, directory)
    with (directory / 'trial.log').open('xb') as stream:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'worker', str(directory)],
            stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, start_new_session=True)
    return {'supervisor_pid': child.pid}


def worker(directory):
    original = process_supervisor.write_state
    def pause_after_validation(path, state):
        original(path, state)
        record = state.get('records', {}).get('validate_kr_index', {})
        if (path.name == 'state.json' and record.get('status') == 'VERIFIED' and
                state['records']['analyze_kr_crashes']['status'] == 'PENDING'):
            write_state(directory / 'interruption.json', dict(pid=os.getpid(), boot=state['goal_boot_id'],
                ticks=Path('/proc/self/stat').read_text().rsplit(') ', 1)[1].split()[19],
                monotonic=time.monotonic(), deadline=state['goal_deadline_monotonic'],
                checksum=record['checkpoint_sha256']))
            os.kill(os.getpid(), signal.SIGSTOP)
    process_supervisor.write_state = pause_after_validation
    return research_runtime.run(directory, max_jobs=1, max_seconds=300)


def resume(directory):
    saved = json.loads((directory / 'interruption.json').read_bytes())
    pid = saved['pid']
    proc = Path('/proc') / str(pid)
    args = (proc / 'cmdline').read_bytes().split(b'\0')[1:4]
    stat = (proc / 'stat').read_text().rsplit(') ', 1)[1].split()
    if (proc.stat().st_uid != os.getuid() or saved['boot'] != process_supervisor._boot_id()
            or args != [os.fsencode(Path(__file__).resolve()), b'worker', os.fsencode(directory)]
            or stat[0] != 'T' or stat[19] != saved['ticks']):
        raise ValueError('Interrupted supervisor identity changed')
    os.kill(pid, signal.SIGKILL)
    return {'resumed_pid': research_runtime.launch(directory, max_jobs=1, max_seconds=300)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('start', 'worker', 'resume'))
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.parent != PRIVATE_ROOT or args.directory.is_symlink():
        parser.error('Use a new immediate child of the private worktree directory')
    print(json.dumps({'start': start, 'worker': worker, 'resume': resume}[args.action](directory)))

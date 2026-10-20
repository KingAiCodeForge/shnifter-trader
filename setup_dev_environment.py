"""Install this project from any directory without shell expansion or tree edits."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extras', choices=('dev', 'market,api,gui,dev'), default='dev')
    args = parser.parse_args(argv)
    command = [sys.executable, '-m', 'pip', 'install', '-e', f'{ROOT}[{args.extras}]']
    try:
        subprocess.run(command, cwd=ROOT, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f'Shnifter setup failed: {exc}', file=sys.stderr)
        return 1
    print('Shnifter research environment installed; GUI prototypes remain experimental.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

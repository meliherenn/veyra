"""Offline regression suite; this command never moves or clicks the real mouse."""
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    raise SystemExit(subprocess.call([sys.executable,'-m','pytest','-q',str(Path(__file__).parent/'tests')]))

"""Local regression for root-harness imports; no root, VM or packet integration."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class IntegrationBytecodeTests(unittest.TestCase):
    def test_harness_disables_import_bytecode_with_clean_environment(self):
        scripts = Path(__file__).resolve().parent
        # Execute the actual harness prologue before its isolated-Linux guard.
        # No namespace setup or privileged command is executed by this test.
        prologue = (scripts / 'linux-integration.sh').read_text().split(
            'if [[ ${UDP_ROUTER_ISOLATED_LINUX:-} != YES ]]; then', 1)[0]
        env = os.environ.copy()
        env.pop('PYTHONDONTWRITEBYTECODE', None)  # Model sudo stripping it.
        env.pop('PYTHONPYCACHEPREFIX', None)
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('extended.py', 'traffic.py'):
                shutil.copyfile(scripts / name, Path(tmp) / name)
            subprocess.run(
                ['bash', '-c', prologue + '\nexec "$1" -c "$2"',
                 'bytecode-regression', sys.executable,
                 'import sys; import extended, traffic; assert sys.dont_write_bytecode'],
                cwd=tmp, env=env, check=True, capture_output=True, text=True)
            self.assertFalse(list(Path(tmp).rglob('__pycache__')))
            self.assertFalse(list(Path(tmp).rglob('*.pyc')))


if __name__ == '__main__':
    unittest.main()

import subprocess
import sys
import unittest
from kis_hl.execution_lock import account_lock


class LockTests(unittest.TestCase):
    def test_nested_owner_allowed_and_other_process_rejected(self):
        with account_lock('test-network', 'test-account'):
            with account_lock('test-network', 'test-account'):
                pass
            result = subprocess.run([sys.executable, '-c',
                "from kis_hl.execution_lock import account_lock\nwith account_lock('test-network','test-account'): pass"],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('another execution owner', result.stderr)
        with account_lock('test-network', 'test-account'):
            pass

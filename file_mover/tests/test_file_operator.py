import unittest
import os
import hashlib
from pathlib import Path
from file_mover.config import load_config
from file_mover.file_operator import FileOperator

class FileOperatorTests(unittest.TestCase):
    def test_compute_checksum(self):
        content = b"test content"
        # Create a temporary file.
        tmp_file = Path("temp_test_file.txt")
        try:
            with tmp_file.open("wb") as f:
                f.write(content)
            operator = FileOperator(load_config())
            checksum = operator._compute_checksum(tmp_file)
            expected = hashlib.sha256(content).hexdigest()
            self.assertEqual(checksum, expected)
        finally:
            if tmp_file.exists():
                os.remove(tmp_file)

if __name__ == "__main__":
    unittest.main()

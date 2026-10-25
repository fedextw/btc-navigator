import tempfile
import unittest
from agent_single_instance import research_lock, AlreadyRunning


class SingleInstanceTests(unittest.TestCase):
    def test_second_instance_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with research_lock(directory):
                with self.assertRaises(AlreadyRunning):
                    with research_lock(directory):
                        pass

    def test_released_after_normal_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            with research_lock(directory):
                pass
            with research_lock(directory):
                pass

    def test_released_after_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                with research_lock(directory):
                    raise ValueError("test")
            with research_lock(directory):
                pass


if __name__ == "__main__":
    unittest.main()

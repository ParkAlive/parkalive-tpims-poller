from __future__ import annotations

import unittest
from pathlib import Path


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = (
            Path(__file__).parents[1] / ".github" / "workflows" / "poll.yml"
        ).read_text()

    def test_each_poll_has_a_hard_safety_window(self) -> None:
        self.assertIn("timeout 600s python poll_tpims.py", self.workflow)
        self.assertIn("timeout 300s python poll_tpims.py", self.workflow)

    def test_controlled_run_does_not_restart_chain(self) -> None:
        self.assertIn("default: once", self.workflow)
        self.assertIn("inputs.mode == 'continuous'", self.workflow)
        self.assertIn("-f mode=continuous", self.workflow)


if __name__ == "__main__":
    unittest.main()

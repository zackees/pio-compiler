"""Integration tests package marker."""

import time
import unittest
from typing import Optional


class TimedTestCase(unittest.TestCase):
    """Base test case class with duration tracking.

    This class provides timing functionality for unit tests,
    automatically tracking and reporting the duration of each test method.
    """

    def setUp(self) -> None:
        """Set up timing for the test."""
        super().setUp()
        self._test_start_time: Optional[float] = None
        self._test_start_time = time.perf_counter()

    def tearDown(self) -> None:
        """Clean up and report test duration."""
        super().tearDown()
        if self._test_start_time is not None:
            duration = time.perf_counter() - self._test_start_time
            test_name = self._testMethodName
            class_name = self.__class__.__name__
            # Use stderr to ensure output is visible even with pytest output capturing
            import sys

            print(
                f"[DURATION] {class_name}.{test_name}: {duration:.4f}s", file=sys.stderr
            )

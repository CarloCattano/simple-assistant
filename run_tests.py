#!/usr/bin/env python3
"""Helper script to run the project's unit tests with optional color output."""

import argparse
import os
import sys
import unittest
from pathlib import Path
from typing import Optional

DEFAULT_PATTERN = "test*.py"


def _reexec_in_venv_if_needed() -> None:
    """Re-exec this script under .venv/bin/python if available.

    This lets you call `python run_tests.py` from the repo root without
    manually activating the virtualenv first, while avoiding infinite
    recursion when already running inside the venv.
    """

    workspace = Path(__file__).resolve().parent
    venv_python = workspace / ".venv" / "bin" / "python"

    # Only re-exec if the venv interpreter exists and we're not already
    # using it.
    if not venv_python.is_file():
        return

    current = Path(sys.executable).resolve()
    if current == venv_python.resolve():
        return

    os.execv(str(venv_python), [str(venv_python), *sys.argv])


def _supports_color(stream) -> bool:
    return stream.isatty() and os.environ.get("NO_COLOR") is None


class ColoredTextTestResult(unittest.TextTestResult):
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RESET = "\033[0m"

    def __init__(self, stream, descriptions, verbosity, enable_color: bool = True):
        super().__init__(stream, descriptions, verbosity)
        self._enable_color = enable_color

    def _colorize(self, status: str) -> str:
        if not self._enable_color:
            return status

        lowered = status.lower()
        if lowered.startswith("ok"):
            color = self.GREEN
        elif lowered.startswith("skipped"):
            color = self.YELLOW
        elif lowered.startswith("expected failure"):
            color = self.CYAN
        elif lowered.startswith("unexpected success"):
            color = self.CYAN
        elif lowered.startswith("fail") or lowered.startswith("error"):
            color = self.RED
        else:
            return status

        return f"{color}{status}{self.RESET}"

    def _write_status(self, test, status):  # type: ignore[override]
        super()._write_status(test, self._colorize(status))


class ColoredTextTestRunner(unittest.TextTestRunner):
    resultclass = ColoredTextTestResult

    def __init__(self, *args, enable_color: Optional[bool] = None, **kwargs):
        if "stream" not in kwargs:
            kwargs["stream"] = sys.stdout
        self._enable_color = (
            _supports_color(kwargs["stream"]) if enable_color is None else enable_color
        )
        super().__init__(*args, **kwargs)

    def _makeResult(self):  # type: ignore[override]
        return self.resultclass(self.stream, self.descriptions, self.verbosity)


def run_all_tests(
    pattern: str = DEFAULT_PATTERN, enable_color: Optional[bool] = None
) -> int:
    """Discover and execute tests, returning an appropriate exit code."""
    workspace = Path(__file__).resolve().parent
    tests_dir = workspace / "tests"
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(tests_dir), pattern=pattern
    )

    runner = ColoredTextTestRunner(verbosity=2, enable_color=enable_color)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def main() -> None:
    # Prefer the project-local virtual environment interpreter when present.
    _reexec_in_venv_if_needed()

    parser = argparse.ArgumentParser(description="Run the project's unit tests.")
    parser.add_argument(
        "-p",
        "--pattern",
        default=DEFAULT_PATTERN,
        help="Glob pattern for test files (default: %(default)s)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color codes in the test output.",
    )
    args = parser.parse_args()

    enable_color = None if not args.no_color else False
    exit_code = run_all_tests(args.pattern, enable_color=enable_color)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

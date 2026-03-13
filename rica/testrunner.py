import subprocess
import re
from pathlib import Path
from loguru import logger
from typing import Dict, List, Optional


class TestRunner:
    """Automatic test runner for Rica projects."""

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)

    def find_tests(
        self,
        snapshot: "CodebaseSnapshot",
    ) -> List[str]:
        """
        Returns list of test file rel paths
        found in snapshot or on disk.
        Looks for:
          - files under tests/ directory
          - files matching test_*.py or *_test.py
        """
        found = []

        # Check snapshot files first
        for rel_path in snapshot.files:
            p = Path(rel_path)
            if (
                p.parts[0] == 'tests'
                or p.name.startswith('test_')
                or p.name.endswith('_test.py')
            ):
                found.append(rel_path)

        # Also scan disk in case tests weren't
        # ranked into snapshot
        if self.project_dir.exists():
            for pattern in (
                'tests/**/test_*.py',
                'tests/**/*_test.py',
                'test_*.py',
                '*_test.py',
            ):
                for f in self.project_dir.glob(
                    pattern
                ):
                    rel = str(
                        f.relative_to(
                            self.project_dir
                        )
                    )
                    if rel not in found:
                        found.append(rel)

        return found

    def run(self) -> Dict:
        """
        Runs pytest in project_dir.
        Returns:
          {
            success: bool,
            output: str,       # full output
            failed: int,       # failed count
            passed: int,       # passed count
            summary: str,      # last line
          }
        """
        try:
            result = subprocess.run(
                [
                    'python', '-m', 'pytest',
                    '--tb=short',
                    '--no-header',
                    '-q',
                ],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = (
                result.stdout
                + result.stderr
            ).strip()
            success = result.returncode == 0

            # Parse counts from pytest output
            # e.g. "2 failed, 5 passed in 0.3s"
            failed = 0
            passed = 0
            summary = ""
            for line in output.splitlines():
                if 'failed' in line or \
                        'passed' in line or \
                        'error' in line.lower():
                    summary = line.strip()
                import re
                m = re.search(
                    r'(\d+) failed', line
                )
                if m:
                    failed = int(m.group(1))
                m = re.search(
                    r'(\d+) passed', line
                )
                if m:
                    passed = int(m.group(1))

            logger.info(
                f"[testrunner] pytest: "
                f"{summary or 'no summary'}"
            )
            return {
                'success': success,
                'output': output,
                'failed': failed,
                'passed': passed,
                'summary': summary,
            }

        except subprocess.TimeoutExpired:
            logger.error(
                "[testrunner] pytest timed out"
            )
            return {
                'success': False,
                'output': 'pytest timed out',
                'failed': -1,
                'passed': 0,
                'summary': 'timeout',
            }
        except Exception as e:
            logger.error(
                f"[testrunner] pytest error: {e}"
            )
            return {
                'success': False,
                'output': str(e),
                'failed': -1,
                'passed': 0,
                'summary': str(e),
            }

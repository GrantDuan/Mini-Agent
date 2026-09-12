"""
Agent Evaluation Framework.

Evals are regression tests for agents.
An eval suite is just a Python file that runs your agent and asserts things didn't break.

This module provides the RESULT MODEL and REPORTING shared by all suites:
- EvalResult: outcome of a single eval case
- EvalSuiteResult: pass/fail counts and details for one suite
- print_eval_report: formatted report across suites

The suites themselves live in run.py - they drive the REAL agent
(Agent.run() + transcript inspection) rather than isolated prompts.
"""

from typing import Any
from dataclasses import dataclass, field


@dataclass
class EvalResult:
    """Result of a single eval case."""
    passed: bool
    input: str
    expected: Any = None
    actual: Any = None
    error: str | None = None


@dataclass
class EvalSuiteResult:
    """Result of running an eval suite."""
    name: str
    passed: int = 0
    failed: int = 0
    results: list[EvalResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0

    def add_result(self, result: EvalResult):
        """Add a result and update counts."""
        self.results.append(result)
        if result.passed:
            self.passed += 1
        else:
            self.failed += 1

    def summary(self) -> str:
        """Generate a human-readable summary."""
        status = "✓ PASSED" if self.failed == 0 else "✗ FAILED"
        return f"{self.name}: {status} ({self.passed}/{self.total})"


def print_eval_report(results: list[EvalSuiteResult]):
    """
    Print a formatted eval report.

    Args:
        results: List of EvalSuiteResults to report
    """
    print("\n" + "="*50)
    print("EVAL REPORT")
    print("="*50)

    total_passed = 0
    total_failed = 0

    for suite in results:
        print(f"\n{suite.summary()}")

        # Show failures
        for result in suite.results:
            if not result.passed:
                print(f"  ✗ Input: {result.input[:50]}...")
                if result.expected:
                    print(f"    Expected: {result.expected}")
                if result.actual:
                    print(f"    Actual: {result.actual}")
                if result.error:
                    print(f"    Error: {result.error}")

        total_passed += suite.passed
        total_failed += suite.failed

    print("\n" + "-"*50)
    overall = "✓ ALL PASSED" if total_failed == 0 else f"✗ {total_failed} FAILED"
    print(f"Overall: {overall} ({total_passed}/{total_passed + total_failed})")
    print("="*50)

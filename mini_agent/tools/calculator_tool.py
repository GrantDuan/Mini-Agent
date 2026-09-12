"""Calculator Tool - Basic arithmetic operations.

This tool allows the agent to:
- Perform add, subtract, multiply, divide operations
- Avoid relying on the LLM for arithmetic (LLMs are unreliable at math)
"""

from typing import Any

from .base import Tool, ToolResult


class CalculatorTool(Tool):
    """Tool for basic arithmetic: add, subtract, multiply, divide."""

    OPERATIONS = {
        "add": lambda a, b: a + b,
        "subtract": lambda a, b: a - b,
        "multiply": lambda a, b: a * b,
        "divide": lambda a, b: a / b if b != 0 else None,
    }

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return (
            "Evaluate a basic arithmetic expression. "
            "Provide two numbers (a, b) and an operation "
            "('add', 'subtract', 'multiply', or 'divide')."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": list(self.OPERATIONS.keys()),
                    "description": "The arithmetic operation to perform",
                },
                "a": {"type": "number", "description": "First operand"},
                "b": {"type": "number", "description": "Second operand"},
            },
            "required": ["operation", "a", "b"],
        }

    async def execute(self, operation: str, a: float, b: float) -> ToolResult:
        """Execute the arithmetic operation.

        Args:
            operation: One of add/subtract/multiply/divide
            a: First operand
            b: Second operand

        Returns:
            ToolResult with the computation result
        """
        op = self.OPERATIONS.get(operation)
        if op is None:
            return ToolResult(
                success=False,
                content="",
                error=f"Unknown operation: {operation}. Must be one of {list(self.OPERATIONS.keys())}",
            )

        result = op(a, b)
        if result is None:
            return ToolResult(success=False, content="", error="Division by zero")

        # Show integers without trailing .0
        if isinstance(result, float) and result.is_integer():
            result = int(result)

        return ToolResult(success=True, content=f"{a} {operation} {b} = {result}")

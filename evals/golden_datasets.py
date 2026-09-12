"""
Golden Datasets for Agent Evals.

Golden datasets are known-good test cases that must always pass.
They are version controlled alongside prompts - when you change a prompt,
you run the golden dataset to make sure you didn't break anything.

Why "golden"?
- These are your source of truth
- If a golden case fails, the agent is broken (not the test)
- They cover both happy paths AND edge cases
"""

# ============================================================
# STRUCTURED OUTPUT GOLDEN DATASET
# Tests: JSON parsing, schema compliance
# 
# NOTE: Schemas use multi-line format with examples for clarity.
# Single-line schemas often confuse models.
# ============================================================

STRUCTURED_OUTPUT_GOLDEN = [
    # Happy path: standard question
    {
        "input": "Explain quantum computing in one sentence",
        "schema": """{
  "topic": "the topic name as a string",
  "difficulty": "beginner" or "intermediate" or "advanced"
}

Example: {"topic": "machine learning", "difficulty": "intermediate"}""",
        "must_have_fields": ["topic", "difficulty"]
    },
    # Happy path: simple question
    {
        "input": "What is Python in one sentence?",
        "schema": """{
  "topic": "the topic name as a string",
  "difficulty": "beginner" or "intermediate" or "advanced"
}

Example: {"topic": "web development", "difficulty": "beginner"}""",
        "must_have_fields": ["topic", "difficulty"]
    },
    # Edge case: question with numbers
    {
        "input": "What is the significance of 42?",
        "schema": """{
  "answer": "your answer as a string"
}

Example: {"answer": "It is the meaning of life"}""",
        "must_have_fields": ["answer"]
    },
    # Edge case: question with special characters
    {
        "input": "What does hello world mean in programming?",
        "schema": """{
  "explanation": "your explanation as a string"
}

Example: {"explanation": "It is a simple test program"}""",
        "must_have_fields": ["explanation"]
    },
]


# ============================================================
# TOOL CALL GOLDEN DATASET  
# Tests: Correct tool selection, valid arguments
# ============================================================

TOOL_CALL_GOLDEN = [
    # Happy path: multiplication
    {
        "input": "What is 42 * 7?",
        "expected_tool": "calculator",
        "expected_args": {"operation": "multiply"}
    },
    # Happy path: addition
    {
        "input": "Calculate 100 + 50",
        "expected_tool": "calculator",
        "expected_args": {"operation": "add"}
    },
    # Happy path: division
    {
        "input": "What is 100 / 5?",
        "expected_tool": "calculator",
        "expected_args": {"operation": "divide"}
    },
    # Happy path: subtraction
    {
        "input": "What's 50 minus 25?",
        "expected_tool": "calculator",
        "expected_args": {"operation": "subtract"}
    },
    # Edge case: word problem
    {
        "input": "If I have 15 apples and buy 27 more, how many do I have?",
        "expected_tool": "calculator",
        "expected_args": {"operation": "add"}
    },
]


# ============================================================
# DECISION GOLDEN DATASET
# Tests: Correct routing based on input
# ============================================================

DECISION_GOLDEN = [
    # Clear summarization request
    {
        "input": "Can you summarize this article for me?",
        "choices": ["answer_question", "summarize_text", "translate"],
        "expected": "summarize_text"
    },
    # Clear translation request
    {
        "input": "Translate 'hello' to Spanish",
        "choices": ["answer_question", "summarize_text", "translate"],
        "expected": "translate"
    },
    # Clear question
    {
        "input": "What is the capital of France?",
        "choices": ["answer_question", "summarize_text", "translate"],
        "expected": "answer_question"
    },
    # Calculate vs answer
    {
        "input": "What is 5 + 5?",
        "choices": ["answer_question", "calculate", "search"],
        "expected": "calculate"
    },
]


# ============================================================
# MEMORY GOLDEN DATASET
# Tests: Store → Retrieve cycle
# ============================================================

MEMORY_GOLDEN = [
    # Name storage and recall
    {
        "store_input": "My name is Alice",
        "query_input": "What's my name?",
        "expected_in_response": "Alice"
    },
    # Preference storage and recall
    {
        "store_input": "I prefer dark mode",
        "query_input": "What's my preference for display mode?",
        "expected_in_response": "dark"
    },
    # Location storage and recall
    {
        "store_input": "I live in New York",
        "query_input": "Where do I live?",
        "expected_in_response": "New York"
    },
]


# ============================================================
# EDGE CASES GOLDEN DATASET
# Tests: Boundary conditions that often break prompts
# ============================================================

EDGE_CASES_GOLDEN = {
    "empty_input": {
        "structured": {
            "input": "Respond with a greeting",
            "schema": '{"response": "your response"}\n\nExample: {"response": "Hello!"}',
            "must_have_fields": ["response"]
        }
    },
    "very_long_input": {
        "structured": {
            "input": "Summarize: " + "very " * 20 + "complex topic",
            "schema": '{"summary": "brief summary"}\n\nExample: {"summary": "A complex topic"}',
            "must_have_fields": ["summary"]
        }
    },
    "unicode_input": {
        "structured": {
            "input": "What does hello mean in Chinese?",
            "schema": '{"translation": "the translation"}\n\nExample: {"translation": "你好"}',
            "must_have_fields": ["translation"]
        }
    },
    "json_in_input": {
        "structured": {
            "input": "What format is this: key value pairs?",
            "schema": '{"parsed": "your answer"}\n\nExample: {"parsed": "dictionary"}',
            "must_have_fields": ["parsed"]
        }
    },
}

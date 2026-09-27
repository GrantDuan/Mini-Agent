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
# REAL AGENT TASKS GOLDEN DATASET
# Tests: multi-step work against a real workspace
#
# The suites above check ONE thing each in ONE step (did it call the
# calculator? did it emit valid JSON?). That is prompt testing, not
# agent testing. These cases are different in kind:
#
#   - multi-step      : read -> compute -> write, not a single call
#   - result-driven   : assert on OUTCOMES (file contents, correct
#                       answers), not merely "the right tool was called"
#                       - an agent can call read_file and then hallucinate
#   - real tools      : read_file / write_file / edit_file / bash, the
#                       tools a coding agent actually lives on
#   - failure paths   : missing files, failing commands - the agent must
#                       recover or report honestly, never fabricate success
#   - restraint       : sometimes the correct answer is NO tool call
#
# Each case runs in a clean workspace (see `setup`) so cases never leak
# into one another.
#
# Schema:
#   name    : stable identifier, shown in failures
#   task    : the user message handed to the agent
#   setup   : {relative_path: content} files created before the run
#   expect  : assertions, all must hold
#             reply_contains / reply_contains_any / reply_excludes
#             tools_called / tools_forbidden / no_tools
#             files (exact, whitespace-normalised) / file_contains / file_absent
#             max_steps
# ============================================================

REAL_AGENT_GOLDEN = [
    # ---- 1. Multi-step, and the ANSWER must be right -------------------
    # The classic agent loop: read a file, compute something, write the
    # result. Asserting on count.txt (not on "read_file was called")
    # is the point - an agent can call the tool and still get the number
    # wrong.
    {
        "name": "read_compute_write",
        "task": (
            "Read the file `data.txt` in the workspace, count how many lines "
            "contain the word `error`, and write ONLY that number into "
            "`count.txt` (nothing else in the file)."
        ),
        "setup": {
            "data.txt": (
                "error: disk full\n"
                "info: started\n"
                "error: timeout\n"
                "info: retrying\n"
                "done\n"
            ),
        },
        "expect": {
            "files": {"count.txt": "2"},
            "tools_called": ["read_file", "write_file"],
            "reply_contains": ["2"],
        },
    },

    # ---- 2. Surgical edit, not a rewrite ------------------------------
    # Real agent work is mostly MODIFYING existing files. The neighbours
    # of the changed line must survive - that is what separates edit_file
    # from a careless write_file.
    {
        "name": "edit_surgical",
        "task": (
            "In `config.txt`, change the value of `timeout` from 30 to 60. "
            "Change nothing else in the file."
        ),
        "setup": {
            "config.txt": "host: localhost\ntimeout: 30\nretries: 3\n",
        },
        # Exact match: catches both "didn't change it" and "rewrote the
        # whole file". file_contains alone would pass a careless rewrite.
        "expect": {
            "files": {"config.txt": "host: localhost\ntimeout: 60\nretries: 3"},
        },
    },

    # ---- 3. Restraint: the right move is NO tool ----------------------
    # Over-eager tool use is a real failure mode and no existing case
    # catches it. A pure-knowledge question should be answered directly
    # rather than triggering a workspace read.
    {
        "name": "no_tool_needed",
        "task": (
            "Answer directly, without using any tools: what is the capital "
            "of France?"
        ),
        "expect": {
            "no_tools": True,
            "reply_contains": ["paris"],
            "max_steps": 2,
        },
    },

    # ---- 4. Recovery from a failing tool ------------------------------
    # reading a file that isn't there is the single most common tool
    # error. The agent must absorb the error and complete the task
    # anyway, not give up and not pretend it succeeded.
    {
        "name": "recover_from_missing_file",
        "task": (
            "Read `missing.txt`. If it does not exist yet, create it with "
            "exactly the content `created by agent`."
        ),
        "expect": {
            "files": {"missing.txt": "created by agent"},
            "reply_contains": ["created"],
        },
    },

    # ---- 5. Listing the workspace (bash, correct filtering) -----------
    {
        "name": "list_and_filter",
        "task": (
            "Tell me the names of all files in the workspace that end "
            "in `.md`."
        ),
        "setup": {
            "alpha.md": "# Alpha\n",
            "beta.txt": "beta\n",
            "gamma.md": "# Gamma\n",
        },
        "expect": {
            "tools_called": ["bash"],
            "reply_contains": ["alpha.md", "gamma.md"],
            "reply_excludes": ["beta.txt"],
        },
    },

    # ---- 6. Exploration when the exact filename is unknown ------------
    # The user gives a hint, not a path. The agent has to go look.
    {
        "name": "discover_by_prefix",
        "task": (
            "There is a file in the workspace whose name starts with "
            "`report`. Read it and tell me the value of the `status` field."
        ),
        "setup": {
            "report_2026.txt": "owner: ops\nstatus: ready\nregion: apac\n",
            "notes.txt": "unrelated\n",
        },
        "expect": {
            "tools_called": ["read_file"],
            "reply_contains": ["ready"],
        },
    },

    # ---- 7. Write code, then RUN it ----------------------------------
    # The write -> execute -> report loop is what makes a coding agent a
    # coding agent. Both halves are asserted: the file must exist AND
    # the observed output must be right.
    {
        "name": "write_then_execute",
        "task": (
            "Create `hello.py` in the workspace containing a function "
            "`greet(name)` that returns the string `Hello, <name>!`. "
            "Then run a command to print `greet('World')` and show me the output."
        ),
        "expect": {
            "file_contains": {"hello.py": ["def greet"]},
            "tools_called": ["write_file", "bash"],
            "reply_contains": ["Hello, World!"],
            "max_steps": 12,
        },
    },

    # ---- 8. Honest failure reporting ----------------------------------
    # A command that cannot work. The agent must report the failure
    # rather than claim success - fabricated success is one of the most
    # damaging agent behaviours and nothing else here tests for it.
    {
        "name": "honest_failure",
        "task": "Run `python does_not_exist.py` in the workspace and tell me what happened.",
        "expect": {
            "tools_called": ["bash"],
            "reply_contains_any": [
                "no such file",
                "not found",
                "does not exist",
                "doesn't exist",
                "cannot find",
                "can't open",
                "can't find",
                "error",
            ],
            # Fabricated success is the failure this case exists to catch.
            "reply_excludes": ["successfully ran", "ran successfully"],
        },
    },

    # ---- 9. Aggregation across several files --------------------------
    # Requires reading more than one file and combining what was found -
    # a level above "read the file I named".
    {
        "name": "search_across_files",
        # The comma-separated constraint is what makes reply_excludes
        # fair. Without it a GOOD answer says "a.txt and c.txt match;
        # b.txt does not" - and check_case would fail it for mentioning
        # the file it correctly ruled out.
        "task": (
            "Find every file in the workspace containing the word "
            "`banana`, and reply with just their filenames, comma-separated."
        ),
        "setup": {
            "a.txt": "apple\nbanana\n",
            "b.txt": "cherry\ndate\n",
            "c.txt": "banana split\n",
        },
        "expect": {
            "reply_contains": ["a.txt", "c.txt"],
            "reply_excludes": ["b.txt"],
        },
    },

    # ---- 10. End-to-end data task -------------------------------------
    # The shape of real work: a data file in, an aggregated result out.
    # Totals differ per product, so a wrong grouping cannot pass by luck.
    {
        "name": "data_pipeline",
        "task": (
            "Read `sales.csv` and compute the total `amount` per product. "
            "Write the result to `summary.txt`, one line per product in the "
            "exact format `product: total`."
        ),
        "setup": {
            "sales.csv": (
                "date,product,amount\n"
                "2026-01-01,widget,10\n"
                "2026-01-02,gadget,30\n"
                "2026-01-03,widget,15\n"
            ),
        },
        # Assert the RESULT only. The agent may reach it with write_file
        # or with a bash pipeline - both are legitimate, and pinning the
        # method would fail a correct answer (it did, on the first run).
        "expect": {
            "file_contains": {"summary.txt": ["widget: 25", "gadget: 30"]},
            "max_steps": 12,
        },
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

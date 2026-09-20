"""Memory constants

Shared definitions for the MCP memory server integration:
tool name set, system prompt policy text, and the policy heading
used to detect whether the policy was injected.
"""

# Tool names exposed by @modelcontextprotocol/server-memory.
# MCP tools are registered with their raw server names (no namespace prefix),
# so we identify memory tools by matching against this set.
MEMORY_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "create_entities",
        "create_relations",
        "add_observations",
        "delete_observations",
        "delete_entities",
        "delete_relations",
        "read_graph",
        "search_nodes",
        "open_nodes",
    }
)

# Heading used both in the policy text and to detect injection
MEMORY_POLICY_HEADING = "## Memory 使用策略"

MEMORY_POLICY_TEXT = f"""{MEMORY_POLICY_HEADING}
你可以使用记忆 MCP 工具（create_entities、create_relations、add_observations、delete_observations、delete_entities、delete_relations、read_graph、search_nodes、open_nodes）进行跨会话长期记忆。
1. 任务/对话开始：先用 search_nodes（按任务关键词）或 read_graph 检索相关记忆再工作。
2. 主动保存：用户透露重要事实、偏好、决策、计划或项目背景时，用 create_entities（类型可用 person/project/preference/decision/fact）或 add_observations 追加；用户明确要求"记住"时必须保存。
3. 引用过去：用户提到"上次/之前/我们说过"等，先 search_nodes 检索，不要凭空猜测或直接反问用户。
4. 何时不用：临时性、一次性的琐碎操作不保存；不保存敏感凭据（密码、API key）；检索无结果时直接继续任务，不要反复重试或向用户长篇解释。"""


def find_memory_tools(tool_names) -> list[str]:
    """Return the subset of given tool names that belong to the memory server.

    Args:
        tool_names: Iterable of tool names (e.g. from loaded Tool objects).

    Returns:
        Sorted list of memory tool names found.
    """
    return sorted(set(tool_names) & MEMORY_TOOL_NAMES)

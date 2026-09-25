"""
Mini Agent - Interactive Runtime Example

Usage:
    mini-agent [--workspace DIR] [--task TASK]

Examples:
    mini-agent                              # Use current directory as workspace (interactive mode)
    mini-agent --workspace /path/to/dir     # Use specific workspace directory (interactive mode)
    mini-agent --task "create a file"       # Execute a task non-interactively
"""

import argparse
import asyncio
import platform
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import List

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from mini_agent import LLMClient
from mini_agent.agent import Agent
from mini_agent.config import Config
from mini_agent.schema import LLMProvider
from mini_agent.stream_display import StreamingDisplay
from mini_agent.tools.base import Tool
from mini_agent.tools.bash_tool import BashKillTool, BashOutputTool, BashTool
from mini_agent.tools.file_tools import EditTool, ReadTool, WriteTool
from mini_agent.tools.mcp_loader import cleanup_mcp_connections, load_mcp_tools_async, set_mcp_timeout_config
from mini_agent.tools.note_tool import RecallNoteTool, SessionNoteTool
from mini_agent.tools.skill_tool import create_skill_tools
from mini_agent.utils import calculate_display_width


# ANSI color codes
class Colors:
    """Terminal color definitions"""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background colors
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"


def get_log_directory() -> Path:
    """Get the log directory path."""
    return Path.home() / ".mini-agent" / "log"


def show_log_directory(open_file_manager: bool = True) -> None:
    """Show log directory contents and optionally open file manager.

    Args:
        open_file_manager: Whether to open the system file manager
    """
    log_dir = get_log_directory()

    print(f"\n{Colors.BRIGHT_CYAN}📁 Log Directory: {log_dir}{Colors.RESET}")

    if not log_dir.exists() or not log_dir.is_dir():
        print(f"{Colors.RED}Log directory does not exist: {log_dir}{Colors.RESET}\n")
        return

    log_files = list(log_dir.glob("*.log"))

    if not log_files:
        print(f"{Colors.YELLOW}No log files found in directory.{Colors.RESET}\n")
        return

    # Sort by modification time (newest first)
    log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_YELLOW}Available Log Files (newest first):{Colors.RESET}")

    for i, log_file in enumerate(log_files[:10], 1):
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        size = log_file.stat().st_size
        size_str = f"{size:,}" if size < 1024 else f"{size / 1024:.1f}K"
        print(f"  {Colors.GREEN}{i:2d}.{Colors.RESET} {Colors.BRIGHT_WHITE}{log_file.name}{Colors.RESET}")
        print(f"      {Colors.DIM}Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}, Size: {size_str}{Colors.RESET}")

    if len(log_files) > 10:
        print(f"  {Colors.DIM}... and {len(log_files) - 10} more files{Colors.RESET}")

    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}")

    # Open file manager
    if open_file_manager:
        _open_directory_in_file_manager(log_dir)

    print()


def _open_directory_in_file_manager(directory: Path) -> None:
    """Open directory in system file manager (cross-platform)."""
    system = platform.system()

    try:
        if system == "Darwin":
            subprocess.run(["open", str(directory)], check=False)
        elif system == "Windows":
            subprocess.run(["explorer", str(directory)], check=False)
        elif system == "Linux":
            subprocess.run(["xdg-open", str(directory)], check=False)
    except FileNotFoundError:
        print(f"{Colors.YELLOW}Could not open file manager. Please navigate manually.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.YELLOW}Error opening file manager: {e}{Colors.RESET}")


def read_log_file(filename: str) -> None:
    """Read and display a specific log file.

    Args:
        filename: The log filename to read
    """
    log_dir = get_log_directory()
    log_file = log_dir / filename

    if not log_file.exists() or not log_file.is_file():
        print(f"\n{Colors.RED}❌ Log file not found: {log_file}{Colors.RESET}\n")
        return

    print(f"\n{Colors.BRIGHT_CYAN}📄 Reading: {log_file}{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 80}{Colors.RESET}")

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        print(content)
        print(f"{Colors.DIM}{'─' * 80}{Colors.RESET}")
        print(f"\n{Colors.GREEN}✅ End of file{Colors.RESET}\n")
    except Exception as e:
        print(f"\n{Colors.RED}❌ Error reading file: {e}{Colors.RESET}\n")


def print_banner():
    """Print welcome banner with proper alignment"""
    BOX_WIDTH = 58
    banner_text = f"{Colors.BOLD}🤖 Mini Agent - Multi-turn Interactive Session{Colors.RESET}"
    banner_width = calculate_display_width(banner_text)

    # Center the text with proper padding
    total_padding = BOX_WIDTH - banner_width
    left_padding = total_padding // 2
    right_padding = total_padding - left_padding

    print()
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}╔{'═' * BOX_WIDTH}╗{Colors.RESET}")
    print(
        f"{Colors.BOLD}{Colors.BRIGHT_CYAN}║{Colors.RESET}{' ' * left_padding}{banner_text}{' ' * right_padding}{Colors.BOLD}{Colors.BRIGHT_CYAN}║{Colors.RESET}"
    )
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}╚{'═' * BOX_WIDTH}╝{Colors.RESET}")
    print()


def print_help():
    """Print help information"""
    help_text = f"""
{Colors.BOLD}{Colors.BRIGHT_YELLOW}Available Commands:{Colors.RESET}
  {Colors.BRIGHT_GREEN}/help{Colors.RESET}      - Show this help message
  {Colors.BRIGHT_GREEN}/clear{Colors.RESET}     - Clear session history (keep system prompt)
  {Colors.BRIGHT_GREEN}/history{Colors.RESET}   - Show current session message count
  {Colors.BRIGHT_GREEN}/stats{Colors.RESET}     - Show session statistics
  {Colors.BRIGHT_GREEN}/log{Colors.RESET}       - Show log directory and recent files
  {Colors.BRIGHT_GREEN}/log <file>{Colors.RESET} - Read a specific log file
  {Colors.BRIGHT_GREEN}/debate <topic>{Colors.RESET} - Multi-agent bull/bear debate with judge verdict
  {Colors.BRIGHT_GREEN}/exit{Colors.RESET}      - Exit program (also: exit, quit, q)

{Colors.BOLD}{Colors.BRIGHT_YELLOW}Keyboard Shortcuts:{Colors.RESET}
  {Colors.BRIGHT_CYAN}Esc{Colors.RESET}        - Cancel current agent execution
  {Colors.BRIGHT_CYAN}Ctrl+C{Colors.RESET}     - Exit program
  {Colors.BRIGHT_CYAN}Ctrl+U{Colors.RESET}     - Clear current input line
  {Colors.BRIGHT_CYAN}Ctrl+L{Colors.RESET}     - Clear screen
  {Colors.BRIGHT_CYAN}Ctrl+J{Colors.RESET}     - Insert newline (also Ctrl+Enter)
  {Colors.BRIGHT_CYAN}Tab{Colors.RESET}        - Auto-complete commands
  {Colors.BRIGHT_CYAN}↑/↓{Colors.RESET}        - Browse command history
  {Colors.BRIGHT_CYAN}→{Colors.RESET}          - Accept auto-suggestion

{Colors.BOLD}{Colors.BRIGHT_YELLOW}Usage:{Colors.RESET}
  - Enter your task directly, Agent will help you complete it
  - Agent remembers all conversation content in this session
  - Use {Colors.BRIGHT_GREEN}/clear{Colors.RESET} to start a new session
  - Press {Colors.BRIGHT_CYAN}Enter{Colors.RESET} to submit your message
  - Use {Colors.BRIGHT_CYAN}Ctrl+J{Colors.RESET} to insert line breaks within your message
"""
    print(help_text)


def print_session_info(agent: Agent, workspace_dir: Path, model: str):
    """Print session information with proper alignment"""
    BOX_WIDTH = 58

    def print_info_line(text: str):
        """Print a single info line with proper padding"""
        # Account for leading space
        text_width = calculate_display_width(text)
        padding = max(0, BOX_WIDTH - 1 - text_width)
        print(f"{Colors.DIM}│{Colors.RESET} {text}{' ' * padding}{Colors.DIM}│{Colors.RESET}")

    # Top border
    print(f"{Colors.DIM}┌{'─' * BOX_WIDTH}┐{Colors.RESET}")

    # Header (centered)
    header_text = f"{Colors.BRIGHT_CYAN}Session Info{Colors.RESET}"
    header_width = calculate_display_width(header_text)
    header_padding_total = BOX_WIDTH - 1 - header_width  # -1 for leading space
    header_padding_left = header_padding_total // 2
    header_padding_right = header_padding_total - header_padding_left
    print(f"{Colors.DIM}│{Colors.RESET} {' ' * header_padding_left}{header_text}{' ' * header_padding_right}{Colors.DIM}│{Colors.RESET}")

    # Divider
    print(f"{Colors.DIM}├{'─' * BOX_WIDTH}┤{Colors.RESET}")

    # Info lines
    print_info_line(f"Model: {model}")
    print_info_line(f"Workspace: {workspace_dir}")
    print_info_line(f"Message History: {len(agent.messages)} messages")
    print_info_line(f"Available Tools: {len(agent.tools)} tools")

    # Bottom border
    print(f"{Colors.DIM}└{'─' * BOX_WIDTH}┘{Colors.RESET}")
    print()
    print(f"{Colors.DIM}Type {Colors.BRIGHT_GREEN}/help{Colors.DIM} for help, {Colors.BRIGHT_GREEN}/exit{Colors.DIM} to quit{Colors.RESET}")
    print()


def print_stats(agent: Agent, session_start: datetime):
    """Print session statistics"""
    duration = datetime.now() - session_start
    hours, remainder = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    # Count different types of messages
    user_msgs = sum(1 for m in agent.messages if m.role == "user")
    assistant_msgs = sum(1 for m in agent.messages if m.role == "assistant")
    tool_msgs = sum(1 for m in agent.messages if m.role == "tool")

    print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Session Statistics:{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 40}{Colors.RESET}")
    print(f"  Session Duration: {hours:02d}:{minutes:02d}:{seconds:02d}")
    print(f"  Total Messages: {len(agent.messages)}")
    print(f"    - User Messages: {Colors.BRIGHT_GREEN}{user_msgs}{Colors.RESET}")
    print(f"    - Assistant Replies: {Colors.BRIGHT_BLUE}{assistant_msgs}{Colors.RESET}")
    print(f"    - Tool Calls: {Colors.BRIGHT_YELLOW}{tool_msgs}{Colors.RESET}")
    print(f"  Available Tools: {len(agent.tools)}")
    if agent.api_total_tokens > 0:
        print(f"  API Tokens Used: {Colors.BRIGHT_MAGENTA}{agent.api_total_tokens:,}{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 40}{Colors.RESET}\n")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Mini Agent - AI assistant with file tools and MCP support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mini-agent                              # Use current directory as workspace
  mini-agent --workspace /path/to/dir     # Use specific workspace directory
  mini-agent log                          # Show log directory and recent files
  mini-agent log agent_run_xxx.log        # Read a specific log file
        """,
    )
    parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory (default: current directory)",
    )
    parser.add_argument(
        "--task",
        "-t",
        type=str,
        default=None,
        help="Execute a task non-interactively and exit",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version="mini-agent 0.1.0",
    )
    parser.add_argument(
        "--memory-judge",
        action="store_true",
        default=False,
        help="Reserved: enable offline LLM judge for memory usage analysis (no-op currently)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # log subcommand
    log_parser = subparsers.add_parser("log", help="Show log directory or read log files")
    log_parser.add_argument(
        "filename",
        nargs="?",
        default=None,
        help="Log filename to read (optional, shows directory if omitted)",
    )

    return parser.parse_args()


async def initialize_base_tools(config: Config):
    """Initialize base tools (independent of workspace)

    These tools are loaded from package configuration and don't depend on workspace.
    Note: File tools are now workspace-dependent and initialized in add_workspace_tools()

    Args:
        config: Configuration object

    Returns:
        Tuple of (list of tools, skill loader if skills enabled)
    """

    tools = []
    skill_loader = None

    # 1. Bash auxiliary tools (output monitoring and kill)
    # Note: BashTool itself is created in add_workspace_tools() with workspace_dir as cwd
    if config.tools.enable_bash:
        bash_output_tool = BashOutputTool()
        tools.append(bash_output_tool)
        print(f"{Colors.GREEN}✅ Loaded Bash Output tool{Colors.RESET}")

        bash_kill_tool = BashKillTool()
        tools.append(bash_kill_tool)
        print(f"{Colors.GREEN}✅ Loaded Bash Kill tool{Colors.RESET}")

    # 3. Claude Skills (loaded from package directory)
    if config.tools.enable_skills:
        print(f"{Colors.BRIGHT_CYAN}Loading Claude Skills...{Colors.RESET}")
        try:
            # Resolve skills directory with priority search
            # Expand ~ to user home directory for portability
            skills_path = Path(config.tools.skills_dir).expanduser()
            if skills_path.is_absolute():
                skills_dir = str(skills_path)
            else:
                # Search in priority order:
                # 1. Current directory (dev mode: ./skills or ./mini_agent/skills)
                # 2. Package directory (installed: site-packages/mini_agent/skills)
                search_paths = [
                    skills_path,  # ./skills for backward compatibility
                    Path("mini_agent") / skills_path,  # ./mini_agent/skills
                    Config.get_package_dir() / skills_path,  # site-packages/mini_agent/skills
                ]

                # Find first existing path
                skills_dir = str(skills_path)  # default
                for path in search_paths:
                    if path.exists():
                        skills_dir = str(path.resolve())
                        break

            skill_tools, skill_loader = create_skill_tools(skills_dir)
            if skill_tools:
                tools.extend(skill_tools)
                print(f"{Colors.GREEN}✅ Loaded Skill tool (get_skill){Colors.RESET}")
            else:
                print(f"{Colors.YELLOW}⚠️  No available Skills found{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.YELLOW}⚠️  Failed to load Skills: {e}{Colors.RESET}")

    # 4. MCP tools (loaded with priority search)
    if config.tools.enable_mcp:
        print(f"{Colors.BRIGHT_CYAN}Loading MCP tools...{Colors.RESET}")
        try:
            # Apply MCP timeout configuration from config.yaml
            mcp_config = config.tools.mcp
            set_mcp_timeout_config(
                connect_timeout=mcp_config.connect_timeout,
                execute_timeout=mcp_config.execute_timeout,
                sse_read_timeout=mcp_config.sse_read_timeout,
            )
            print(
                f"{Colors.DIM}  MCP timeouts: connect={mcp_config.connect_timeout}s, "
                f"execute={mcp_config.execute_timeout}s, sse_read={mcp_config.sse_read_timeout}s{Colors.RESET}"
            )

            # Use priority search for mcp.json
            mcp_config_path = Config.find_config_file(config.tools.mcp_config_path)
            if mcp_config_path:
                mcp_tools = await load_mcp_tools_async(str(mcp_config_path))
                if mcp_tools:
                    tools.extend(mcp_tools)
                    print(f"{Colors.GREEN}✅ Loaded {len(mcp_tools)} MCP tools (from: {mcp_config_path}){Colors.RESET}")
                else:
                    print(f"{Colors.YELLOW}⚠️  No available MCP tools found{Colors.RESET}")
            else:
                print(f"{Colors.YELLOW}⚠️  MCP config file not found: {config.tools.mcp_config_path}{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.YELLOW}⚠️  Failed to load MCP tools: {e}{Colors.RESET}")

    print()  # Empty line separator
    return tools, skill_loader


def add_workspace_tools(tools: List[Tool], config: Config, workspace_dir: Path):
    """Add workspace-dependent tools

    These tools need to know the workspace directory.

    Args:
        tools: Existing tools list to add to
        config: Configuration object
        workspace_dir: Workspace directory path
    """
    # Ensure workspace directory exists
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Bash tool - needs workspace as cwd for command execution
    if config.tools.enable_bash:
        bash_tool = BashTool(workspace_dir=str(workspace_dir))
        tools.append(bash_tool)
        print(f"{Colors.GREEN}✅ Loaded Bash tool (cwd: {workspace_dir}){Colors.RESET}")

    # File tools - need workspace to resolve relative paths
    if config.tools.enable_file_tools:
        tools.extend(
            [
                ReadTool(workspace_dir=str(workspace_dir)),
                WriteTool(workspace_dir=str(workspace_dir)),
                EditTool(workspace_dir=str(workspace_dir)),
            ]
        )
        print(f"{Colors.GREEN}✅ Loaded file operation tools (workspace: {workspace_dir}){Colors.RESET}")

    # Session note tool - needs workspace to store memory file
    if config.tools.enable_note:
        tools.append(SessionNoteTool(memory_file=str(workspace_dir / ".agent_memory.json")))
        tools.append(RecallNoteTool(memory_file=str(workspace_dir / ".agent_memory.json")))
        print(f"{Colors.GREEN}✅ Loaded session note tools (record + recall){Colors.RESET}")

    # Calculator tool - deterministic arithmetic (don't trust LLM math)
    from mini_agent.tools.calculator_tool import CalculatorTool
    tools.append(CalculatorTool())
    print(f"{Colors.GREEN}✅ Loaded calculator tool{Colors.RESET}")

    # Weather tool - no workspace dependency but loaded here for convenience
    from mini_agent.tools.weather_tool import WeatherTool
    tools.append(WeatherTool())
    print(f"{Colors.GREEN}✅ Loaded weather tool{Colors.RESET}")


async def _quiet_cleanup():
    """Clean up MCP connections, suppressing noisy asyncgen teardown tracebacks."""
    # Silence the asyncgen finalization noise that anyio/mcp emits when
    # stdio_client's task group is torn down across tasks.  The handler is
    # intentionally NOT restored: asyncgen finalization happens during
    # asyncio.run() shutdown (after run_agent returns), so restoring the
    # handler here would still let the noise through.  Since this runs
    # right before process exit, swallowing late exceptions is safe.
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(lambda _loop, _ctx: None)
    try:
        await cleanup_mcp_connections()
    except Exception:
        pass


async def _run_with_esc_cancel(coro_factory, stream_display: StreamingDisplay):
    """Run a coroutine factory with Esc-to-cancel support.

    coro_factory receives an asyncio.Event used as the cancellation event.
    Returns (result, cancelled).
    """
    cancel_event = asyncio.Event()
    esc_listener_stop = threading.Event()
    esc_cancelled = [False]  # Mutable container for thread access

    def esc_key_listener():
        """Listen for Esc key in a separate thread."""
        if platform.system() == "Windows":
            try:
                import msvcrt

                while not esc_listener_stop.is_set():
                    if msvcrt.kbhit():
                        char = msvcrt.getch()
                        if char == b"\x1b":  # Esc
                            stream_display.finish()
                            print(f"\n{Colors.BRIGHT_YELLOW}⏹️  Esc pressed, cancelling...{Colors.RESET}")
                            esc_cancelled[0] = True
                            cancel_event.set()
                            break
                    esc_listener_stop.wait(0.05)
            except Exception:
                pass
            return

        # Unix/macOS
        try:
            import select
            import termios
            import tty

            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)

            try:
                tty.setcbreak(fd)
                while not esc_listener_stop.is_set():
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if rlist:
                        char = sys.stdin.read(1)
                        if char == "\x1b":  # Esc
                            stream_display.finish()
                            print(f"\n{Colors.BRIGHT_YELLOW}⏹️  Esc pressed, cancelling...{Colors.RESET}")
                            esc_cancelled[0] = True
                            cancel_event.set()
                            break
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass

    esc_thread = threading.Thread(target=esc_key_listener, daemon=True)
    esc_thread.start()

    try:
        task = asyncio.create_task(coro_factory(cancel_event))
        while not task.done():
            if esc_cancelled[0]:
                cancel_event.set()
            await asyncio.sleep(0.1)
        return task.result(), False
    except asyncio.CancelledError:
        return None, True
    finally:
        esc_listener_stop.set()
        esc_thread.join(timeout=0.2)


def _parse_debate_args(user_input: str):
    """Parse `/debate <topic> [--rounds N]`. Returns (topic, rounds) or (None, 0)."""
    parts = user_input.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return None, 0
    rest = parts[1].strip()
    rounds = 2
    match = re.search(r"(?:^|\s)--rounds[= ](\d+)(?=\s|$)", rest)
    if match:
        rounds = max(1, int(match.group(1)))
        rest = rest[: match.start()] + rest[match.end():]
    topic = rest.strip()
    return (topic, rounds) if topic else (None, 0)


async def run_debate_command(
    llm_client,
    tools: List,
    workspace_dir: Path,
    topic: str,
    rounds: int,
    stream_display: StreamingDisplay,
):
    """Run a bull/bear debate with a judge verdict via the multi-agent layer."""
    from mini_agent.multi_agent import AgentRegistry, DebateOrchestrator, SharedTranscript

    registry = AgentRegistry()
    transcript = SharedTranscript()

    def on_turn_start(role: str, round_no: int):
        icons = {"bull": "🐂", "bear": "🐻", "judge": "⚖️"}
        labels = {"bull": "Bull", "bear": "Bear", "judge": "Judge"}
        colors = {
            "bull": Colors.BRIGHT_GREEN,
            "bear": Colors.BRIGHT_RED,
            "judge": Colors.BRIGHT_YELLOW,
        }
        stream_display.finish()
        round_label = f" (R{round_no})" if role != "judge" else ""
        print(
            f"\n{Colors.BOLD}{colors[role]}{icons[role]} {labels[role]}{round_label}{Colors.RESET}"
            f" {Colors.DIM}›{Colors.RESET}\n"
        )

    orchestrator = DebateOrchestrator(
        num_rounds=rounds,
        on_turn_start=on_turn_start,
        registry=registry,
        transcript=transcript,
        llm_client=llm_client,
        tools=tools,
        workspace_dir=str(workspace_dir),
    )

    print(
        f"\n{Colors.BRIGHT_MAGENTA}⚔️  Debate started{Colors.RESET} "
        f"{Colors.DIM}(topic: {topic} | rounds: {rounds} | Esc to cancel){Colors.RESET}\n"
    )

    def coro_factory(cancel_event: asyncio.Event):
        orchestrator.cancel_event = cancel_event
        return orchestrator.run(topic)

    verdict, _ = await _run_with_esc_cancel(coro_factory, stream_display)

    # Save the full debate transcript to the workspace
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    transcript_file = workspace_dir / f"debate_{timestamp}.md"
    try:
        header = (
            f"# Debate Transcript\n\n- Topic: {topic}\n- Rounds: {rounds}\n"
            f"- Time: {timestamp}\n\n"
        )
        body = transcript.render() if transcript.messages else "(no turns completed)"
        transcript_file.write_text(header + body, encoding="utf-8")
    except Exception as e:
        print(f"{Colors.RED}❌ Failed to save debate transcript: {e}{Colors.RESET}")
        transcript_file = None

    if verdict == "Task cancelled by user.":
        print(f"\n{Colors.BRIGHT_YELLOW}⚠️  Debate cancelled{Colors.RESET}")
    elif transcript_file:
        print(
            f"\n{Colors.GREEN}✅ Debate finished, transcript saved to: "
            f"{transcript_file}{Colors.RESET}\n"
        )


async def run_agent(workspace_dir: Path, task: str = None, memory_judge: bool = False):
    """Run Agent in interactive or non-interactive mode.

    Args:
        workspace_dir: Workspace directory path
        task: If provided, execute this task and exit (non-interactive mode)
        memory_judge: Reserved flag for the future offline LLM judge (no-op now)
    """
    session_start = datetime.now()

    # 1. Load configuration from package directory
    config_path = Config.get_default_config_path()

    if not config_path.exists():
        print(f"{Colors.RED}❌ Configuration file not found{Colors.RESET}")
        print()
        print(f"{Colors.BRIGHT_CYAN}📦 Configuration Search Path:{Colors.RESET}")
        print(f"  {Colors.DIM}1) mini_agent/config/config.yaml{Colors.RESET} (development)")
        print(f"  {Colors.DIM}2) ~/.mini-agent/config/config.yaml{Colors.RESET} (user)")
        print(f"  {Colors.DIM}3) <package>/config/config.yaml{Colors.RESET} (installed)")
        print()
        print(f"{Colors.BRIGHT_YELLOW}🚀 Quick Setup (Recommended):{Colors.RESET}")
        print(
            f"  {Colors.BRIGHT_GREEN}curl -fsSL https://raw.githubusercontent.com/MiniMax-AI/Mini-Agent/main/scripts/setup-config.sh | bash{Colors.RESET}"
        )
        print()
        print(f"{Colors.DIM}  This will automatically:{Colors.RESET}")
        print(f"{Colors.DIM}    • Create ~/.mini-agent/config/{Colors.RESET}")
        print(f"{Colors.DIM}    • Download configuration files{Colors.RESET}")
        print(f"{Colors.DIM}    • Guide you to add your API Key{Colors.RESET}")
        print()
        print(f"{Colors.BRIGHT_YELLOW}📝 Manual Setup:{Colors.RESET}")
        user_config_dir = Path.home() / ".mini-agent" / "config"
        example_config = Config.get_package_dir() / "config" / "config-example.yaml"
        print(f"  {Colors.DIM}mkdir -p {user_config_dir}{Colors.RESET}")
        print(f"  {Colors.DIM}cp {example_config} {user_config_dir}/config.yaml{Colors.RESET}")
        print(f"  {Colors.DIM}# Then edit {user_config_dir}/config.yaml to add your API Key{Colors.RESET}")
        print()
        return

    try:
        config = Config.from_yaml(config_path)
        config.agent.memory_judge = memory_judge
    except FileNotFoundError:
        print(f"{Colors.RED}❌ Error: Configuration file not found: {config_path}{Colors.RESET}")
        return
    except ValueError as e:
        print(f"{Colors.RED}❌ Error: {e}{Colors.RESET}")
        print(f"{Colors.YELLOW}Please check the configuration file format{Colors.RESET}")
        return
    except Exception as e:
        print(f"{Colors.RED}❌ Error: Failed to load configuration file: {e}{Colors.RESET}")
        return

    # 2. Initialize LLM client
    from mini_agent.retry import RetryConfig as RetryConfigBase

    # Convert configuration format
    retry_config = RetryConfigBase(
        enabled=config.llm.retry.enabled,
        max_retries=config.llm.retry.max_retries,
        initial_delay=config.llm.retry.initial_delay,
        max_delay=config.llm.retry.max_delay,
        exponential_base=config.llm.retry.exponential_base,
        retryable_exceptions=(Exception,),
    )

    # Live streaming strip: shows LLM output in a small in-place area
    stream_display = StreamingDisplay(max_lines=3)

    # Create retry callback function to display retry information in terminal
    def on_retry(exception: Exception, attempt: int):
        """Retry callback function to display retry information"""
        stream_display.finish()  # clear the streaming strip before printing
        print(f"\n{Colors.BRIGHT_YELLOW}⚠️  LLM call failed (attempt {attempt}): {str(exception)}{Colors.RESET}")
        next_delay = retry_config.calculate_delay(attempt - 1)
        print(f"{Colors.DIM}   Retrying in {next_delay:.1f}s (attempt {attempt + 1})...{Colors.RESET}")

    # Convert provider string to LLMProvider enum
    provider = LLMProvider.ANTHROPIC if config.llm.provider.lower() == "anthropic" else LLMProvider.OPENAI

    llm_client = LLMClient(
        api_key=config.llm.api_key,
        provider=provider,
        api_base=config.llm.api_base,
        model=config.llm.model,
        retry_config=retry_config if config.llm.retry.enabled else None,
        timeout=config.llm.timeout,
    )

    # Set retry callback
    if config.llm.retry.enabled:
        llm_client.retry_callback = on_retry
        print(f"{Colors.GREEN}✅ LLM retry mechanism enabled (max {config.llm.retry.max_retries} retries){Colors.RESET}")

    # Hook up live streaming display (updates on every LLM text delta,
    # cleared automatically when each stream ends)
    llm_client.stream_callback = stream_display.update
    llm_client.stream_end_callback = stream_display.finish

    # 3. Initialize base tools (independent of workspace)
    tools, skill_loader = await initialize_base_tools(config)

    # 4. Add workspace-dependent tools
    add_workspace_tools(tools, config, workspace_dir)

    # 4.5 Load plugins (Claude Code format agents/skills from mini_agent/plugins)
    plugin_directory = None
    if config.tools.enable_plugins:
        from mini_agent.multi_agent.dispatch_tool import DispatchAgentTool
        from mini_agent.multi_agent.plugin_loader import discover_plugins

        plugins_path = Path(config.tools.plugins_dir).expanduser()
        search_paths = [
            plugins_path,                              # ./plugins
            Path("mini_agent") / plugins_path,         # ./mini_agent/plugins
            Config.get_package_dir() / plugins_path,   # site-packages/mini_agent/plugins
        ]
        plugins_dir = next((p.resolve() for p in search_paths if p.exists()), None)
        if plugins_dir:
            plugin_directory = discover_plugins(plugins_dir)
            for warning in plugin_directory.warnings:
                print(f"{Colors.YELLOW}{warning}{Colors.RESET}")
            if plugin_directory.definitions:
                # 排除主 agent 的 get_skill：Agent.tools 按名字建 dict，
                # 两个 get_skill 会静默互相覆盖；subagent 只用插件版 skill 工具。
                base_for_subagents = [t for t in tools if t.name != "get_skill"]
                dispatch_tool = DispatchAgentTool(
                    directory=plugin_directory,
                    llm_client=llm_client,
                    base_tools=base_for_subagents,
                    workspace_dir=str(workspace_dir),
                    max_steps=config.agent.max_steps,
                )
                tools.append(dispatch_tool)
                print(
                    f"{Colors.GREEN}✅ Loaded plugins: {len(plugin_directory.definitions)} "
                    f"subagents ({', '.join(plugin_directory.names())}){Colors.RESET}"
                )
                # frontmatter 里引用的、本机没有的工具（mcp__factset__* 等）警告一次
                known = {t.name for t in tools}
                unresolved = sorted(
                    {t for d in plugin_directory.definitions.values() for t in d.tools}
                    - known
                )
                if unresolved:
                    print(
                        f"{Colors.YELLOW}⚠️  插件引用的不可用工具（已忽略）: "
                        f"{', '.join(unresolved)}{Colors.RESET}"
                    )
            else:
                print(f"{Colors.YELLOW}⚠️  No plugin agents found in {plugins_dir}{Colors.RESET}")

    # 5. Load System Prompt (with priority search)
    system_prompt_path = Config.find_config_file(config.agent.system_prompt_path)
    if system_prompt_path and system_prompt_path.exists():
        system_prompt = system_prompt_path.read_text(encoding="utf-8")
        print(f"{Colors.GREEN}✅ Loaded system prompt (from: {system_prompt_path}){Colors.RESET}")
    else:
        system_prompt = "You are Mini-Agent, an intelligent assistant powered by MiniMax M2.5 that can help users complete various tasks."
        print(f"{Colors.YELLOW}⚠️  System prompt not found, using default{Colors.RESET}")

    # 6. Inject Skills Metadata into System Prompt (Progressive Disclosure - Level 1)
    if skill_loader:
        skills_metadata = skill_loader.get_skills_metadata_prompt()
        if skills_metadata:
            # Replace placeholder with actual metadata
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", skills_metadata)
            print(f"{Colors.GREEN}✅ Injected {len(skill_loader.loaded_skills)} skills metadata into system prompt{Colors.RESET}")
        else:
            # Remove placeholder if no skills
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")
    else:
        # Remove placeholder if skills not enabled
        system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")

    # 6.5 Inject Memory Usage Policy (only when memory MCP tools are available)
    from .memory import MEMORY_POLICY_TEXT, find_memory_tools

    memory_tools = find_memory_tools(tool.name for tool in tools)
    if memory_tools:
        if "{MEMORY_POLICY}" in system_prompt:
            system_prompt = system_prompt.replace("{MEMORY_POLICY}", MEMORY_POLICY_TEXT)
        else:
            # Fallback: custom system prompt without the placeholder
            system_prompt = system_prompt + "\n\n" + MEMORY_POLICY_TEXT
        print(f"{Colors.GREEN}✅ Injected memory policy (memory tools: {', '.join(memory_tools)}){Colors.RESET}")
    else:
        system_prompt = system_prompt.replace("{MEMORY_POLICY}", "")

    # 6.6 Inject available subagents into system prompt
    if plugin_directory and plugin_directory.definitions:
        system_prompt = system_prompt + "\n\n" + plugin_directory.prompt_section()

    # 7. Create Agent
    agent = Agent(
        llm_client=llm_client,
        system_prompt=system_prompt,
        tools=tools,
        max_steps=config.agent.max_steps,
        workspace_dir=str(workspace_dir),
        memory_judge=config.agent.memory_judge,
    )

    # 8. Display welcome information
    if not task:
        print_banner()
        print_session_info(agent, workspace_dir, config.llm.model)

    # 8.5 Non-interactive mode: execute task and exit
    if task:
        print(f"\n{Colors.BRIGHT_BLUE}Agent{Colors.RESET} {Colors.DIM}›{Colors.RESET} {Colors.DIM}Executing task...{Colors.RESET}\n")
        agent.add_user_message(task)
        try:
            await agent.run()
        except Exception as e:
            print(f"\n{Colors.RED}❌ Error: {e}{Colors.RESET}")
        finally:
            print_stats(agent, session_start)

        # Cleanup MCP connections
        await _quiet_cleanup()
        return

    # 9. Setup prompt_toolkit session
    # Command completer
    command_completer = WordCompleter(
        ["/help", "/clear", "/history", "/stats", "/log", "/debate", "/exit", "/quit", "/q"],
        ignore_case=True,
        sentence=True,
    )

    # Custom style for prompt
    prompt_style = Style.from_dict(
        {
            "prompt": "#00ff00 bold",  # Green and bold
            "separator": "#666666",  # Gray
        }
    )

    # Custom key bindings
    kb = KeyBindings()

    @kb.add("c-u")  # Ctrl+U: Clear current line
    def _(event):
        """Clear the current input line"""
        event.current_buffer.reset()

    @kb.add("c-l")  # Ctrl+L: Clear screen (optional bonus)
    def _(event):
        """Clear the screen"""
        event.app.renderer.clear()

    @kb.add("c-j")  # Ctrl+J (对应 Ctrl+Enter)
    def _(event):
        """Insert a newline"""
        event.current_buffer.insert_text("\n")

    # Create prompt session with history and auto-suggest
    # Use FileHistory for persistent history across sessions (stored in user's home directory)
    history_file = Path.home() / ".mini-agent" / ".history"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=command_completer,
        style=prompt_style,
        key_bindings=kb,
    )

    # 10. Interactive loop
    while True:
        try:
            # Get user input using prompt_toolkit
            user_input = await session.prompt_async(
                [
                    ("class:prompt", "You"),
                    ("", " › "),
                ],
                multiline=False,
                enable_history_search=True,
            )
            user_input = user_input.strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                command = user_input.lower()

                if command in ["/exit", "/quit", "/q"]:
                    print(f"\n{Colors.BRIGHT_YELLOW}👋 Goodbye! Thanks for using Mini Agent{Colors.RESET}\n")
                    print_stats(agent, session_start)
                    break

                elif command == "/help":
                    print_help()
                    continue

                elif command == "/clear":
                    # Clear message history but keep system prompt
                    old_count = len(agent.messages)
                    agent.messages = [agent.messages[0]]  # Keep only system message
                    print(f"{Colors.GREEN}✅ Cleared {old_count - 1} messages, starting new session{Colors.RESET}\n")
                    continue

                elif command == "/history":
                    print(f"\n{Colors.BRIGHT_CYAN}Current session message count: {len(agent.messages)}{Colors.RESET}\n")
                    continue

                elif command == "/stats":
                    print_stats(agent, session_start)
                    continue

                elif command == "/log" or command.startswith("/log "):
                    # Parse /log command
                    parts = user_input.split(maxsplit=1)
                    if len(parts) == 1:
                        # /log - show log directory
                        show_log_directory(open_file_manager=True)
                    else:
                        # /log <filename> - read specific log file
                        filename = parts[1].strip("\"'")
                        read_log_file(filename)
                    continue

                elif command == "/debate" or command.startswith("/debate "):
                    topic, rounds = _parse_debate_args(user_input)
                    if not topic:
                        print(
                            f"{Colors.RED}❌ Usage: /debate <topic> [--rounds N] "
                            f"(default rounds: 2){Colors.RESET}\n"
                        )
                        continue
                    try:
                        await run_debate_command(
                            llm_client, tools, workspace_dir, topic, rounds, stream_display
                        )
                    except Exception as e:
                        print(f"{Colors.RED}❌ Debate failed: {e}{Colors.RESET}\n")
                    continue

                else:
                    print(f"{Colors.RED}❌ Unknown command: {user_input}{Colors.RESET}")
                    print(f"{Colors.DIM}Type /help to see available commands{Colors.RESET}\n")
                    continue

            # Normal conversation - exit check
            if user_input.lower() in ["exit", "quit", "q"]:
                print(f"\n{Colors.BRIGHT_YELLOW}👋 Goodbye! Thanks for using Mini Agent{Colors.RESET}\n")
                print_stats(agent, session_start)
                break

            # Run Agent with Esc cancellation support
            print(
                f"\n{Colors.BRIGHT_BLUE}Agent{Colors.RESET} {Colors.DIM}›{Colors.RESET} {Colors.DIM}(Esc to cancel){Colors.RESET}\n"
            )
            agent.add_user_message(user_input)

            # Create cancellation event
            cancel_event = asyncio.Event()
            agent.cancel_event = cancel_event

            # Esc key listener thread
            esc_listener_stop = threading.Event()
            esc_cancelled = [False]  # Mutable container for thread access

            def esc_key_listener():
                """Listen for Esc key in a separate thread."""
                if platform.system() == "Windows":
                    try:
                        import msvcrt

                        while not esc_listener_stop.is_set():
                            if msvcrt.kbhit():
                                char = msvcrt.getch()
                                if char == b"\x1b":  # Esc
                                    stream_display.finish()  # clear strip before printing
                                    print(f"\n{Colors.BRIGHT_YELLOW}⏹️  Esc pressed, cancelling...{Colors.RESET}")
                                    esc_cancelled[0] = True
                                    cancel_event.set()
                                    break
                            esc_listener_stop.wait(0.05)
                    except Exception:
                        pass
                    return

                # Unix/macOS
                try:
                    import select
                    import termios
                    import tty

                    fd = sys.stdin.fileno()
                    old_settings = termios.tcgetattr(fd)

                    try:
                        tty.setcbreak(fd)
                        while not esc_listener_stop.is_set():
                            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                            if rlist:
                                char = sys.stdin.read(1)
                                if char == "\x1b":  # Esc
                                    stream_display.finish()  # clear strip before printing
                                    print(f"\n{Colors.BRIGHT_YELLOW}⏹️  Esc pressed, cancelling...{Colors.RESET}")
                                    esc_cancelled[0] = True
                                    cancel_event.set()
                                    break
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except Exception:
                    pass

            # Start Esc listener thread
            esc_thread = threading.Thread(target=esc_key_listener, daemon=True)
            esc_thread.start()

            # Run agent with periodic cancellation check
            try:
                agent_task = asyncio.create_task(agent.run())

                # Poll for cancellation while agent runs
                while not agent_task.done():
                    if esc_cancelled[0]:
                        cancel_event.set()
                    await asyncio.sleep(0.1)

                # Get result
                _ = agent_task.result()

            except asyncio.CancelledError:
                print(f"\n{Colors.BRIGHT_YELLOW}⚠️  Agent execution cancelled{Colors.RESET}")
            finally:
                agent.cancel_event = None
                esc_listener_stop.set()
                esc_thread.join(timeout=0.2)

            # Visual separation
            print(f"\n{Colors.DIM}{'─' * 60}{Colors.RESET}\n")

        except KeyboardInterrupt:
            print(f"\n\n{Colors.BRIGHT_YELLOW}👋 Interrupt signal detected, exiting...{Colors.RESET}\n")
            print_stats(agent, session_start)
            break

        except Exception as e:
            print(f"\n{Colors.RED}❌ Error: {e}{Colors.RESET}")
            print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}\n")

    # 11. Cleanup MCP connections
    await _quiet_cleanup()


def main():
    """Main entry point for CLI"""
    # Parse command line arguments
    args = parse_args()

    # Handle log subcommand
    if args.command == "log":
        if args.filename:
            read_log_file(args.filename)
        else:
            show_log_directory(open_file_manager=True)
        return

    # Determine workspace directory
    # Expand ~ to user home directory for portability
    if args.workspace:
        workspace_dir = Path(args.workspace).expanduser().absolute()
    else:
        # Use current working directory
        workspace_dir = Path.cwd()

    # Ensure workspace directory exists
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Run the agent (config always loaded from package directory)
    asyncio.run(
        run_agent(workspace_dir, task=args.task, memory_judge=getattr(args, "memory_judge", False))
    )


if __name__ == "__main__":
    main()

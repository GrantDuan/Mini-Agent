"""OpenAI LLM client implementation."""

import json
import logging
import time
from types import SimpleNamespace
from typing import Any

from openai import AsyncOpenAI

from ..retry import RetryConfig, async_retry
from ..schema import FunctionCall, LLMResponse, Message, TokenUsage, ToolCall
from .base import LLMClientBase

logger = logging.getLogger(__name__)


class OpenAIClient(LLMClientBase):
    """LLM client using OpenAI's protocol.

    This client uses the official OpenAI SDK and supports:
    - Reasoning content (via reasoning_split=True)
    - Tool calling
    - Retry logic
    """

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.minimaxi.com/v1",
        model: str = "MiniMax-M2.5",
        retry_config: RetryConfig | None = None,
        timeout: float = 600.0,
    ):
        """Initialize OpenAI client.

        Args:
            api_key: API key for authentication
            api_base: Base URL for the API (default: MiniMax OpenAI endpoint)
            model: Model name to use (default: MiniMax-M2.5)
            retry_config: Optional retry configuration
            timeout: Request timeout in seconds
        """
        super().__init__(api_key, api_base, model, retry_config, timeout)

        # Initialize OpenAI client with request timeout
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=self.timeout,
        )

    async def _make_api_request(
        self,
        api_messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> Any:
        """Execute API request (core method that can be retried).

        Args:
            api_messages: List of messages in OpenAI format
            tools: Optional list of tools

        Returns:
            OpenAI ChatCompletion response (full response including usage)

        Raises:
            Exception: API call failed
        """
        params = {
            "model": self.model,
            "messages": api_messages,
            # Enable reasoning_split to separate thinking content
            "extra_body": {"reasoning_split": True},
            # Streaming mode: the read timeout measures the gap between chunks
            # instead of the total generation time, so long-running reasoning
            # is not cut off as long as data keeps flowing, while a stalled
            # connection is detected within one read-timeout window.
            "stream": True,
            # Ask the server to append a final usage-only chunk
            "stream_options": {"include_usage": True},
        }

        if tools:
            params["tools"] = self._convert_tools(tools)

        start = time.monotonic()
        first_token_after: float | None = None

        # Content parts accumulated from chunk deltas
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        # tool_calls accumulated by index: {index: {"id", "name", "arguments"}}
        tool_calls_acc: dict[int, dict[str, str]] = {}
        usage: Any = None

        stream = await self.client.chat.completions.create(**params)
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage

            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta

            # First content-bearing chunk marks time-to-first-token
            if first_token_after is None and (
                getattr(delta, "content", None)
                or getattr(delta, "reasoning_content", None)
                or getattr(delta, "reasoning_details", None)
                or getattr(delta, "tool_calls", None)
            ):
                first_token_after = time.monotonic() - start

            # Text content
            if delta.content:
                content_parts.append(delta.content)
                if self.stream_callback:
                    self.stream_callback(delta.content)

            # Reasoning / thinking content (MiniMax-style extension)
            reasoning_piece = getattr(delta, "reasoning_content", None) or getattr(
                delta, "reasoning_details", None
            )
            if reasoning_piece:
                if isinstance(reasoning_piece, str):
                    thinking_parts.append(reasoning_piece)
                    if self.stream_callback:
                        self.stream_callback(reasoning_piece)
                elif isinstance(reasoning_piece, list):
                    for part in reasoning_piece:
                        piece_text = getattr(part, "text", "") or ""
                        thinking_parts.append(piece_text)
                        if piece_text and self.stream_callback:
                            self.stream_callback(piece_text)

            # Tool call deltas: merge by index
            for tc in delta.tool_calls or []:
                acc = tool_calls_acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    acc["id"] += tc.id
                if tc.function and tc.function.name:
                    acc["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    acc["arguments"] += tc.function.arguments

        logger.info(
            "LLM stream finished: first token after %.1fs, total %.1fs",
            first_token_after if first_token_after is not None else -1.0,
            time.monotonic() - start,
        )

        # Assemble a ChatCompletion-shaped object so _parse_response works
        # unchanged for both streaming and non-streaming code paths.
        message = SimpleNamespace(
            content="".join(content_parts),
            reasoning_details=(
                [SimpleNamespace(text="".join(thinking_parts))] if thinking_parts else []
            ),
            tool_calls=(
                [
                    SimpleNamespace(
                        id=acc["id"],
                        function=SimpleNamespace(name=acc["name"], arguments=acc["arguments"]),
                    )
                    for _, acc in sorted(tool_calls_acc.items())
                ]
                or None
            ),
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)

    def _convert_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        """Convert tools to OpenAI format.

        Args:
            tools: List of Tool objects or dicts

        Returns:
            List of tools in OpenAI dict format
        """
        result = []
        for tool in tools:
            if isinstance(tool, dict):
                # If already a dict, check if it's in OpenAI format
                if "type" in tool and tool["type"] == "function":
                    result.append(tool)
                else:
                    # Assume it's in Anthropic format, convert to OpenAI
                    result.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool["name"],
                                "description": tool["description"],
                                "parameters": tool["input_schema"],
                            },
                        }
                    )
            elif hasattr(tool, "to_openai_schema"):
                # Tool object with to_openai_schema method
                result.append(tool.to_openai_schema())
            else:
                raise TypeError(f"Unsupported tool type: {type(tool)}")
        return result

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal messages to OpenAI format.

        Args:
            messages: List of internal Message objects

        Returns:
            Tuple of (system_message, api_messages)
            Note: OpenAI includes system message in the messages array
        """
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                # OpenAI includes system message in messages array
                api_messages.append({"role": "system", "content": msg.content})
                continue

            # For user messages
            if msg.role == "user":
                api_messages.append({"role": "user", "content": msg.content})

            # For assistant messages
            elif msg.role == "assistant":
                assistant_msg = {"role": "assistant"}

                # Add content if present
                if msg.content:
                    assistant_msg["content"] = msg.content

                # Add tool calls if present
                if msg.tool_calls:
                    tool_calls_list = []
                    for tool_call in msg.tool_calls:
                        tool_calls_list.append(
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": json.dumps(tool_call.function.arguments),
                                },
                            }
                        )
                    assistant_msg["tool_calls"] = tool_calls_list

                # IMPORTANT: Add reasoning_details if thinking is present
                # This is CRITICAL for Interleaved Thinking to work properly!
                # The complete response_message (including reasoning_details) must be
                # preserved in Message History and passed back to the model in the next turn.
                # This ensures the model's chain of thought is not interrupted.
                if msg.thinking:
                    assistant_msg["reasoning_details"] = [{"text": msg.thinking}]

                api_messages.append(assistant_msg)

            # For tool result messages
            elif msg.role == "tool":
                api_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                )

        return None, api_messages

    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare the request for OpenAI API.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            Dictionary containing request parameters
        """
        _, api_messages = self._convert_messages(messages)

        return {
            "api_messages": api_messages,
            "tools": tools,
        }

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse OpenAI response into LLMResponse.

        Args:
            response: OpenAI ChatCompletion response (full response object)

        Returns:
            LLMResponse object
        """
        # Get message from response
        message = response.choices[0].message

        # Extract text content
        text_content = message.content or ""

        # Extract thinking content from reasoning_details
        thinking_content = ""
        if hasattr(message, "reasoning_details") and message.reasoning_details:
            # reasoning_details is a list of reasoning blocks
            for detail in message.reasoning_details:
                if hasattr(detail, "text"):
                    thinking_content += detail.text

        # Extract tool calls
        tool_calls = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                # Parse arguments from JSON string
                arguments = json.loads(tool_call.function.arguments)

                tool_calls.append(
                    ToolCall(
                        id=tool_call.id,
                        type="function",
                        function=FunctionCall(
                            name=tool_call.function.name,
                            arguments=arguments,
                        ),
                    )
                )

        # Extract token usage from response
        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
                total_tokens=response.usage.total_tokens or 0,
            )

        return LLMResponse(
            content=text_content,
            thinking=thinking_content if thinking_content else None,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason="stop",  # OpenAI doesn't provide finish_reason in the message
            usage=usage,
        )

    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> LLMResponse:
        """Generate response from OpenAI LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            LLMResponse containing the generated content
        """
        # Prepare request
        request_params = self._prepare_request(messages, tools)

        # Make API request with retry logic
        if self.retry_config.enabled:
            # Apply retry logic
            retry_decorator = async_retry(config=self.retry_config, on_retry=self.retry_callback)
            api_call = retry_decorator(self._make_api_request)
            response = await api_call(
                request_params["api_messages"],
                request_params["tools"],
            )
        else:
            # Don't use retry
            response = await self._make_api_request(
                request_params["api_messages"],
                request_params["tools"],
            )

        # Parse and return response
        self._notify_stream_end()
        return self._parse_response(response)

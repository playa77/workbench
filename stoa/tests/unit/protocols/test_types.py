from caw.protocols.provider import ModelProvider
from caw.protocols.types import (
    ContentBlock,
    ProviderHealth,
    ProviderMessage,
    ProviderResponse,
    ProviderStreamChunk,
    ToolDefinition,
)


def test_content_block_text() -> None:
    block = ContentBlock(type="text", text="hello")
    assert block.type == "text"
    assert block.text == "hello"


def test_provider_message_construction() -> None:
    message = ProviderMessage(
        role="user",
        content=[
            ContentBlock(type="text", text="hello"),
            ContentBlock(type="document", source_uri="x"),
        ],
    )
    assert message.role == "user"
    assert isinstance(message.content, list)
    assert len(message.content) == 2


def test_provider_response_fields() -> None:
    response = ProviderResponse(
        content="ok",
        model="test-model",
        input_tokens=12,
        output_tokens=24,
        latency_ms=17,
    )
    assert response.content == "ok"
    assert response.model == "test-model"
    assert response.input_tokens == 12
    assert response.output_tokens == 24
    assert response.latency_ms == 17


def test_provider_protocol_check() -> None:
    class _ProviderImpl:
        @property
        def provider_id(self) -> str:
            return "x"

        async def complete(
            self,
            messages: list[ProviderMessage],
            model: str,
            tools: list[ToolDefinition] | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.0,
            stream: bool = False,
        ) -> ProviderResponse | list[ProviderStreamChunk]:
            del messages, tools, max_tokens, temperature, stream
            return ProviderResponse(content="ok", model=model)

        async def health_check(self) -> ProviderHealth:
            return ProviderHealth(available=True)

        def supports_tool_use(self) -> bool:
            return True

        def supports_streaming(self) -> bool:
            return True

        def max_context_window(self, model: str) -> int:
            del model
            return 10

    assert isinstance(_ProviderImpl(), ModelProvider)

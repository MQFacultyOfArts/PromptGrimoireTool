---
source: https://openrouter.ai/docs/guides/community/pydantic-ai
fetched: 2026-02-23
library: openrouter
summary: Using pydantic-ai with OpenRouter via OpenAI-compatible interface
---

# PydanticAI with OpenRouter

## Setup

```bash
pip install 'pydantic-ai-slim[openai]'
```

PydanticAI integrates with OpenRouter through its OpenAI-compatible interface. Use `OpenAIModel` with the OpenRouter base URL.

## Basic Usage

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel

model = OpenAIModel(
    "anthropic/claude-3.5-sonnet",
    base_url="https://openrouter.ai/api/v1",
    api_key="sk-or-...",
)

agent = Agent(model)
result = await agent.run("What is the meaning of life?")
print(result)
```

## Key Points

- Model ID uses OpenRouter format: `provider/model-name` (e.g., `anthropic/claude-3.5-sonnet`, `openai/gpt-4o`, `google/gemini-2.0-flash`)
- Base URL: `https://openrouter.ai/api/v1`
- API key: OpenRouter key (`sk-or-...`)
- Streaming: Uses pydantic-ai's standard streaming interface (`run_stream_events()`)
- Thinking blocks: Arrive as `ThinkingPart`/`DeltaThinkingPart` events for models that support them
- Model switching: Create new `OpenAIModel` with different model ID, same base_url/api_key pattern

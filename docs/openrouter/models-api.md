---
source: https://openrouter.ai/docs/api-reference/models/get-models
fetched: 2026-02-23
library: openrouter
summary: List available models with pricing, capabilities, context length, and supported parameters
---

# OpenRouter Models API

## List Available Models

```
GET https://openrouter.ai/api/v1/models
```

No authentication required. Returns all available models.

### Response Fields (per model)

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Model identifier (e.g., `anthropic/claude-opus-4-6`) |
| `name` | string | Display name (e.g., "Anthropic: Claude Opus 4.6") |
| `context_length` | int | Max context window in tokens |
| `pricing.prompt` | string | Cost per prompt token in USD |
| `pricing.completion` | string | Cost per completion token in USD |
| `architecture.modality` | string | I/O modality (e.g., `text+image+file->text`) |
| `architecture.input_modalities` | array | Supported inputs: `text`, `image`, `file` |
| `architecture.output_modalities` | array | Supported outputs: `text` |
| `supported_parameters` | array | Supported params: `temperature`, `top_p`, `max_tokens`, etc. |
| `top_provider.max_completion_tokens` | int | Max completion tokens |
| `top_provider.is_moderated` | bool | Whether output is moderated |

### Example Response

```json
{
  "data": [
    {
      "id": "anthropic/claude-3.5-sonnet",
      "name": "Anthropic: Claude 3.5 Sonnet",
      "context_length": 200000,
      "pricing": {
        "prompt": "0.000003",
        "completion": "0.000015"
      },
      "architecture": {
        "modality": "text+image+file->text",
        "input_modalities": ["file", "image", "text"],
        "output_modalities": ["text"]
      },
      "supported_parameters": ["max_tokens", "temperature", "top_p", "tools"],
      "top_provider": {
        "max_completion_tokens": 8192,
        "is_moderated": false
      }
    }
  ]
}
```

### Usage for Model Allowlist

For the LLM Playground, the instructor configures an allowlist of model IDs per course. The UI fetches `/api/v1/models` to populate the model picker with display names, pricing, and capability info — filtered to only show models on the course allowlist.

Key fields for the allowlist UI:
- `id` — stored in course config
- `name` — shown in picker dropdown
- `pricing` — shown as cost indicator
- `context_length` — shown as context limit
- `architecture.input_modalities` — determines if file/image upload is enabled
- `supported_parameters` — determines which sliders/toggles to show

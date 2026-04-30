# Decisions

## Task 20: static/js/modules/init.js - ollama → litellm rename (2026-04-28)

**Decision:** Renamed ALL 12 occurrences of `ollama` to `litellm` in `static/js/modules/init.js`, including:
- `'ollama'` string literals → `'litellm'` (provider type comparisons)
- `ollamaUrl` variable name → `litellmUrl` (Phase 1 provider config)
- `phase2OllamaUrl` variable name → `phase2LitellmUrl` (Phase 2 provider config)
- `initOllamaInstancesHandlers()` function call → `initLitellmInstancesHandlers()`
- Comment `// Ollama Instances handlers` → `// Litellm Instances handlers`

**Rationale:** The `ollama` provider type is being replaced by `litellm` throughout the frontend. This file must be consistent with the rest of the provider system. The `initOllamaInstancesHandlers()` call must match whatever the function is named in `ollama-settings.js` — that file's function definition must also be renamed for the call to resolve at runtime.

**Note:** `ollama-settings.js` still exports `initOllamaInstancesHandlers` — the function name there MUST be renamed to `initLitellmInstancesHandlers` in a follow-up task, otherwise this init.js call will throw `ReferenceError: initLitellmInstancesHandlers is not defined`.

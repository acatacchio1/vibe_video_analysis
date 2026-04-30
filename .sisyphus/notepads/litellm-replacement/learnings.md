## Task 8: app.py init_providers cleanup

- Removed `discovery` import and all Ollama hardcoding (192.168.1.237, 192.168.1.241)
- Replaced `OllamaProvider` import with `LiteLLMProvider` from `providers.litellm`
- Collapsed `init_providers()` from ~70 lines to 7 lines: single LiteLLM provider + conditional OpenRouter
- Removed `get_loaded_ollama_models()` closure, `vram_manager.set_ollama_running_models_provider()`, `_get_monitor_ollama_url()`, `monitor.set_ollama_url_provider()`
- File went from 1849 lines to 1784 lines
- Verified: no OllamaProvider/discovery/hardcoded IP references remain, syntax compiles, import resolves

## Task 16: src/worker/pipelines/standard_two_step.py

- Replaced all `"ollama"` provider_type checks with `"litellm"` (5 locations: _synthesize_frame, run, _build_config x2, _save_results)
- Replaced all `OllamaClient` usage with `GenericOpenAIAPIClient` from video_analyzer library
- Removed entire OllamaClient patching blocks (functools.patch, encode_image, /api/chat) — no longer needed
- Changed all URL defaults from `192.168.1.237:11434` / `localhost:11434` to `172.16.17.3:4000/v1`
- Changed `_synthesize_frame` to use OpenAI-compatible `/chat/completions` endpoint with Bearer header (empty for litellm proxy)
- Updated `_build_config`: litellm path now uses `config_data["clients"]["openai_api"]` and `["phase2_openai_api"]` keys with `api_key`/`api_url` format (instead of `["ollama"]` with `url`)
- Renamed `"ollama_url"` → `"litellm_url"` in auto-LLM chat request dict in `_save_results`
- `GenericOpenAIAPIClient` now used in 3 client creation points: _analyze_frames x2, _reconstruct_video x2 (both litellm + openrouter)
- OpenRouter code paths remain completely untouched
- `video_analyzer` package LSP errors are pre-existing (package only available in Docker venv)
- File went from 1080 lines to 1018 lines (removed ~62 lines of OllamaClient patching code)

## Task 17: src/worker/pipelines/linkedin_extraction.py

- Replaced `provider_type == "ollama"` with `== "litellm"` in 3 locations: `_initialize_client`, `_call_llm_for_frame`, `_call_llm_for_fusion`
- Replaced `OllamaClient` import/usage with `GenericOpenAIAPIClient` from video_analyzer library
- Removed entire OllamaClient patching block (`functools.wraps`, `types.MethodType`, `/api/chat`) — ~40 lines of patching code eliminated
- Changed URL defaults from `localhost:11434` to `172.16.17.3:4000/v1`
- Changed `_call_llm_for_fusion` to use OpenAI-compatible `/chat/completions` endpoint with `Authorization: Bearer ` header (empty key for local proxy) + `resp.json()["choices"][0]["message"]["content"]` parsing
- Updated `_call_llm_for_frame` to use `max_tokens=4096` instead of `num_predict=4096`
- Removed unused `import types` (was only used for `types.MethodType` in old patching code)
- Changed default provider_type from `"ollama"` to `"litellm"` in `_call_llm_for_fusion` fallback
- OpenRouter code paths remain completely untouched
- `video_analyzer` package LSP errors are pre-existing (package only available in Docker venv)
- File went from 1269 lines to 1229 lines (net -40 lines removed)

## Task 22: static/js/modules/results.js

- Replaced all `'ollama'` type checks with `'litellm'` in `buildResultsDropdown()` function (lines 125-128)
- Changed `<optgroup label="Ollama">` to `<optgroup label="LiteLLM">`
- Changed `.filter(p => p.type === 'ollama')` to `.filter(p => p.type === 'litellm')`
- Changed `.map(p => <option value="ollama"...` to `.map(p => <option value="litellm"...`
- OpenRouter handling completely untouched
- Grep verified: zero remaining `ollama` references in results.js

## Plan File Cleanup

- Removed duplicate T20 and T21 task blocks from plan (accidental duplication from prior edit tool usage)
- Marked T22 checkbox as `[x]` after code changes were completed

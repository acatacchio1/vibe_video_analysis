## Task 15: Update src/cli/api_client.py

### Completed Changes
- Renamed `get_ollama_instances` → `get_litellm_status` (line 181)
- Changed URL to `/api/providers/litellm/models` (line 182)
- Deleted `update_ollama_instances` method entirely (was lines 185-191)

### Notes
- 4 remaining `ollama` references exist: `get_ollama_models` (line 185) and `ollama_url` param in `submit_chat` (line 235)
- These were NOT part of Task 15 scope
- Callers of deleted methods (`get_ollama_instances`, `update_ollama_instances`) exist in `src/cli/commands/providers.py` — likely addressed by another task
- `get_litellm_status` currently has no callers in codebase (likely to be wired by a follow-up task)

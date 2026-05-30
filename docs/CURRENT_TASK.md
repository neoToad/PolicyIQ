# Current Task

**Step 4.4 — LLM Config Swap**

Adding a configurable LLM backend so PolicyIQ can switch between Ollama (local, free) and Anthropic API (production demo) with a single settings change.

- Add `LLM_BACKEND` setting (`ollama` or `anthropic`) and `ANTHROPIC_API_KEY` from env
- Update `queries/services/generator.py` to route based on `LLM_BACKEND`
- Build Anthropic streaming generator using `claude-sonnet-4-20250514`
- Both backends consume the same `build_prompt()` output and yield streamed tokens
- Writing tests first per TDD workflow

Next: 4.5 — README.

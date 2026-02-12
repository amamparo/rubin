# Rubin — Audio Evaluation MCP Server

## Commands
- `just install` — install dependencies via Poetry
- `just check` — lint + test
- `just fmt` — auto-format with Black
- `just lint` — check formatting (Black) and linting (Ruff)
- `just test` — run pytest
- `poetry run pytest tests/test_foo.py::test_bar` — run a single test

## Architecture

**MCP Server** (`src/rubin/`):
- `server.py` — FastMCP server factory, DI setup, all MCP tool definitions
- `client.py` — `AudioClient` ABC + backends (SystemAudioClient, TcpAudioClient, StdinAudioClient)
- `analyzer.py` — librosa-based feature extraction (spectral, timbral, loudness, stereo)
- `evaluator.py` — scores audio against style profiles, flags issues, suggests fixes
- `__main__.py` — CLI entrypoint, calls `mcp.run()`

**Style Profiles** (`styles/`):
- JSON configs defining target ranges for frequency balance, dynamics, brightness, etc.
- e.g. `ambient.json`, `synthpop.json`

## Dependency Injection
- `injector` is used to decouple tool handlers from concrete implementations
- `AudioModule` binds `AudioClient` to the selected backend
- `create_server()` accepts an optional `Injector` for test swapping
- Tests inject a `FakeAudioClient` via `FakeAudioModule`

## Testing
- Tests use `@pytest.mark.anyio` for async
- Call tools via `mcp_server.call_tool(name, args)`
- `FakeAudioClient` in `tests/conftest.py` provides canned audio buffers
- Parse results from `content[0].text` via `json.loads`

## Code Style
- Python 3.12+
- Black (88 chars), Ruff (E/F/I/W)
- Keep tool surface small and composable

# Native Lean Workflow Note

The old managed autoformalize backend design is retired for the maintained OpenGauss path.

Current contract:

- `/prove`, `/autoprove`, `/formalize`, and `/autoformalize` run through the native OpenGauss Lean workflow runner.
- The native runner uses `openai-codex:gpt-5.5` with `api_mode="codex_responses"`.
- The workflow toolset is `opengauss-lean`, which combines file tools, AXLE tools, and controlled local Lean project operations.
- External clients may use `gauss mcp-server`, but MCP tools are adapters over the same Python services and are not the canonical harness path.
- FormalQualBench calls the native runner directly and records `mcp_call_count = 0`.

Historical external CLI launchers are not maintained as OpenGauss workflow lanes.

# agent_kernel (MCP-only)

`agent_kernel` is an importable facade for the protocol kernel and MCP runtime.

## What is exported

- `append_phase`, `build_step_record`, `compose_verify_summary`, `dedupe_insights`, `derive_final_answer`
- `ProtocolAgentRunner`, `ProtocolRunnerDeps`
- `MCPWidgetRuntime`, `RuntimeSnapshot`

## Minimal usage

```python
from packages.agent_kernel import RuntimeSnapshot, MCPWidgetRuntime
```

For an executable example, run:

```bash
python examples/package_import_demo.py
```

## Scope

- This package is MCP-only by design.
- Main project runtime path is intentionally unchanged.

# widget_sdk host integration

`widget_sdk` is the host-facing analysis capability package for widget-centric VA integration.

## What hosts should use

- Request contract: `AnalysisRequest`
- Result contract: `AnalysisResult`
- Headless entrypoint: `analyze_widget(request)`
- Session entrypoint: `start_widget_session(request)`
- Plugin entrypoint: `register_plugin(...)`

This keeps host integrations focused on a stable contract instead of internal runner details.

## Minimal usage

```python
from packages.widget_sdk import AnalysisRequest, analyze_widget

request = AnalysisRequest(
    query="Summarize the main trend in this chart.",
    vega_spec=my_vega_spec,
)

result = await analyze_widget(request)
print(result.answer)
```

## Contract notes

- `AnalysisRequest.vega_spec` is the primary widget state carrier.
- `chart_type` is optional. If omitted, the SDK infers it from `vega_spec`.
- `model_name` is optional. If omitted, backend uses default `gpt_protocol`.
- `request_id` is always present in `AnalysisResult` for host-side tracing.
- `metadata` is pass-through context for host systems.

## Extensibility

Hosts can register custom chart tools via:

- `tools.registration_api.register_tool(...)`
- `tools.registration_api.register_widget_tool(...)`
- `packages.widget_sdk.plugins.register_plugin(...)`

## Session usage

```python
from packages.widget_sdk import (
    SessionStartRequest,
    SessionContinueRequest,
    start_widget_session,
)

session = await start_widget_session(
    SessionStartRequest(
        vega_spec=my_vega_spec,
    )
)

step = await session.continue_analysis(
    SessionContinueRequest(
        session_id=session.session_id,
        query="Focus on outliers and explain why they matter.",
    )
)

await session.close()
print(step.answer)
```


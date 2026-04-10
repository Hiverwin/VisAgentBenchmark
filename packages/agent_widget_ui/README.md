# @agentic-visual-reframe/agent-widget-ui

Embeddable React UI package for host VA systems.

## Install

```bash
npm install @agentic-visual-reframe/agent-widget-ui
```

## Minimal usage

```tsx
import { AgentWidget } from "@agentic-visual-reframe/agent-widget-ui";

export function RightPanel() {
  return (
    <AgentWidget
      apiBaseUrl="https://your-agent-service.example.com"
      vegaSpec={{
        $schema: "https://vega.github.io/schema/vega-lite/v5.json",
        mark: "point",
        encoding: {
          x: { field: "x", type: "quantitative" },
          y: { field: "y", type: "quantitative" }
        },
        data: { values: [{ x: 1, y: 2 }, { x: 2, y: 4 }] }
      }}
    />
  );
}
```

## Host responsibilities

- Provide `apiBaseUrl` to a service exposing `/api/analyze`.
- Provide current widget state as `vegaSpec`.
- Optionally pass `modelName` when backend exposes model override.
- Optionally inject auth token with `getAuthToken()`.


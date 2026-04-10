import React, { useMemo, useState } from "react";
import { useAgentAnalysis } from "./useAgentAnalysis";
import type { AgentWidgetTheme, AnalyzeRequest, AnalyzeResponse } from "./types";

export type AgentWidgetProps = {
  apiBaseUrl: string;
  vegaSpec: Record<string, unknown>;
  modelName?: string;
  defaultQuery?: string;
  inputMode?: string;
  maxIterations?: number;
  chartType?: string;
  metadata?: Record<string, unknown>;
  getAuthToken?: () => string | undefined | Promise<string | undefined>;
  theme?: AgentWidgetTheme;
  onResult?: (result: AnalyzeResponse) => void;
  onError?: (error: string) => void;
  className?: string;
};

export function AgentWidget(props: AgentWidgetProps) {
  const [query, setQuery] = useState(props.defaultQuery ?? "Summarize key insights from this chart.");
  const { loading, error, result, analyze } = useAgentAnalysis({
    apiBaseUrl: props.apiBaseUrl,
    getAuthToken: props.getAuthToken
  });

  const styles = useMemo(
    () => ({
      border: `1px solid ${props.theme?.borderColor ?? "#e2e8f0"}`,
      background: props.theme?.panelBackground ?? "#ffffff",
      color: props.theme?.textColor ?? "#0f172a"
    }),
    [props.theme]
  );

  const run = async () => {
    const payload: AnalyzeRequest = {
      query,
      vega_spec: props.vegaSpec,
      model_name: props.modelName,
      input_mode: props.inputMode ?? "text_and_image",
      max_iterations: props.maxIterations ?? 6,
      chart_type: props.chartType,
      metadata: props.metadata ?? {}
    };
    try {
      const response = await analyze(payload);
      props.onResult?.(response);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown widget error.";
      props.onError?.(message);
    }
  };

  return (
    <section className={props.className} style={{ ...styles, borderRadius: 10, padding: 12 }}>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Agent Widget</div>
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        rows={4}
        style={{
          width: "100%",
          border: "1px solid #cbd5e1",
          borderRadius: 8,
          padding: 8,
          fontSize: 13
        }}
      />
      <button
        type="button"
        onClick={run}
        disabled={loading}
        style={{
          marginTop: 8,
          border: "none",
          borderRadius: 8,
          padding: "8px 12px",
          cursor: loading ? "not-allowed" : "pointer",
          background: props.theme?.accentColor ?? "#2563eb",
          color: "#fff",
          fontWeight: 600
        }}
      >
        {loading ? "Running..." : "Run Analysis"}
      </button>

      {error ? (
        <pre style={{ marginTop: 10, color: "#b91c1c", whiteSpace: "pre-wrap", fontSize: 12 }}>{error}</pre>
      ) : null}

      {result ? (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontWeight: 600, fontSize: 13 }}>Answer</div>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{result.answer}</pre>
          <div style={{ fontWeight: 600, fontSize: 13, marginTop: 8 }}>Tool Calls</div>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
            {JSON.stringify(result.tool_calls, null, 2)}
          </pre>
        </div>
      ) : null}
    </section>
  );
}


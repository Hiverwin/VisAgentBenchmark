import { useCallback, useMemo, useState } from "react";
import type { AnalyzeRequest, AnalyzeResponse } from "./types";

type UseAgentAnalysisOptions = {
  apiBaseUrl: string;
  endpoint?: string;
  getAuthToken?: () => string | undefined | Promise<string | undefined>;
};

export function useAgentAnalysis(options: UseAgentAnalysisOptions) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string>("");

  const endpoint = useMemo(
    () => `${options.apiBaseUrl.replace(/\/$/, "")}${options.endpoint ?? "/api/analyze"}`,
    [options.apiBaseUrl, options.endpoint]
  );

  const analyze = useCallback(
    async (payload: AnalyzeRequest) => {
      setLoading(true);
      setError("");
      try {
        const token = options.getAuthToken ? await options.getAuthToken() : undefined;
        const headers: Record<string, string> = {
          "Content-Type": "application/json"
        };
        if (token) headers.Authorization = `Bearer ${token}`;

        const response = await fetch(endpoint, {
          method: "POST",
          headers,
          body: JSON.stringify(payload)
        });
        const json = (await response.json()) as AnalyzeResponse & { detail?: string };
        if (!response.ok) {
          throw new Error(json.detail ?? json.error ?? "Analyze request failed.");
        }
        setResult(json);
        return json;
      } catch (e) {
        const message = e instanceof Error ? e.message : "Unknown analyze error.";
        setError(message);
        throw e;
      } finally {
        setLoading(false);
      }
    },
    [endpoint, options]
  );

  return {
    loading,
    result,
    error,
    analyze,
    clearResult: () => setResult(null)
  };
}


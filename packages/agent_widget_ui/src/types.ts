export type AnalyzeRequest = {
  query: string;
  vega_spec: Record<string, unknown>;
  model_name?: string;
  input_mode?: string;
  max_iterations?: number;
  chart_type?: string;
  session_id?: string;
  metadata?: Record<string, unknown>;
  request_id?: string;
};

export type AnalyzeResponse = {
  request_id: string;
  query: string;
  success: boolean;
  answer: string;
  tool_calls: Array<Record<string, unknown>>;
  final_observation: Record<string, unknown>;
  chart_type: string;
  mode: string;
  error?: string;
  stop_reason?: string;
  metadata?: Record<string, unknown>;
};

export type AgentWidgetTheme = {
  borderColor?: string;
  panelBackground?: string;
  textColor?: string;
  accentColor?: string;
};


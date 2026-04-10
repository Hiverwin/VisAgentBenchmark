# Intent Grounding Reference (Offline-Mined)

This document is distilled from benchmark tasks. It is an offline artifact used to improve intent grounding.
It is NOT for online benchmark retrieval.

## Dataset Coverage
- clear_multi/type3
- clear_single/type3
- vague_single/type1a
- vague_multi/type1a
- Total mined question-level samples: 542

## Stable Latent Intent Taxonomy
- rank_dominance: identify highest/lowest/top-k/leader
- pairwise_compare_gap: compare A vs B, quantify or qualify the gap
- relationship_strength: detect/quantify association or correlation
- composition_mix: compare internal composition or contribution shares
- time_local_change: locate period-level changes, turning points, local anomalies
- outlier_hotspot: detect extremes, anomalies, hotspots
- flow_path_conversion: trace paths, bottlenecks, conversion/efficiency
- subgroup_slice: analyze behavior under a subset/cohort condition

## Intent Normalization Rules
- Normalize user wording before tool selection.
- "compare A and B" is ambiguous; map to one of:
  - who is higher/lower (rank_dominance)
  - how large is the gap (pairwise_compare_gap)
  - how compositions differ (composition_mix)
- "relationship" can mean correlation, subgroup separation, or overlap structure.
  Resolve with chart affordance and requested evidence type.
- "what stands out" can mean outlier/hotspot or dominance ranking.
- If multiple incompatible intents remain and no safe default exists, ask clarification.

## Alignment Policy (Avoid Overfitting)
- Define intent by user information need, not by tool names in text.
- Use tool trace only as posterior validation.
- For vague tasks that include tool hints, discount the hint and recover the analytic goal first.
- Prefer a small stable intent set over many brittle micro-intents.

## Chart-Aware Toolchain Priors (Preferred -> Fallback)
- Bar
  - rank_dominance: sort_bars -> highlight_top_n/filter_categories
  - pairwise_compare_gap: filter_categories + sort_bars -> toggle_stack_mode
  - composition_mix: toggle_stack_mode/expand_stack -> filter_categories
- Scatter
  - relationship_strength: calculate_correlation -> show_regression + zoom_2d_region
  - subgroup_slice: filter_categorical + calculate_correlation -> zoom_2d_region
  - overlap_structure: identify_clusters/zoom_2d_region -> brush_region/select_region
- Line
  - time_local_change: zoom_x_region + filter_lines -> detect_anomalies
  - pairwise_compare_gap: filter_lines + zoom_x_region -> show_moving_average
  - trend_robustness: resample_x_axis -> drill_down_x_axis
- Parallel
  - subgroup_slice: filter_by_category -> hide_dimensions
  - relationship_strength: reorder_dimensions + highlight_category -> hide_dimensions
  - profile_anomaly: highlight_category + reorder_dimensions -> filter_by_category
- Heatmap
  - rank_dominance/outlier_hotspot: filter_cells_by_region/find_extremes -> highlight_region_by_value
  - pairwise_compare_gap: filter_cells_by_region + get_data_summary -> highlight_region
  - structure_discovery: cluster_rows_cols + select_submatrix -> transpose
- Sankey
  - flow_path_conversion: calculate_conversion_rate/collapse_nodes -> trace_node
  - path_attribution: trace_node/highlight_path -> filter_flow
  - bottleneck_leakage: filter_flow + find_bottleneck/calculate_conversion_rate -> trace_node

## Online Runtime Principle
- Online model should only use distilled rules/templates in prompts.
- Do not retrieve benchmark tasks at inference time.

## Objective Questions: Interaction-First Bias
- For objective exact-value queries, prefer interaction tools that expose the answer on chart before raw table retrieval.
- Treat `get_data` / `get_data_summary` as fallback, not default first step, unless:
  - the requested value is not visually retrievable after reasonable interaction, or
  - the task explicitly asks for aggregate summary output.
- High-priority examples:
  - Sankey node amount / redirected count -> `calculate_conversion_rate`
  - Line quarter average -> `resample_x_axis(granularity=quarter)`
  - Bar stacked-segment exact value -> `expand_stack` then read from view

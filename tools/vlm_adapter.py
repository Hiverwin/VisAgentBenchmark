"""
Convert registered tools to OpenAI / Anthropic function-calling schemas.

Fixes applied:
- array types include ``items`` (OpenAI requirement)
- object types include ``additionalProperties`` where needed
- ``vega_spec`` / ``state`` are stripped from exported schemas
"""

from typing import Dict, List, Any, Optional
from .tool_registry import tool_registry
from config.chart_types import ChartType


class VLMToolAdapter:
    """Adapters between ToolRegistry and various LLM tool formats."""

    def __init__(self):
        self.registry = tool_registry

    def to_openai_format(self, chart_type: Optional[ChartType] = None) -> List[Dict[str, Any]]:
        """
        Export tools as OpenAI ``chat.completions`` function definitions.

        Args:
            chart_type: If set, only tools for this chart type.

        Returns:
            List of ``{"type": "function", "function": {...}}`` objects.
        """
        tools = []

        if chart_type:
            tool_names = self.registry.list_tools_for_chart(chart_type)
        else:
            tool_names = self.registry.list_all_tools()

        for tool_name in tool_names:
            tool_info = self.registry.get_tool(tool_name)
            if not tool_info:
                continue

            params_schema = self._convert_params_to_json_schema(tool_info['params'])

            for key in ('vega_spec', 'state'):
                if 'properties' in params_schema and key in params_schema['properties']:
                    del params_schema['properties'][key]
                if 'required' in params_schema and key in params_schema['required']:
                    params_schema['required'].remove(key)

            self._fix_schema_types(params_schema)

            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_info['description'],
                    "parameters": params_schema
                }
            }
            tools.append(openai_tool)

        return tools

    def _fix_schema_types(self, schema: Dict[str, Any]) -> None:
        """
        Ensure JSON Schema arrays have ``items`` and objects are valid.

        Args:
            schema: Parameter schema dict (mutated in place).
        """
        if 'properties' not in schema:
            return

        for prop_name, prop_def in schema['properties'].items():
            prop_type = prop_def.get('type')

            if prop_type == 'array' and 'items' not in prop_def:
                if any(keyword in prop_name.lower() for keyword in ['range', 'position', 'point', 'coord', 'size', 'extent']):
                    prop_def['items'] = {"type": "number"}
                elif any(keyword in prop_name.lower() for keyword in ['name', 'label', 'category', 'field', 'column']):
                    prop_def['items'] = {"type": "string"}
                else:
                    prop_def['items'] = {"type": "number"}

            elif prop_type == 'object':
                if 'properties' not in prop_def and 'additionalProperties' not in prop_def:
                    prop_def['additionalProperties'] = True

    def to_anthropic_format(self, chart_type: Optional[ChartType] = None) -> List[Dict[str, Any]]:
        """Export tools for Anthropic tool_use."""
        tools = []

        if chart_type:
            tool_names = self.registry.list_tools_for_chart(chart_type)
        else:
            tool_names = self.registry.list_all_tools()

        for tool_name in tool_names:
            tool_info = self.registry.get_tool(tool_name)
            if not tool_info:
                continue

            params_schema = self._convert_params_to_json_schema(tool_info['params'])

            for key in ('vega_spec', 'state'):
                if 'properties' in params_schema and key in params_schema['properties']:
                    del params_schema['properties'][key]
                if 'required' in params_schema and key in params_schema['required']:
                    params_schema['required'].remove(key)

            self._fix_schema_types(params_schema)

            anthropic_tool = {
                "name": tool_name,
                "description": tool_info['description'],
                "input_schema": params_schema
            }
            tools.append(anthropic_tool)

        return tools

    def to_generic_format(self, chart_type: Optional[ChartType] = None) -> List[Dict[str, Any]]:
        """Plain dicts suitable for prompt text."""
        tools = []

        if chart_type:
            tool_names = self.registry.list_tools_for_chart(chart_type)
        else:
            tool_names = self.registry.list_all_tools()

        for tool_name in tool_names:
            tool_info = self.registry.get_tool(tool_name)
            if not tool_info:
                continue

            params_desc = []
            for param_name, param_spec in tool_info['params'].items():
                if param_name in ('vega_spec', 'state'):
                    continue

                param_type = param_spec.get('type', 'any')
                required = param_spec.get('required', False)
                default = param_spec.get('default', 'N/A')

                param_str = f"  - {param_name} ({param_type})"
                if required:
                    param_str += " [REQUIRED]"
                elif default != 'N/A':
                    param_str += f" [default={default}]"

                params_desc.append(param_str)

            tool_desc = {
                "name": tool_name,
                "category": tool_info.get('category', 'unknown'),
                "description": tool_info['description'],
                "parameters": "\n".join(params_desc) if params_desc else "No parameters"
            }
            tools.append(tool_desc)

        return tools

    def to_prompt_string(self, chart_type: Optional[ChartType] = None) -> str:
        """Single markdown string for models without native tools."""
        tools = self.to_generic_format(chart_type)

        prompt_parts = ["# Available Tools\n"]

        categories = {}
        for tool in tools:
            cat = tool['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(tool)

        for category, cat_tools in categories.items():
            prompt_parts.append(f"\n## {category.upper()} Tools\n")

            for tool in cat_tools:
                prompt_parts.append(f"\n### {tool['name']}")
                prompt_parts.append(f"\n{tool['description']}")
                prompt_parts.append(f"\n**Parameters:**\n{tool['parameters']}\n")

        prompt_parts.append("\n## Tool Usage Format\n")
        prompt_parts.append("To use a tool, respond with JSON in this format:\n")
        prompt_parts.append("```json\n")
        prompt_parts.append('{\n')
        prompt_parts.append('  "tool": "tool_name",\n')
        prompt_parts.append('  "params": {\n')
        prompt_parts.append('    "param1": "value1",\n')
        prompt_parts.append('    "param2": "value2"\n')
        prompt_parts.append('  },\n')
        prompt_parts.append('  "reason": "Why you are calling this tool"\n')
        prompt_parts.append('}\n')
        prompt_parts.append("```\n")

        return "".join(prompt_parts)

    def _convert_params_to_json_schema(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Build JSON Schema ``properties`` / ``required`` from registry param specs."""
        properties = {}
        required = []

        for param_name, param_spec in params.items():
            if param_name in ('vega_spec', 'state'):
                continue

            param_type = param_spec.get('type', 'string')

            type_mapping = {
                'str': 'string',
                'string': 'string',
                'int': 'integer',
                'integer': 'integer',
                'float': 'number',
                'number': 'number',
                'bool': 'boolean',
                'boolean': 'boolean',
                'list': 'array',
                'array': 'array',
                'dict': 'object',
                'object': 'object',
                'tuple': 'array',
                'any': 'string'
            }

            json_type = type_mapping.get(param_type, 'string')

            prop_def = {
                "type": json_type,
                "description": param_spec.get('description', f"{param_name} parameter")
            }

            if json_type == 'array':
                item_type = param_spec.get('item_type', param_spec.get('items_type', 'number'))
                item_type_mapping = {
                    'str': 'string',
                    'string': 'string',
                    'int': 'integer',
                    'integer': 'integer',
                    'float': 'number',
                    'number': 'number',
                    'bool': 'boolean',
                    'boolean': 'boolean'
                }
                prop_def['items'] = {
                    "type": item_type_mapping.get(item_type, 'number')
                }

            if json_type == 'object':
                prop_def['additionalProperties'] = True

            if 'default' in param_spec:
                prop_def['default'] = param_spec['default']

            if 'enum' in param_spec:
                prop_def['enum'] = param_spec['enum']

            properties[param_name] = prop_def

            if param_spec.get('required', False):
                required.append(param_name)

        schema = {
            "type": "object",
            "properties": properties
        }

        if required:
            schema["required"] = required

        return schema

    def generate_tool_execution_guide(self) -> str:
        """Long-form markdown guide for agents."""
        guide = """
# Tool Execution Guide

## Overview
This system provides interactive tools for visual analysis. All tools operate on Vega-Lite specifications.

## Core Principles

1. **Tools are automatically connected to the visualization**: You don't need to pass vega_spec, it's handled automatically
2. **Tools return updated state**: Action tools return an updated visualization
3. **Tools are composable**: You can chain multiple tool calls in sequence

## Tool Categories

### Perception Tools
These tools READ the current state:
- `get_data_summary`: Get statistical summary of data
- `get_tooltip_data`: Get data at specific position

### Action Tools  
These tools MODIFY the visualization:
- `zoom`: Zoom to a specific area
- `filter`: Filter data by dimension
- `brush`: Select/brush an area
- `change_encoding`: Change visual encoding
- `highlight`: Highlight specific categories
- `render_chart`: Render the visualization

### Analysis Tools
These tools ANALYZE patterns:
- `identify_clusters`: Find clusters in scatter plots
- `calculate_correlation`: Calculate correlation

## Usage Pattern

1. **Understand the task**: Parse user query
2. **Plan tool usage**: Decide which tools to use
3. **Execute tools**: Call tools with proper parameters
4. **Interpret results**: Analyze tool outputs
5. **Respond to user**: Provide insights based on results

## Example Workflow

```python
# 1. Get data summary to understand the data
result = get_data_summary(scope='all')

# 2. Identify interesting patterns
clusters = identify_clusters(n_clusters=3)

# 3. Highlight findings
updated = highlight(category='cluster_0')

# 4. Return insights to user
```

## Error Handling

- Always check tool result['success']
- If a tool fails, try alternative approaches
- Validate parameters before calling tools
"""
        return guide

    def validate_tools(self) -> List[str]:
        """Return human-readable schema errors, if any."""
        errors = []
        tools = self.to_openai_format()

        for tool in tools:
            func = tool.get('function', {})
            name = func.get('name', 'unknown')
            params = func.get('parameters', {})

            if 'properties' in params:
                for prop_name, prop_def in params['properties'].items():
                    prop_type = prop_def.get('type')

                    if prop_type == 'array' and 'items' not in prop_def:
                        errors.append(
                            f"Tool '{name}' param '{prop_name}' is array but missing 'items'"
                        )

                    if prop_type == 'object':
                        if 'properties' not in prop_def and 'additionalProperties' not in prop_def:
                            errors.append(
                                f"Tool '{name}' param '{prop_name}' is object but missing "
                                f"properties or additionalProperties"
                            )

        return errors


vlm_adapter = VLMToolAdapter()


def validate_all_tools() -> bool:
    """Print validation result; return True if no issues."""
    errors = vlm_adapter.validate_tools()
    if errors:
        print("Tool schema validation failed:")
        for error in errors:
            print(f"  - {error}")
        return False
    print("All tool schemas validated.")
    return True

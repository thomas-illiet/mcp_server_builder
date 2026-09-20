> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# namespace

# `fastmcp.server.transforms.namespace`

Namespace transform for prefixing component names.

## Classes

### `Namespace` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/transforms/namespace.py#L28" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

Prefixes component names with a namespace.

* Tools: name → namespace\_name
* Prompts: name → namespace\_name
* Resources: protocol://path → protocol://namespace/path
* Resource Templates: same as resources

**Methods:**

#### `list_tools` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/transforms/namespace.py#L97" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
list_tools(self, tools: Sequence[Tool]) -> Sequence[Tool]
```

Prefix tool names with namespace.

#### `get_tool` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/transforms/namespace.py#L103" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_tool(self, name: str, call_next: GetToolNext) -> Tool | None
```

Get tool by namespaced name.

#### `list_resources` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/transforms/namespace.py#L119" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
list_resources(self, resources: Sequence[Resource]) -> Sequence[Resource]
```

Add namespace path segment to resource URIs.

#### `get_resource` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/transforms/namespace.py#L126" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_resource(self, uri: str, call_next: GetResourceNext) -> Resource | None
```

Get resource by namespaced URI.

#### `list_resource_templates` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/transforms/namespace.py#L146" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
list_resource_templates(self, templates: Sequence[ResourceTemplate]) -> Sequence[ResourceTemplate]
```

Add namespace path segment to template URIs.

#### `get_resource_template` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/transforms/namespace.py#L155" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_resource_template(self, uri: str, call_next: GetResourceTemplateNext) -> ResourceTemplate | None
```

Get resource template by namespaced URI.

#### `list_prompts` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/transforms/namespace.py#L177" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
list_prompts(self, prompts: Sequence[Prompt]) -> Sequence[Prompt]
```

Prefix prompt names with namespace.

#### `get_prompt` <sup><a href="https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/transforms/namespace.py#L183" target="_blank"><Icon icon="github" style="width: 14px; height: 14px;" /></a></sup>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
get_prompt(self, name: str, call_next: GetPromptNext) -> Prompt | None
```

Get prompt by namespaced name.

> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Form Input

> Collect structured data from users via Pydantic models

export const VersionBadge = ({version}) => {
  return <Badge stroke size="lg" icon="gift" iconType="regular" className="version-badge">
            New in version <code>{version}</code>
        </Badge>;
};

<VersionBadge version="3.2.0" />

`FormInput` generates a validated form from a Pydantic model. The user fills it out, and the submission is validated against the model before being returned. Structured elicitation that can't be hallucinated.

<Frame>
  <img src="https://mintcdn.com/fastmcp/qxtzRAUiJsjdoWFw/apps/images/app-form.png?fit=max&auto=format&n=qxtzRAUiJsjdoWFw&q=85&s=57b5ffa624312117018e5feefbf6d901" alt="The FormInput provider shown in Goose, with a bug report form" width="2142" height="1830" data-path="apps/images/app-form.png" />
</Frame>

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
from typing import Literal

from pydantic import BaseModel, Field
from fastmcp import FastMCP
from fastmcp.apps.form import FormInput

class BugReport(BaseModel):
    title: str = Field(description="Brief summary")
    severity: Literal["low", "medium", "high", "critical"]
    description: str = Field(
        description="Detailed description",
        json_schema_extra={"ui": {"type": "textarea"}},
    )

mcp = FastMCP("My Server")
mcp.add_provider(FormInput(model=BugReport))
```

This registers two tools:

| Tool                | Visibility | Purpose                                |
| ------------------- | ---------- | -------------------------------------- |
| `collect_bugreport` | Model      | Opens the form UI                      |
| `submit_form`       | App only   | Validates and processes the submission |

The tool name is derived from the model class name, lowercased: `collect_{modelname}`. So `BugReport` becomes `collect_bugreport`, `ShippingAddress` becomes `collect_shippingaddress`. Use `tool_name` to override if needed. The LLM calls it with a prompt explaining what it needs, and the user gets a form with fields matching the model.

## Field mapping

`FormInput` uses Prefab's `Form.from_model()`, which maps Pydantic types to form components:

| Python type     | Form component  |
| --------------- | --------------- |
| `str`           | Text input      |
| `int`, `float`  | Number input    |
| `bool`          | Checkbox        |
| `datetime.date` | Date picker     |
| `Literal[...]`  | Select dropdown |
| `SecretStr`     | Password input  |

Use `Field()` metadata to control labels (`title`), placeholders (`description`), and validation (`min_length`, `max_length`, `ge`, `le`). Use `json_schema_extra={"ui": {"type": "textarea"}}` for multiline text.

## Callback

By default, the validated model is returned as JSON. Provide an `on_submit` callback to process the data server-side:

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
def save_report(report: BugReport) -> str:
    db.insert(report.model_dump())
    return f"Bug #{db.last_id} filed: {report.title}"

mcp.add_provider(FormInput(model=BugReport, on_submit=save_report))
```

The callback receives a validated model instance and returns a string that becomes the tool result.

## Configuration

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
FormInput(
    model=BugReport,             # Required: the Pydantic model
    name="BugTracker",           # App name (default: model name)
    title="File a Bug",          # Card heading (default: model name)
    tool_name="file_bug",        # Tool name (default: collect_{model})
    submit_text="Submit Report", # Button label (default: "Submit")
    on_submit=save_report,       # Optional callback
    send_message=True,           # Push result as a chat message
)
```

Set `send_message=True` to push the result back into the conversation via `SendMessage`, triggering the LLM's next turn. Without it, the result is just the tool return value.

## Multiple forms

Add multiple providers for different models — each gets its own tool:

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
mcp = FastMCP(
    "My Server",
    providers=[
        FormInput(model=ShippingAddress),
        FormInput(model=BugReport),
        FormInput(model=ContactInfo),
    ],
)
```

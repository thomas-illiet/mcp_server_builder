> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Examples

> Example apps you can run right now.

export const VersionBadge = ({version}) => {
  return <Badge stroke size="lg" icon="gift" iconType="regular" className="version-badge">
            New in version <code>{version}</code>
        </Badge>;
};

<VersionBadge version="3.2.0" />

Each tile below is a working FastMCP server you can run with `fastmcp dev apps` or connect to from any MCP host. Source lives in `examples/apps/` in the repository.

<Columns cols={2}>
  <Tile href="#sales-dashboard" title="Sales Dashboard" description="Metrics, charts, and deal pipeline">
    <div style={{overflow: "hidden", width: "100%"}}>
      <img src="https://mintcdn.com/fastmcp/qxtzRAUiJsjdoWFw/apps/images/app-example-sales-dashboard.png?fit=max&auto=format&n=qxtzRAUiJsjdoWFw&q=85&s=49c0933bc736b3ed5ca422571ca0bcb9" width="2784" height="1830" data-path="apps/images/app-example-sales-dashboard.png" />
    </div>
  </Tile>

  <Tile href="#system-monitor" title="System Monitor" description="Live CPU, memory, disk with auto-refresh">
    <img src="https://mintcdn.com/fastmcp/qxtzRAUiJsjdoWFw/apps/images/app-example-system-dashboard.png?fit=max&auto=format&n=qxtzRAUiJsjdoWFw&q=85&s=2ee8939c549618735dcfd78601976b68" width="2784" height="1830" data-path="apps/images/app-example-system-dashboard.png" />
  </Tile>

  <Tile href="#quiz" title="Quiz" description="LLM-generated trivia with scoring">
    <img src="https://mintcdn.com/fastmcp/qxtzRAUiJsjdoWFw/apps/images/app-example-quiz.png?fit=max&auto=format&n=qxtzRAUiJsjdoWFw&q=85&s=774d6875cdcbb885b316e6a7f240b91c" width="2206" height="1830" data-path="apps/images/app-example-quiz.png" />
  </Tile>

  <Tile href="#interactive-map" title="Interactive Map" description="Geocoded addresses on Leaflet">
    <img src="https://mintcdn.com/fastmcp/qxtzRAUiJsjdoWFw/apps/images/app-example-map.png?fit=max&auto=format&n=qxtzRAUiJsjdoWFw&q=85&s=2d91bcba86a78d73985fec8354a4fc10" width="2206" height="1778" data-path="apps/images/app-example-map.png" />
  </Tile>

  <Tile href="/apps/providers/file-upload" title="File Upload" description="Drag-and-drop upload provider">
    <img src="https://mintcdn.com/fastmcp/qxtzRAUiJsjdoWFw/apps/images/app-file-upload.png?fit=max&auto=format&n=qxtzRAUiJsjdoWFw&q=85&s=844653a18265bbf6fa4c74be254cc8bd" width="2104" height="1824" data-path="apps/images/app-file-upload.png" />
  </Tile>

  <Tile href="/apps/providers/approval" title="Approval" description="Human-in-the-loop confirmation">
    <img src="https://mintcdn.com/fastmcp/qxtzRAUiJsjdoWFw/apps/images/app-approval.png?fit=max&auto=format&n=qxtzRAUiJsjdoWFw&q=85&s=a7612b699f039f04ddf85690e46d6695" width="2142" height="1830" data-path="apps/images/app-approval.png" />
  </Tile>

  <Tile href="/apps/providers/choice" title="Choice" description="Clickable option selection">
    <img src="https://mintcdn.com/fastmcp/qxtzRAUiJsjdoWFw/apps/images/app-choice.png?fit=max&auto=format&n=qxtzRAUiJsjdoWFw&q=85&s=254e3d7ebaca6ec7b24cdccb5caa9999" width="2142" height="1704" data-path="apps/images/app-choice.png" />
  </Tile>

  <Tile href="/apps/providers/form" title="Form Input" description="Pydantic model forms">
    <img src="https://mintcdn.com/fastmcp/qxtzRAUiJsjdoWFw/apps/images/app-form.png?fit=max&auto=format&n=qxtzRAUiJsjdoWFw&q=85&s=57b5ffa624312117018e5feefbf6d901" width="2142" height="1830" data-path="apps/images/app-form.png" />
  </Tile>

  <Tile href="/apps/generative" title="Generative UI" description="LLM writes the UI at runtime">
    <img src="https://mintcdn.com/fastmcp/qxtzRAUiJsjdoWFw/apps/images/app-showcase.png?fit=max&auto=format&n=qxtzRAUiJsjdoWFw&q=85&s=f9775f56a3128c1907fdc8a9f6c5e715" width="2914" height="2060" data-path="apps/images/app-showcase.png" />
  </Tile>
</Columns>

## Running the examples

Preview any example in your browser with the dev server:

```bash theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
pip install "fastmcp[apps]"
fastmcp dev apps examples/apps/sales_dashboard/sales_dashboard_server.py
```

The dev UI lets you pick a tool and fill in arguments. In a real deployment the LLM provides those arguments from conversation context — the quiz example especially shines when connected to a host like Goose or Claude Desktop, where the LLM generates the questions itself.

## Standalone apps

### Sales dashboard

A full dashboard with KPI metrics, revenue trends, segment breakdown, and a deal pipeline table. Shows what you can build with a single `app=True` tool and Prefab's chart and data components.

```bash theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
fastmcp dev apps examples/apps/sales_dashboard/sales_dashboard_server.py
```

### System monitor

Reads live CPU, memory, and disk stats from your machine using `psutil`. Auto-refreshes via `SetInterval` calling a backend tool, with a dropdown to control the refresh rate. The chart accumulates up to 100 data points over time.

```bash theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
pip install psutil
fastmcp dev apps examples/apps/system_monitor/system_monitor_server.py
```

### Quiz

The LLM generates trivia questions and passes them to the tool. The user answers via buttons, sees correct/incorrect feedback, and tracks score across questions. Demonstrates multi-turn client-side state with FastMCPApp.

```bash theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
fastmcp dev apps examples/apps/quiz/quiz_server.py
```

### Interactive map

Accepts addresses or place names, geocodes them via OpenStreetMap Nominatim (free, no API key), and renders an interactive Leaflet map using Prefab's `Embed` component with inline HTML. A reminder that Prefab apps can break out of built-in components when they need to.

```bash theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
fastmcp dev apps examples/apps/map/map_server.py
```

For ready-made building blocks like approvals, choice pickers, file uploads, and Pydantic forms, see the [Providers](/apps/providers/approval) group.

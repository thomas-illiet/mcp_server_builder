> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Apps

> Give your tools interactive UIs rendered directly in the conversation.

export const PrefabDemoFrame = ({demo, height, title}) => {
  const [blobUrl, setBlobUrl] = React.useState(null);
  React.useEffect(() => {
    let active = true;
    let objectUrl = null;
    let payloadsPromise = window.__FASTMCP_PREFAB_DEMOS_PROMISE__;
    if (window.__FASTMCP_PREFAB_DEMOS__) {
      payloadsPromise = Promise.resolve(window.__FASTMCP_PREFAB_DEMOS__);
    } else if (!payloadsPromise) {
      payloadsPromise = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "/prefab-demo-payloads.js";
        script.onload = () => resolve(window.__FASTMCP_PREFAB_DEMOS__);
        script.onerror = reject;
        document.head.appendChild(script);
      });
      window.__FASTMCP_PREFAB_DEMOS_PROMISE__ = payloadsPromise;
    }
    payloadsPromise.then(payloads => {
      const html = payloads[demo];
      if (!html) {
        throw new Error(`Unknown Prefab demo: ${demo}`);
      }
      objectUrl = URL.createObjectURL(new Blob([html], {
        type: "text/html"
      }));
      if (active) {
        setBlobUrl(objectUrl);
      } else {
        URL.revokeObjectURL(objectUrl);
      }
    });
    return () => {
      active = false;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [demo]);
  if (!blobUrl) {
    return <div style={{
      width: "100%",
      height,
      borderRadius: "8px"
    }} />;
  }
  return <iframe src={blobUrl} title={title} style={{
    width: "100%",
    height,
    border: "none",
    overflow: "hidden",
    borderRadius: "8px"
  }} frameBorder="0" scrolling="no" sandbox="allow-scripts allow-same-origin" />;
};

export const VersionBadge = ({version}) => {
  return <Badge stroke size="lg" icon="gift" iconType="regular" className="version-badge">
            New in version <code>{version}</code>
        </Badge>;
};

<VersionBadge version="3.0.0" />

A FastMCP app is a tool that returns an interactive UI instead of text. When the host calls it, the user sees a chart, a table, a form, or a whole dashboard rendered right inside the conversation, with working sort, search, tooltips, and state.

<div
  style={{
margin: '0 clamp(-180px, calc(-18vw + 90px), 0px) 2rem',
maxHeight: '700px',
overflow: 'hidden',
position: 'relative',
maskImage: 'linear-gradient(to bottom, black 75%, transparent)',
WebkitMaskImage: 'linear-gradient(to bottom, black 75%, transparent)',
}}
>
  <PrefabDemoFrame demo="hitchhikers" height="2000px" title="Prefab showcase demo" />
</div>

The dashboard above is a [Prefab](https://prefab.prefect.io) showcase — a taste of what you can deliver from a FastMCP tool. Every card, chart, slider, dialog, and carousel is a Python component. Build a composition like this, add `@mcp.tool(app=True)`, and the host renders it inside the conversation.

Under the hood, FastMCP builds on the [MCP Apps extension](https://modelcontextprotocol.io/docs/extensions/apps) and uses Prefab to describe UIs in Python.

```bash theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
pip install "fastmcp[apps]"
```

<Tip>
  [Prefab](https://prefab.prefect.io) is under active development with frequent breaking changes. FastMCP sets a minimum `prefab-ui` version but does not pin an upper bound — **pin `prefab-ui` to a specific version in your own dependencies** before deploying.
</Tip>

## Pick your path

Four patterns cover almost everything you'd want to build. Most apps start with Interactive Tools; you only reach for the others when you've hit a specific limit.

### [Interactive Tools](/apps/prefab) — start here

Add `app=True` to a tool and return a Prefab component. Charts, tables, dashboards, and client-side interactivity (toggles, tabs, filtering) all work without any server round-trips.

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
@mcp.tool(app=True)
def team_directory() -> DataTable:
    return DataTable(columns=[...], rows=employees, search=True)
```

### [FastMCPApp](/apps/fastmcp-app) — when the UI calls back to the server

Forms that save data, buttons that trigger backend work, search that hits a database. `FastMCPApp` manages the wiring between UI actions and backend tools, with stable tool identifiers that survive server composition.

### [Generative UI](/apps/generative) — when the LLM writes the UI

Register one provider and the model can write Prefab code tailored to the current data and request. The user watches the UI build up as the model generates it.

```python theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
mcp.add_provider(GenerativeUI())
```

### [Custom HTML](/apps/low-level) — when you need full control

Write your own HTML, CSS, and JavaScript. Use a specific framework, drop in a map or 3D viewer, embed video. You're talking to the MCP Apps protocol directly.

## What's next

* **[Quickstart](/apps/quickstart)** — build a working app in a minute
* **[Examples](/apps/examples)** — complete working servers you can run today
* **[Providers](/apps/providers/approval)** — ready-made capabilities (approvals, choice pickers, file upload, forms) you add with one line
* **[Development](/apps/development)** — preview app tools locally with `fastmcp dev apps`

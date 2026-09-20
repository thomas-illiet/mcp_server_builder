> ## Documentation Index
> Fetch the complete documentation index at: https://gofastmcp.com/llms.txt
> Use this file to discover all available pages before exploring further.

# FAQ

> Answers to common questions about installing and using FastMCP

## `import fastmcp` stopped working after I upgraded with pip

This can happen when you upgrade to FastMCP 3.3 or later from FastMCP 3.2 or earlier with `pip`. The quick fix is `pip install --force-reinstall fastmcp`. See [Troubleshooting](/getting-started/installation#troubleshooting) for the clean-reinstall fallback and an explanation of why it happens.

## What's the difference between `fastmcp` and `fastmcp-slim`?

`fastmcp` is the full distribution. Installing it gives you the complete framework — server, client, CLI, and the common integrations — and is the right choice for most users:

```bash theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
pip install fastmcp
```

`fastmcp-slim` ships the same importable `fastmcp` package with a minimal set of required dependencies. You opt into the pieces you need through extras, which keeps environments lean when you only use part of the framework:

```bash theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
pip install "fastmcp-slim[client]"
```

Both distributions expose the same `import fastmcp`, so application code is identical regardless of which one you install.

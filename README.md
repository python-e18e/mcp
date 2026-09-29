# python-e18e MCP

Stdio MCP server inspired by [e18e/mcp](https://github.com/e18e/mcp).
Uses the [official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
and the same codemod functions as the command line. Requires Python 3.11+.

From a checkout of this repository, point it at an explicit checkout of the separate
[replacement catalog](https://github.com/python-e18e/module-replacements):

```sh
uv sync --locked
uv run --locked python-e18e-mcp --replacements /path/to/module-replacements/replacements.json
```

This starts a protocol server; stdout is reserved for MCP messages. For a client
with JSON server configuration, replace the two absolute paths below:

```json
{
  "mcpServers": {
    "python-e18e": {
      "command": "uv",
      "args": [
        "run", "--project", "/absolute/path/to/mcp", "--locked",
        "python-e18e-mcp", "--replacements",
        "/absolute/path/to/module-replacements/replacements.json"
      ]
    }
  }
}
```

| Tool | Input | Result |
| --- | --- | --- |
| `check_dependencies` | PEP 508 requirement strings, `target_python` | Catalog guidance, evidence, compatibility if present, and `meets_python_floor`. |
| `check_code` | Python source, `target_python` | Suggestions with import line numbers. |
| `list_codemods` | None | Available recipes, floors, scopes, and caveats. |
| `preview_codemod` | Source, recipe ID, `target_python` | Transformed source, unified diff, skips, and guidance. |

All tools return structured JSON and advertise read-only behavior. They accept
source text rather than filesystem paths. They never install packages, write
project files, or execute supplied Python. Ruff runs only the fixed recipe rule
on stdin with isolated configuration and safe fixes.

Resources: `python-e18e://replacements` returns the configured manifest;
`python-e18e://docs/{name}` returns an entry using its normalized distribution
name (for example `importlib-metadata`). The `modernize` prompt guides an agent
through checking, previewing, reviewing, and project validation.

The manifest is loaded at startup and is not fetched or updated remotely.
Requirements retain version pins, extras, URLs, and markers in the response;
markers are not evaluated, and replacement version constraints are not solved.
`target_python` is the project's declared minimum, such as `3.11`, not a range.
Meeting a catalog floor does not establish API compatibility.

Import analysis recognizes distribution names with hyphens changed to
underscores, excluding known shared or different namespaces. It cannot infer
installed distributions, local-module shadowing, or dynamic imports. Check
dependency declarations for those cases; do not remove packages from an import
suggestion alone. Invalid source, unknown recipes, and malformed requirements
return MCP tool errors.

```sh
uv run --locked python checks/check_mcp.py
```

The codemods dependency is pinned to an immutable commit in
[python-e18e/codemods](https://github.com/python-e18e/codemods), so this checkout
installs independently without a sibling repository. PyPI publication is a
separate milestone; replace the Git dependency with a published version then.
See [the rollout](https://github.com/python-e18e/python-e18e/blob/main/docs/migrations.md).

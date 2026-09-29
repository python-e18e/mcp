"""Run from this checkout: uv run python checks/check_mcp.py."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import Client, StdioServerParameters

from python_e18e_mcp.server import create_server


def check():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        catalog = root / "replacements.json"
        catalog.write_text(
            json.dumps(
                [
                    {
                        "name": "tomli",
                        "alternative": "tomllib",
                        "minimum_python": "3.11",
                        "guidance": "Retain backports on older interpreters.",
                        "source": "https://docs.python.org/3/library/tomllib.html",
                        "compatibility": "import-only",
                    }
                ]
            )
        )
        asyncio.run(check_mcp(catalog, root))
        entries = json.loads(catalog.read_text())
        for invalid in ([{**entries[0], "name": "tomli[extra]"}], entries * 2):
            catalog.write_text(json.dumps(invalid))
            try:
                create_server(catalog)
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid catalog name or duplicate accepted")


async def check_mcp(catalog, root):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "python_e18e_mcp.server", "--replacements", str(catalog)],
        env=dict(os.environ),
    )
    async with Client(parameters) as client:
        tools = (await client.list_tools()).tools
        assert {tool.name for tool in tools} == {
            "check_dependencies",
            "check_code",
            "list_codemods",
            "preview_codemod",
        }
        assert all(tool.annotations.read_only_hint for tool in tools)
        result = await client.call_tool(
            "check_dependencies",
            {
                "requirements": ['tomli>=2; python_version < "3.11"', "other>=1"],
                "target_python": "3.10",
            },
        )
        assert (
            not result.is_error and len(result.structured_content["suggestions"]) == 1
        )
        assert not result.structured_content["suggestions"][0]["meets_python_floor"]
        for source, count in [
            ("import tomli as parser\n", 1),
            ("from .tomli import loads\n", 0),
            ('text = "import tomli"\n', 0),
        ]:
            result = await client.call_tool(
                "check_code", {"source": source, "target_python": "3.11"}
            )
            assert (
                not result.is_error
                and len(result.structured_content["suggestions"]) == count
            )
        sentinel = root / "executed"
        source = f'import tomli\nopen({str(sentinel)!r}, "w").close()\n'
        result = await client.call_tool(
            "preview_codemod",
            {"source": source, "recipe": "tomli-to-tomllib", "target_python": "3.11"},
        )
        assert (
            not result.is_error
            and result.structured_content["changed"]
            and not sentinel.exists()
        )
        result = await client.call_tool(
            "preview_codemod",
            {
                "source": "import tomli\n",
                "recipe": "tomli-to-tomllib",
                "target_python": "3.10",
            },
        )
        assert result.is_error
        assert "requires Python 3.11" in result.content[0].text
        result = await client.call_tool(
            "check_dependencies",
            {"requirements": ["-r requirements.txt"], "target_python": "3.11"},
        )
        assert result.is_error
        result = await client.read_resource("python-e18e://docs/tomli")
        assert "Retain backports" in result.contents[0].text
        assert (await client.list_resources()).resources
        assert (await client.list_resource_templates()).resource_templates
        assert (await client.get_prompt("modernize")).messages


if __name__ == "__main__":
    check()
    print("MCP stdio and catalog checks passed.")

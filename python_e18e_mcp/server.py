"""Serve an explicit local replacement catalog and source previews over stdio."""

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import libcst as cst
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from python_e18e_codemods import RECIPES, preview, python_version


def create_server(catalog_path):
    entries = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    fields = ("name", "alternative", "minimum_python", "guidance", "source")
    if not isinstance(entries, list) or any(
        not isinstance(entry, dict)
        or any(
            not isinstance(entry.get(field), str) or not entry[field].strip()
            for field in fields
        )
        for entry in entries
    ):
        raise ValueError("Expected an array of complete replacement entries")
    catalog = {}
    for entry in entries:
        requirement = Requirement(entry["name"])
        name = canonicalize_name(requirement.name)
        if requirement.name != entry["name"] or name in catalog:
            raise ValueError("Catalog names must be unique plain distribution names")
        if not re.fullmatch(r"3\.\d+", entry["minimum_python"]):
            raise ValueError("Catalog minimum_python must be 3.x")
        catalog[name] = entry

    server = MCPServer(
        "python-e18e",
        instructions="Check declared dependencies and migration guidance. Preview changes against the lowest supported Python. Review the diff and run project checks before applying it.",
    )
    read_only = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    def suggestion(entry, target_python):
        return {
            **entry,
            "meets_python_floor": python_version(target_python)
            >= python_version(entry["minimum_python"]),
        }

    @server.tool(annotations=read_only)
    def check_dependencies(
        requirements: list[str], target_python: str
    ) -> dict[str, Any]:
        """Check PEP 508 requirements against the catalog; markers are preserved, not evaluated."""
        findings = []
        try:
            python_version(target_python)
            for value in requirements:
                entry = catalog.get(canonicalize_name(Requirement(value).name))
                if entry:
                    findings.append(
                        {"requirement": value, **suggestion(entry, target_python)}
                    )
        except ValueError as error:
            raise ToolError(str(error)) from error
        return {"suggestions": findings}

    @server.tool(annotations=read_only)
    def check_code(source: str, target_python: str) -> dict[str, Any]:
        """Suggest replacements for distinct legacy imports; inspect declarations to disambiguate shared namespaces."""
        try:
            tree = ast.parse(source, feature_version=python_version(target_python))
        except (ValueError, SyntaxError) as error:
            raise ToolError(str(error)) from error
        # ponytail: explicit ambiguous namespaces omitted; add dependency-aware matching with project scans.
        modules = {
            entry["name"].replace("-", "_"): entry
            for entry in entries
            if entry["name"] != entry["alternative"]
            and canonicalize_name(entry["name"])
            not in {
                "enum34",
                "futures",
                "fpdf",
                "pycrypto",
                "python-dateutil",
                "pip-tools",
                "selectors34",
                "sklearn",
            }
        }
        findings = []
        for node in ast.walk(tree):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else (
                    [node.module]
                    if isinstance(node, ast.ImportFrom)
                    and not node.level
                    and node.module
                    else []
                )
            )
            for name in names:
                entry = next(
                    (
                        entry
                        for module, entry in modules.items()
                        if name == module or name.startswith(module + ".")
                    ),
                    None,
                )
                if entry:
                    findings.append(
                        {
                            "line": node.lineno,
                            "module": name,
                            **suggestion(entry, target_python),
                        }
                    )
        return {"suggestions": findings}

    @server.tool(annotations=read_only)
    def list_codemods() -> dict[str, Any]:
        """List explicit migration recipes, Python floors, caveats, and evidence."""
        return {"recipes": RECIPES}

    @server.tool(annotations=read_only)
    def preview_codemod(source: str, recipe: str, target_python: str) -> dict[str, Any]:
        """Return transformed source and a diff. Does not write files or execute supplied code."""
        try:
            return preview(source, recipe, target_python)
        except (
            ValueError,
            SyntaxError,
            cst.ParserSyntaxError,
            OSError,
            subprocess.SubprocessError,
        ) as error:
            raise ToolError(str(error)) from error

    @server.resource("python-e18e://replacements")
    def replacements() -> str:
        """The configured local replacement manifest."""
        return json.dumps(entries, indent=2)

    @server.resource("python-e18e://docs/{name}")
    def migration_guide(name: str) -> str:
        """Guidance for a normalized distribution name, for example importlib-metadata."""
        key = canonicalize_name(name)
        if key not in catalog:
            raise ValueError(f"Unknown replacement: {name}")
        return json.dumps(catalog[key], indent=2)

    @server.prompt()
    def modernize() -> str:
        """Plan a migration with evidence and an explicit Python floor."""
        return "Check dependencies and source against the catalog. Read migration guidance, select an explicit recipe and the project's lowest supported Python, then preview its diff. Review API and platform caveats, update dependencies separately, and run the project's checks before applying changes."

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replacements", type=Path, required=True)
    args = parser.parse_args()
    try:
        server = create_server(args.replacements)
    except (OSError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

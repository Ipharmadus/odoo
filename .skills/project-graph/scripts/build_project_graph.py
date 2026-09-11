#!/usr/bin/env python3
"""Build a structural graph for the Pharmadus Odoo addons.

The script is intentionally dependency-free and parses repository files without
starting Odoo. It extracts enough structure for agents and developers to orient
future changes: addons, manifest dependencies, Python models, comodel links,
XML records, menus, actions, and CSV security/data files.
"""

from __future__ import annotations

import ast
import csv
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = REPO_ROOT / ".skills" / "project-graph"
GRAPH_DIR = SKILL_ROOT / "graph"

MODEL_ATTRS = {"_name", "_inherit", "_inherits", "_description", "_transient"}
FIELD_CALL_RE = re.compile(r"fields\.(Many2one|One2many|Many2many|Reference)\s*\((?P<args>.*?)\)", re.S)
COMODEL_RE = re.compile(r"comodel_name\s*=\s*['\"]([^'\"]+)['\"]|^[\s\n]*['\"]([^'\"]+)['\"]", re.S)
MODEL_REF_RE = re.compile(r"['\"]([a-zA-Z0-9_.]+\.[a-zA-Z0-9_.]+)['\"]")


@dataclass
class XmlSummary:
    file: str
    records: list[dict[str, str]] = field(default_factory=list)
    menus: list[dict[str, str]] = field(default_factory=list)
    actions: list[dict[str, str]] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)


@dataclass
class CsvSummary:
    file: str
    columns: list[str] = field(default_factory=list)
    rows: int = 0
    models: list[str] = field(default_factory=list)


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def literal(value: ast.AST) -> Any:
    try:
        return ast.literal_eval(value)
    except Exception:
        return None


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        data = ast.literal_eval(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_parse_error": str(exc)}
    return data if isinstance(data, dict) else {"_parse_error": "Manifest is not a dict"}


def find_addons() -> list[Path]:
    addons = []
    for manifest in sorted(REPO_ROOT.glob("*/__manifest__.py")):
        if ".skills" not in manifest.parts:
            addons.append(manifest.parent)
    return addons


def class_attr_value(class_node: ast.ClassDef, attr_name: str) -> Any:
    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == attr_name:
                    return literal(stmt.value)
    return None


def parse_python_models(addon: Path) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    for path in sorted(addon.rglob("*.py")):
        if path.name == "__manifest__.py":
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            attrs = {name: class_attr_value(node, name) for name in MODEL_ATTRS}
            if not any(value is not None for value in attrs.values()):
                continue
            class_source = ast.get_source_segment(source, node) or ""
            comodels = sorted({match.group(1) or match.group(2) for match in COMODEL_RE.finditer(class_source) if match.group(1) or match.group(2)})
            field_types = sorted({match.group(1) for match in FIELD_CALL_RE.finditer(class_source)})
            models.append(
                {
                    "class": node.name,
                    "file": rel(path),
                    "line": node.lineno,
                    "name": attrs.get("_name"),
                    "inherit": attrs.get("_inherit"),
                    "inherits": attrs.get("_inherits"),
                    "description": attrs.get("_description"),
                    "transient": attrs.get("_transient"),
                    "field_types": field_types,
                    "comodels": comodels,
                }
            )
    return models


def xml_attr(elem: ET.Element, name: str) -> str:
    return elem.attrib.get(name, "")


def parse_xml_file(path: Path) -> XmlSummary:
    summary = XmlSummary(file=rel(path))
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return summary
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "record":
            record = {"id": xml_attr(elem, "id"), "model": xml_attr(elem, "model")}
            if record["id"] or record["model"]:
                summary.records.append(record)
            if record["model"] == "ir.actions.act_window":
                action = dict(record)
                for field_elem in elem.findall("field"):
                    if xml_attr(field_elem, "name") in {"name", "res_model", "view_mode"}:
                        action[xml_attr(field_elem, "name")] = (field_elem.text or xml_attr(field_elem, "ref") or "").strip()
                summary.actions.append(action)
        elif tag == "menuitem":
            summary.menus.append(
                {
                    "id": xml_attr(elem, "id"),
                    "name": xml_attr(elem, "name"),
                    "parent": xml_attr(elem, "parent"),
                    "action": xml_attr(elem, "action"),
                    "groups": xml_attr(elem, "groups"),
                    "sequence": xml_attr(elem, "sequence"),
                }
            )
        elif tag == "template":
            template_id = xml_attr(elem, "id") or xml_attr(elem, "t-name")
            if template_id:
                summary.templates.append(template_id)
    return summary


def parse_xml(addon: Path) -> list[XmlSummary]:
    return [parse_xml_file(path) for path in sorted(addon.rglob("*.xml"))]


def parse_csv_file(path: Path) -> CsvSummary:
    summary = CsvSummary(file=rel(path))
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            summary.columns = reader.fieldnames or []
            models = set()
            rows = 0
            for row in reader:
                rows += 1
                for key in ("model_id:id", "model", "res_model"):
                    value = row.get(key)
                    if value:
                        models.add(value)
            summary.rows = rows
            summary.models = sorted(models)
    except Exception:
        pass
    return summary


def parse_csv_files(addon: Path) -> list[CsvSummary]:
    return [parse_csv_file(path) for path in sorted(addon.rglob("*.csv"))]


def build_graph() -> dict[str, Any]:
    addons_data: dict[str, Any] = {}
    for addon in find_addons():
        manifest = read_manifest(addon / "__manifest__.py")
        xml_files = parse_xml(addon)
        csv_files = parse_csv_files(addon)
        addons_data[addon.name] = {
            "path": rel(addon),
            "manifest": {
                "name": manifest.get("name", addon.name),
                "version": manifest.get("version", ""),
                "depends": manifest.get("depends", []),
                "data": manifest.get("data", []),
                "assets": manifest.get("assets", {}),
                "installable": manifest.get("installable", True),
                "license": manifest.get("license", ""),
                "post_init_hook": manifest.get("post_init_hook", ""),
            },
            "models": parse_python_models(addon),
            "xml": [summary.__dict__ for summary in xml_files],
            "csv": [summary.__dict__ for summary in csv_files],
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo_root": str(REPO_ROOT),
        "addons": addons_data,
    }


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        values = [str(value).replace("\n", " ") if value not in (None, "") else "" for value in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render_addons_md(graph: dict[str, Any]) -> str:
    rows = []
    for name, addon in graph["addons"].items():
        manifest = addon["manifest"]
        rows.append([name, manifest["name"], manifest["version"], ", ".join(manifest["depends"]), manifest["installable"]])
    return "\n".join(
        [
            "# Addons Dependencies",
            "",
            f"Generated: `{graph['generated_at']}`",
            "",
            md_table(["Addon", "Display Name", "Version", "Depends", "Installable"], rows),
            "",
        ]
    )


def render_models_md(graph: dict[str, Any]) -> str:
    lines = ["# Models", "", f"Generated: `{graph['generated_at']}`", ""]
    for addon_name, addon in graph["addons"].items():
        rows = []
        for model in addon["models"]:
            rows.append(
                [
                    model["class"],
                    model["name"] or "",
                    model["inherit"] or "",
                    ", ".join(model["comodels"]),
                    f"{model['file']}:{model['line']}",
                ]
            )
        lines.extend([f"## {addon_name}", "", md_table(["Class", "_name", "_inherit", "Comodels", "Location"], rows or [["", "", "", "", ""]]), ""])
    return "\n".join(lines)


def render_views_md(graph: dict[str, Any]) -> str:
    lines = ["# Views, Menus, Actions And Data", "", f"Generated: `{graph['generated_at']}`", ""]
    for addon_name, addon in graph["addons"].items():
        lines.extend([f"## {addon_name}", ""])
        xml_rows = []
        menu_rows = []
        action_rows = []
        template_rows = []
        for xml in addon["xml"]:
            models = sorted({record["model"] for record in xml["records"] if record.get("model")})
            xml_rows.append([xml["file"], len(xml["records"]), ", ".join(models)])
            for menu in xml["menus"]:
                menu_rows.append([menu["id"], menu["name"], menu["parent"], menu["action"], menu["groups"], menu["sequence"], xml["file"]])
            for action in xml["actions"]:
                action_rows.append([action.get("id", ""), action.get("name", ""), action.get("res_model", ""), action.get("view_mode", ""), xml["file"]])
            for template in xml["templates"]:
                template_rows.append([template, xml["file"]])
        csv_rows = [[csv_file["file"], csv_file["rows"], ", ".join(csv_file["models"])] for csv_file in addon["csv"]]
        lines.extend(["### XML Files", "", md_table(["File", "Records", "Record Models"], xml_rows or [["", "", ""]]), ""])
        lines.extend(["### Menus", "", md_table(["ID", "Name", "Parent", "Action", "Groups", "Sequence", "File"], menu_rows or [["", "", "", "", "", "", ""]]), ""])
        lines.extend(["### Actions", "", md_table(["ID", "Name", "Res Model", "View Mode", "File"], action_rows or [["", "", "", "", ""]]), ""])
        lines.extend(["### Templates", "", md_table(["ID", "File"], template_rows or [["", ""]]), ""])
        lines.extend(["### CSV Files", "", md_table(["File", "Rows", "Models"], csv_rows or [["", "", ""]]), ""])
    return "\n".join(lines)


def render_dot(graph: dict[str, Any]) -> str:
    lines = ["digraph pharmadus_addons {", "  rankdir=LR;", "  node [shape=box];"]
    addons = set(graph["addons"].keys())
    for addon_name, addon in graph["addons"].items():
        lines.append(f'  "{addon_name}" [style=filled, fillcolor="#e8f0fe"];')
        for dep in addon["manifest"].get("depends", []):
            style = "solid" if dep in addons else "dashed"
            lines.append(f'  "{dep}" -> "{addon_name}" [style={style}];')
        for model in addon["models"]:
            model_name = model.get("name") or model.get("inherit")
            if model_name:
                lines.append(f'  "{addon_name}" -> "{model_name}" [label="model", color="#888888"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_outputs(graph: dict[str, Any]) -> None:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    (GRAPH_DIR / "project-graph.json").write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (GRAPH_DIR / "addons-dependencies.md").write_text(render_addons_md(graph), encoding="utf-8")
    (GRAPH_DIR / "models.md").write_text(render_models_md(graph), encoding="utf-8")
    (GRAPH_DIR / "views-menus-actions.md").write_text(render_views_md(graph), encoding="utf-8")
    (GRAPH_DIR / "addons-dependencies.dot").write_text(render_dot(graph), encoding="utf-8")


def main() -> None:
    graph = build_graph()
    write_outputs(graph)
    print(f"Generated project graph for {len(graph['addons'])} addons in {GRAPH_DIR}")


if __name__ == "__main__":
    main()

# Skill: project-graph

# Pharmadus Project Structural Graph

Use this skill before making non-trivial changes to Pharmadus Odoo addons when
you need a quick structural map of the repository.

This skill stores a regenerable project graph generated from repository files,
without connecting to Odoo or PostgreSQL.

## When To Use

Use this skill when work involves:

- Adding, removing, renaming, or changing addon dependencies.
- Editing `__manifest__.py` files.
- Adding or changing Odoo models, `_name`, `_inherit`, `_inherits`, fields, or
  comodel relations.
- Adding or changing XML views, menus, actions, reports, templates, data, or
  security records.
- Adding or changing CSV security/data files.
- Reviewing impact across custom addons.

For Odoo implementation rules, also use `.skills/odoo-18.0/SKILL.md`.
For local runtime, updates, logs, containers, and database validation, also use
`.skills/odoo-dev/SKILL.md`.

## Generated Files

```text
.skills/project-graph/graph/project-graph.json
.skills/project-graph/graph/addons-dependencies.md
.skills/project-graph/graph/addons-dependencies.dot
.skills/project-graph/graph/models.md
.skills/project-graph/graph/views-menus-actions.md
```

## Regeneration Command

Run from the repository root:

```bash
python3 .skills/project-graph/scripts/build_project_graph.py
```

The generator is dependency-free and reads local files only.

## Maintenance Rule For Agents

Agents must keep this graph current.

After changing any of these files or concepts, regenerate the graph in the same
session before final response:

- Any `__manifest__.py`.
- Any Python Odoo model/report/wizard file that changes `_name`, `_inherit`,
  `_inherits`, fields, or comodels.
- Any XML file defining or modifying `record`, `menuitem`, `template`, actions,
  views, reports, data, or security.
- Any CSV file under an addon, especially `security/ir.model.access.csv` or
  data seed files.
- Any addon directory addition/removal/rename.

If the generator output changes, include the generated graph files in the same
worktree changes unless the user explicitly asks not to.

If the generator cannot run, state that clearly in the final response and do not
claim the graph is current.

## How To Read The Graph

- Start with `graph/addons-dependencies.md` for module dependencies and versions.
- Use `graph/models.md` to locate model classes, inherited models, and comodel
  relationships.
- Use `graph/views-menus-actions.md` for XML/CSV surface area: views, menus,
  actions, templates, and security/data files.
- Use `graph/project-graph.json` for machine-readable analysis.
- Use `graph/addons-dependencies.dot` with Graphviz if a visual dependency graph
  is needed.

## Scope And Limits

The graph is structural, not a runtime truth source.

It does not prove whether a module is installed in a database, whether a view is
valid after inheritance resolution, or whether access rules are effective. Query
Odoo/PostgreSQL for runtime state when needed.

Coverage: the graph describes the installable addons of this repository
(`pharmadus_base`, `pharmadus_custom`, `pharmadus_stock_supplier_lot`,
`stock_lot_state`). It ignores `migracion_pharmadus_8_18` (no
`__manifest__.py`) and does not cover the addons living in `../private/`
(`bookmark`, `sale_custom`, `sale_messages`) or the OCA/OCB sources in
`../odoo/` and other aggregated addon repositories.

Output is deterministic for a given worktree: when nothing relevant changed,
regenerating only refreshes the `Generated:` / `generated_at` timestamp. Any
other difference means the graph was stale.

The parser is intentionally conservative. If code uses dynamic model names or
unusual XML generation, verify manually against the source files.

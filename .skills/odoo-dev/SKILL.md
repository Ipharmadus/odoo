---
name: odoo-dev
description: >
  Pharmadus Odoo 18 development environment context. Use for tasks specific to
  this Debian/Docker Compose/Doodba server: compose files, service ports, local
  addon layout, custom modules, migrations, debugging, and safe operational
  commands for the Pharmadus Odoo 18 instance.
globs: "**/*.{py,xml,csv,yaml,yml,json,md,txt}"
---

# Pharmadus Odoo 18 Development Environment

This skill documents the actual local development setup on this server. Prefer
the repository files over this document if they disagree.

## Root Paths

```text
/opt/pharmadus/                            Docker Compose/Doodba project root
/opt/pharmadus/odoo/custom/src/pharmadus/  Pharmadus repo (origin Ipharmadus/odoo, branch 18.0)
/opt/pharmadus/odoo/custom/src/private/    Extra local addons (bookmark, sale_custom, sale_messages)
/opt/pharmadus/odoo/custom/src/odoo/       OCB 18.0 core source (do not edit)
```

Run Docker Compose commands from `/opt/pharmadus` and code/git commands from
`/opt/pharmadus/odoo/custom/src/pharmadus` unless a task requires another path.

## Key Files

```text
/opt/pharmadus/devel.yaml                 Main development compose file
/opt/pharmadus/common.yaml                Shared compose service definitions
/opt/pharmadus/setup-devel.yaml           Doodba autoaggregate helper
/opt/pharmadus/odoo/custom/src/repos.yaml Aggregated repositories
/opt/pharmadus/odoo/custom/src/addons.yaml Addon selection
/opt/pharmadus/odoo/custom/conf.d/        Odoo config fragments
/opt/pharmadus/odoo/custom/dependencies/  pip/apt dependency lists
```

## Compose Model

`devel.yaml` extends `common.yaml`.

Development database:

```text
Database: devel
PostgreSQL user: odoo
PostgreSQL password: odoopassword
```

The Odoo service is built from `./odoo` with Doodba build arguments:

```text
ODOO_VERSION=18.0
DB_VERSION=17
PIP_INSTALL_ODOO=false
AGGREGATE=false
```

`common.yaml` uses PostgreSQL image:

```text
ghcr.io/tecnativa/postgres-autoconf:17-alpine
```

The repository aggregation in `repos.yaml` uses OCB 18.0 for `./odoo` and the
private Pharmadus repository for `./private`.

## Development Services And Ports

Use the ports declared in `devel.yaml`:

```text
Odoo web via whitelist proxy: http://127.0.0.1:18069
Odoo longpolling/websocket proxy: 127.0.0.1:18072
Whitelist proxy extra port: 127.0.0.1:18899
Pgweb: http://127.0.0.1:18081
Mailhog: http://127.0.0.1:18025
WDB: http://127.0.0.1:18984
```

Do not assume Odoo is available at `localhost:8069`; in this devel setup the
public access path is the proxy on `18069`.

Do not assume containers are running. Check first:

```bash
docker compose -f devel.yaml ps
```

Expected Compose service names include `odoo`, `db`, `odoo_proxy`, `pgweb`,
`smtp`, `wdb`, and several whitelist proxy services. Container names are derived
by Docker Compose and should be verified with `docker compose -f devel.yaml ps`
instead of hardcoding them.

## Development Runtime

`devel.yaml` starts Odoo with development flags:

```text
--workers=0
--dev=reload,qweb,werkzeug,xml
--limit-memory-soft=0
--limit-time-real-cron=9999999
--limit-time-real=9999999
```

Important environment values:

```text
DOODBA_ENVIRONMENT=devel by default
INITIAL_LANG=es_ES
LIST_DB=true
PGDATABASE=devel
PYTHONPATH=/opt/odoo/custom/src/odoo
WDB_WEB_PORT=18984
DEBUGPY_ENABLE=${DOODBA_DEBUGPY_ENABLE:-0}
WITHOUT_DEMO=${DOODBA_WITHOUT_DEMO-false}
```

`/opt/pharmadus/odoo/custom/conf.d/80-workers.conf` sets `workers = 3`, but the
development command in `devel.yaml` overrides runtime workers to `0`.

## Common Commands

Always set the working directory to `/opt/pharmadus` for these commands.

```bash
docker compose -f devel.yaml up -d --build
docker compose -f devel.yaml down
docker compose -f devel.yaml ps
docker compose -f devel.yaml logs -f odoo
docker compose -f devel.yaml logs --tail=100 odoo
docker compose -f devel.yaml exec db psql -U odoo -d devel
```

For non-interactive SQL:

```bash
docker compose -f devel.yaml exec -T db psql -U odoo -d devel -c "SELECT current_database();"
```

Use `exec -T` for scripted or non-interactive commands that pass SQL with `-c`.
Keep plain `exec` for interactive `psql` sessions.

## Addon Layout

Custom addons in `/opt/pharmadus/odoo/custom/src/pharmadus` (the git repo):

```text
pharmadus_base
stock_lot_state
pharmadus_stock_supplier_lot
pharmadus_custom
```

Extra addons in `/opt/pharmadus/odoo/custom/src/private` (outside the Pharmadus
git repo, but present and installed in the development database):

```text
bookmark
sale_custom
sale_messages
```

`migracion_pharmadus_8_18` is a migration project directory, not an installable
addon: it has no `__manifest__.py`. Do not treat it as a module.

Before modifying a module, confirm ownership with the team; several addons in
this environment come from external collaborators, and OCA addons plus the OCB
core source under `odoo/` must not be edited here.

There may be additional work-in-progress addons in the working tree. Check
`git status --short` and avoid overwriting unrelated changes.

Manifest summaries from the local files:

```text
pharmadus_base 18.0.1.0.0
Depends: base, mail, sales_team, sale, purchase, purchase_requisition, stock,
mrp, stock_lot_state, product_expiry, quality_control_oca, account,
stock_account.

stock_lot_state 18.0.1.0.0
Depends: stock, product_expiry, stock_lock_lot.

pharmadus_stock_supplier_lot 18.0.1.0.0
Depends: stock_picking_auto_create_lot. Has post_init_hook.

pharmadus_custom 18.0.1.0.0
Depends: sale, stock.
```

The files confirm module availability in the source tree, not installation
state in the database. Verify installation state through Odoo/database before
claiming a module is installed.

## Updating Modules

Prefer the Odoo CLI over ad-hoc Python snippets.

Recommended workflow for this development stack: stop the running Odoo process,
run the update in a one-off container, then start Odoo again. This avoids two
Odoo processes touching the same database registry at the same time.

From `/opt/pharmadus`:

```bash
docker compose -f devel.yaml stop odoo odoo_proxy
docker compose -f devel.yaml run --rm odoo odoo -d devel -u pharmadus_base --stop-after-init
docker compose -f devel.yaml start odoo odoo_proxy
docker compose -f devel.yaml logs --tail=150 odoo
```

For multiple modules:

```bash
docker compose -f devel.yaml stop odoo odoo_proxy
docker compose -f devel.yaml run --rm odoo odoo -d devel -u pharmadus_base,stock_lot_state,pharmadus_stock_supplier_lot,pharmadus_custom --stop-after-init
docker compose -f devel.yaml start odoo odoo_proxy
docker compose -f devel.yaml logs --tail=150 odoo
```

Faster but less clean alternative when Odoo is already running:

```bash
docker compose -f devel.yaml exec odoo odoo -d devel -u pharmadus_base --stop-after-init
```

Avoid the alternative unless explicitly accepted, because it can coexist with
the active Odoo process in the service container.

## Repositories And Addons

`repos.yaml` (each key is a directory under `odoo/custom/src/`):

```text
./odoo      OCA/OCB, target `ocb $ODOO_VERSION` (remotes: ocb, odoo)
pharmadus   Ipharmadus/odoo, target `$ODOO_VERSION` (remote: origin)
```

`addons.yaml` enables all addons (`*`) from many OCA repositories plus
`pharmadus` and `spreadsheet`. Do not assume all possible addons are installed
in the database; this only controls addon availability. `private/` is not listed
in `repos.yaml`, so it is not managed by Doodba aggregation.

Use `setup-devel.yaml` only for Doodba aggregation:

```bash
docker compose -f setup-devel.yaml run --rm odoo
```

The file comments mention exporting UID/GID/UMASK variables before aggregation.

## Migrations

Migration directory:

```text
/opt/pharmadus/odoo/custom/src/pharmadus/migracion_pharmadus_8_18/
```

Known files:

```text
README.md
config.example.json
config.json
scripts/__init__.py
scripts/odoo_xmlrpc.py
scripts/migrate_customer_valued_picking.py
scripts/migrate_product_expiry.py
scripts/migrate_product_extra_categories.py
scripts/migrate_product_specifications.py
scripts/migrate_user_signatures.py
```

`config.json` contains source/target XML-RPC connection details and may contain
secrets. Do not print, commit, or rewrite real credentials. Use
`config.example.json` for examples and scrub secrets from any output.

The current target URL pattern for local development is the proxy:

```text
http://127.0.0.1:18069
```

Do not assume `_tmp_import/data` exists; verify paths before running migration
scripts. Always perform backups and dry runs where the script supports them.

## Testing And Verification

After code changes, use checks appropriate to the change:

```bash
docker compose -f devel.yaml ps
docker compose -f devel.yaml logs --tail=100 odoo
docker compose -f devel.yaml exec -T db psql -U odoo -d devel -c "SELECT name, state FROM ir_module_module WHERE name IN ('pharmadus_base', 'stock_lot_state', 'pharmadus_stock_supplier_lot', 'pharmadus_custom');"
```

For Odoo tests, prefer module-scoped test execution and avoid running the full
suite unless explicitly needed.

## Security And Safety

- Do not expose credentials from `config.json` or other local files.
- Do not assume service/container names; verify with Compose.
- Do not claim database state without querying the database.
- Before making code or configuration changes, update the local branch from
  `/opt/pharmadus` and confirm the worktree reflects the latest remote state.
- Protect remote repository changes already present locally: restore or merge
  tracked files carefully and preserve local-only addon directories unless the
  task explicitly requires removing them.
- Do not overwrite worktree changes made by the user or other agents.
- Do not commit, push, or amend unless explicitly requested.
- Use `/opt/pharmadus` as the working directory for Docker Compose commands.
- Use `/opt/pharmadus/odoo/custom/src/pharmadus` as the working directory for
  addon source edits and git commands.

## Known Corrections Versus Older Notes

- The development web URL is `http://127.0.0.1:18069`, not direct `8069`.
- The Odoo image is built locally by Doodba; do not document it as
  `tecnativa/odoo:18.0-ee` unless the compose file changes.
- The PostgreSQL image is `ghcr.io/tecnativa/postgres-autoconf:17-alpine`, not
  plain `postgres:17-alpine`.
- WDB service name is `wdb`; do not hardcode a nonexistent
  `pharmadus-wdb-debugpy-1` container.
- Module source presence is not the same as installed database state.
- Migration configuration uses XML-RPC source/target credentials; do not replace
  it with unrelated dry-run JSON unless intentionally changing the migration
  scripts.
- The current Pharmadus repo is `/opt/pharmadus/odoo/custom/src/pharmadus`, not
  `.../custom/src/private`. `private/` holds unrelated addons (`bookmark`,
  `sale_custom`, `sale_messages`).
- The migration project lives inside the Pharmadus repo
  (`.../pharmadus/migracion_pharmadus_8_18/`) and ships five migration scripts
  besides `odoo_xmlrpc.py`.
- `conf.d/80-workers.conf` sets `workers = 3` (older notes said 8); the devel
  command still overrides it with `--workers=0`.

Last reviewed against local files: 2026-09-11.

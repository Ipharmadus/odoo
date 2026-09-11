# Project Instructions

Este repositorio usa skills locales en la carpeta `.skills/`.

Antes de trabajar en tareas relacionadas con Odoo, addons, vistas XML, CSV de datos, modelos ORM, migraciones o actualización de módulos, revisa y aplica primero la skill más adecuada disponible en `.skills/`.

Skills locales prioritarias:

- `.skills/odoo-18.0/SKILL.md`: referencia general de desarrollo Odoo 18.
- `.skills/odoo-dev/SKILL.md`: contexto operativo del entorno local Pharmadus, Docker Compose, Doodba, puertos, base de datos y comandos seguros.
- `.skills/project-graph/SKILL.md`: grafo estructural regenerable de addons, dependencias, modelos, vistas, menús, acciones y datos.

Reglas de uso:

- Para cualquier cambio funcional o técnico en addons Odoo, usa primero la referencia de `.skills/odoo-18.0/`.
- Para cualquier operación sobre esta instancia local, actualización de módulos, logs, contenedores, base de datos o validaciones del entorno, usa también `.skills/odoo-dev/SKILL.md`.
- Para cambios no triviales en manifests, modelos, vistas XML, menús, acciones, seguridad o datos CSV, consulta `.skills/project-graph/SKILL.md` y mantén actualizado su grafo.
- Si cambias cualquier `__manifest__.py`, modelo Odoo, XML de vistas/datos/seguridad, CSV de addons o añades/eliminas/renombras addons, ejecuta `python3 .skills/project-graph/scripts/build_project_graph.py` antes de finalizar y conserva los archivos generados.
- Si hay discrepancias entre una skill y el código real del repositorio, prevalece el código del repositorio.

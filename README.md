# Fikrity Workspaces

Distributes the approved workspace layout from `demo.fikrity.com` to ERPNext +
HRMS sites. CRM and links owned by other custom apps are intentionally excluded.

The baseline is applied only when the app is first installed. It is not a
fixture and is not re-applied by `migrate`. Before every migration the app
snapshots the managed workspaces and restores that exact snapshot afterwards,
so customer edits are not replaced by newer standard ERPNext/HRMS workspace
files.

## Requirements

- Frappe/ERPNext v15
- ERPNext installed on the target site
- HRMS installed on the target site

## Installation

```bash
bench --site SITE_NAME install-app fikrity_workspaces
```

Installation imports 32 workspaces plus all of their bundled widget
dependencies (currently 27 dashboard charts and 12 number cards). The prior
state of those records is retained in the single `Fikrity Workspace Settings`
document for recovery/audit purposes.

## Updating the distributed baseline

This is an explicit developer operation and must only be run on the approved
source site. It does not run during install or migration:

```bash
bench --site demo.fikrity.com console
```

```python
from fikrity_workspaces.bundle import audit_bundle, export_bundle

export_bundle()
audit_bundle()
```

The audit must report no missing targets and no external links. Increment
`BUNDLE_VERSION` when deliberately publishing a new baseline. Existing customer
sites are never upgraded automatically; use a reviewed one-time patch or an
explicit command that preserves customer changes.

## Development

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/fikrity_workspaces
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

## License

mit

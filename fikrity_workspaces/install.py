from __future__ import annotations

import json

import frappe
from frappe.utils import now_datetime

from fikrity_workspaces.bundle import BUNDLE_VERSION, apply_bundle, audit_bundle, capture_current_state


def after_install() -> None:
	installed_apps = set(frappe.get_installed_apps())
	missing = {"erpnext", "hrms"} - installed_apps
	if missing:
		frappe.throw(f"Install required apps before Fikrity Workspaces: {', '.join(sorted(missing))}")

	audit = audit_bundle()
	if audit["missing"]:
		frappe.throw(f"Workspace bundle has missing dependencies: {audit['missing']}")
	if audit["external_links"]:
		frappe.throw(f"Workspace bundle has unsupported app dependencies: {audit['external_links']}")

	settings = frappe.get_single("Fikrity Workspace Settings")
	if not settings.preinstall_snapshot:
		settings.preinstall_snapshot = json.dumps(
			capture_current_state(), ensure_ascii=False, sort_keys=True, default=str
		)

	counts = apply_bundle()
	settings.installed_bundle_version = BUNDLE_VERSION
	settings.installed_on = now_datetime()
	settings.save(ignore_permissions=True)

	frappe.logger("fikrity_workspaces").info("Installed workspace bundle %s: %s", BUNDLE_VERSION, counts)

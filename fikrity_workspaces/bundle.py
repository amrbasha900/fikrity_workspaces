from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import frappe
from frappe.modules.import_file import import_doc
from frappe.utils import now_datetime

BUNDLE_VERSION = "1"
BUNDLE_PATH = Path(__file__).with_name("data") / "workspace_bundle.json"

# Public workspaces created on demo.fikrity.com.  They have no source file in
# ERPNext/HRMS, so they must travel in this app.
CUSTOM_WORKSPACES = (
	"Financial Management",
	"Reports",
	"General Reports",
	"HR Management",
	"HR File",
	"HR Finance",
	"Performance",
	"Expenses",
)

# Standard ERPNext/HRMS workspaces changed on demo.fikrity.com. CRM is
# deliberately excluded. Their desired state is installed once; protection.py
# preserves the customer's later edits during subsequent migrations.
CHANGED_STANDARD_WORKSPACES = (
	"Accounting",
	"Financial Reports",
	"Payables",
	"Receivables",
	"Assets",
	"Buying",
	"ERPNext Integrations",
	"Manufacturing",
	"Projects",
	"Quality",
	"Selling",
	"ERPNext Settings",
	"Home",
	"Stock",
	"Support",
	"Employee Lifecycle",
	"Expense Claims",
	"HR",
	"Leaves",
	"Recruitment",
	"Shift & Attendance",
	"Payroll",
	"Salary Payout",
	"Tax & Benefits",
)

MANAGED_WORKSPACES = CUSTOM_WORKSPACES + CHANGED_STANDARD_WORKSPACES
MANAGED_DASHBOARD_CHARTS = (
	"Incoming Bills (Purchase Invoice)",
	"Outgoing Bills (Sales Invoice)",
	"Profit and Loss",
)
ALLOWED_APPS = {"frappe", "erpnext", "hrms"}


def _origin_app(doctype: str, name: str) -> str | None:
	if not frappe.db.exists(doctype, name):
		return None
	module = frappe.db.get_value(doctype, name, "module")
	return frappe.db.get_value("Module Def", module, "app_name") if module else "frappe"


def _workspace_dependencies(workspace: dict):
	for row in workspace.get("links") or []:
		if row.get("link_to") and row.get("link_type") in {"DocType", "Report", "Page"}:
			yield "links", row, row["link_type"], row["link_to"]

	for row in workspace.get("shortcuts") or []:
		if row.get("link_to") and row.get("type") in {"DocType", "Report", "Page"}:
			yield "shortcuts", row, row["type"], row["link_to"]

	for row in workspace.get("quick_lists") or []:
		if row.get("document_type"):
			yield "quick_lists", row, "DocType", row["document_type"]

	for row in workspace.get("charts") or []:
		if row.get("chart_name"):
			yield "charts", row, "Dashboard Chart", row["chart_name"]

	for row in workspace.get("number_cards") or []:
		if row.get("number_card_name"):
			yield "number_cards", row, "Number Card", row["number_card_name"]

	for row in workspace.get("custom_blocks") or []:
		if row.get("custom_block_name"):
			yield "custom_blocks", row, "Custom HTML Block", row["custom_block_name"]


def _recount_link_groups(links: list[dict]) -> None:
	for index, row in enumerate(links):
		if row.get("type") != "Card Break":
			continue
		count = 0
		for following in links[index + 1 :]:
			if following.get("type") == "Card Break":
				break
			count += 1
		row["link_count"] = count


def _clean_workspace_links(workspace: dict) -> None:
	cleaned: list[dict] = []
	seen_in_group: set[tuple[str | None, str | None]] = set()
	for row in workspace.get("links") or []:
		if row.get("type") == "Card Break":
			seen_in_group.clear()
			cleaned.append(row)
			continue

		if (
			workspace.get("name") == "General Reports"
			and (row.get("label") or "").strip() == "Total Stock Summary"
		):
			row["link_to"] = "Total Stock Summary"

		key = (row.get("link_type"), row.get("link_to"))
		if row.get("type") == "Link" and key in seen_in_group:
			continue
		if row.get("type") == "Link":
			seen_in_group.add(key)
		cleaned.append(row)

	workspace["links"] = cleaned
	_recount_link_groups(cleaned)


def _remove_external_dependencies(workspace: dict) -> None:
	removals: dict[str, set[str]] = {}
	for fieldname, _row, doctype, target in _workspace_dependencies(workspace):
		app_name = _origin_app(doctype, target)
		if app_name and app_name not in ALLOWED_APPS:
			removals.setdefault(fieldname, set()).add(target)

	field_target_keys = {
		"links": "link_to",
		"shortcuts": "link_to",
		"quick_lists": "document_type",
		"charts": "chart_name",
		"number_cards": "number_card_name",
		"custom_blocks": "custom_block_name",
	}
	for fieldname, targets in removals.items():
		target_key = field_target_keys[fieldname]
		workspace[fieldname] = [
			row for row in workspace.get(fieldname) or [] if row.get(target_key) not in targets
		]

	_clean_workspace_links(workspace)

	content = json.loads(workspace.get("content") or "[]")
	content_mapping = {
		"shortcut": ("shortcut_name", removals.get("shortcuts", set())),
		"quick_list": ("quick_list_name", removals.get("quick_lists", set())),
		"chart": ("chart_name", removals.get("charts", set())),
		"number_card": ("number_card_name", removals.get("number_cards", set())),
		"custom_block": ("custom_block_name", removals.get("custom_blocks", set())),
	}
	workspace["content"] = json.dumps(
		[
			block
			for block in content
			if not (
				block.get("type") in content_mapping
				and block.get("data", {}).get(content_mapping[block["type"]][0])
				in content_mapping[block["type"]][1]
			)
		],
		ensure_ascii=False,
		separators=(",", ":"),
	)


def load_bundle() -> dict:
	if not BUNDLE_PATH.exists():
		frappe.throw(f"Workspace bundle is missing: {BUNDLE_PATH}")

	with BUNDLE_PATH.open(encoding="utf-8") as bundle_file:
		bundle = json.load(bundle_file)

	if bundle.get("bundle_version") != BUNDLE_VERSION:
		frappe.throw(
			f"Unsupported workspace bundle version {bundle.get('bundle_version')!r}; "
			f"expected {BUNDLE_VERSION!r}"
		)
	return bundle


def audit_bundle() -> dict:
	"""Report missing workspace link targets and the apps they come from."""
	bundle = load_bundle()
	missing: list[dict] = []
	apps: set[str] = set()
	external_links: list[dict] = []

	for workspace in bundle.get("documents", {}).get("Workspace", []):
		for fieldname, _row, target_doctype, target in _workspace_dependencies(workspace):
			if not frappe.db.exists(target_doctype, target):
				missing.append(
					{
						"workspace": workspace["name"],
						"field": fieldname,
						"type": target_doctype,
						"target": target,
					}
				)
				continue

			app_name = _origin_app(target_doctype, target)
			if app_name:
				apps.add(app_name)
				if app_name not in ALLOWED_APPS:
					external_links.append(
						{
							"workspace": workspace["name"],
							"field": fieldname,
							"type": target_doctype,
							"target": target,
							"app": app_name,
						}
					)

	return {"missing": missing, "apps": sorted(apps), "external_links": external_links}


def _document_payload(doctype: str, name: str) -> dict | None:
	if not frappe.db.exists(doctype, name):
		return None

	doc = frappe.get_doc(doctype, name).as_dict(no_nulls=False)
	doc.pop("__onload", None)
	return doc


def capture_current_state() -> dict:
	"""Return an exact, JSON-serialisable snapshot of managed records."""
	return {
		"captured_at": str(now_datetime()),
		"bundle_version": BUNDLE_VERSION,
		"documents": {
			"Workspace": [
				doc
				for name in MANAGED_WORKSPACES
				if (doc := _document_payload("Workspace", name)) is not None
			],
			"Dashboard Chart": [
				doc
				for name in MANAGED_DASHBOARD_CHARTS
				if (doc := _document_payload("Dashboard Chart", name)) is not None
			],
		},
	}


def export_bundle() -> str:
	"""Export the approved records from the current site into this app.

	This is an explicit developer command. It is never called by install or
	migrate, so a customer's changes cannot leak back into the distributed
	baseline.
	"""
	payload = capture_current_state()
	payload["source_site"] = frappe.local.site
	for workspace in payload["documents"]["Workspace"]:
		_remove_external_dependencies(workspace)
	BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
	with BUNDLE_PATH.open("w", encoding="utf-8") as bundle_file:
		json.dump(payload, bundle_file, ensure_ascii=False, indent=2, sort_keys=True, default=str)
		bundle_file.write("\n")
	return str(BUNDLE_PATH)


def _import_document(payload: dict) -> None:
	payload = deepcopy(payload)
	doctype = payload["doctype"]
	name = payload["name"]
	desired_hidden = payload.get("is_hidden") if doctype == "Workspace" else None

	# Frappe's standard importer performs a complete child-table replacement.
	# Workspace.is_hidden is intentionally preserved from the old record by the
	# framework, so set the bundled value explicitly on first installation.
	import_doc(payload, ignore_version=True)
	if desired_hidden is not None:
		frappe.db.set_value(doctype, name, "is_hidden", int(desired_hidden), update_modified=False)


def apply_bundle() -> dict[str, int]:
	"""Apply the baseline once. This function is not attached to migrate."""
	bundle = load_bundle()
	counts: dict[str, int] = {}
	for doctype, documents in bundle.get("documents", {}).items():
		for document in documents:
			_import_document(document)
		counts[doctype] = len(documents)

	frappe.clear_cache()
	return counts

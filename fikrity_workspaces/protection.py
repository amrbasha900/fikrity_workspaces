from __future__ import annotations

import json

import frappe

from fikrity_workspaces.bundle import (
	_import_document,
	capture_current_state,
	get_managed_document_names,
)


def before_migrate() -> None:
	"""Snapshot customer state once before standard workspace synchronisation."""
	if not frappe.db.exists("DocType", "Fikrity Workspace Settings"):
		return

	settings = frappe.get_single("Fikrity Workspace Settings")
	# A non-empty snapshot means a previous migration did not reach the restore
	# hook. Never replace that known-good state with a partially migrated one.
	if settings.pending_migration_snapshot:
		return

	settings.pending_migration_snapshot = json.dumps(
		capture_current_state(), ensure_ascii=False, sort_keys=True, default=str
	)
	settings.save(ignore_permissions=True)


def after_migrate() -> None:
	"""Restore exactly what the customer had before migrate, then clear backup."""
	if not frappe.db.exists("DocType", "Fikrity Workspace Settings"):
		return

	settings = frappe.get_single("Fikrity Workspace Settings")
	if not settings.pending_migration_snapshot:
		return

	snapshot = json.loads(settings.pending_migration_snapshot)
	managed_documents = get_managed_document_names()
	for doctype, documents in snapshot.get("documents", {}).items():
		for document in documents:
			_import_document(document)

		# A deletion is a customer change too. Standard app sync can recreate a
		# deleted managed record; remove it again when it was absent before migrate.
		snapshot_names = {document["name"] for document in documents}
		for name in managed_documents.get(doctype, set()) - snapshot_names:
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

	settings.pending_migration_snapshot = ""
	settings.save(ignore_permissions=True)
	frappe.clear_cache()

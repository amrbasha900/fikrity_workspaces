import json
import unittest

from fikrity_workspaces.bundle import BUNDLE_VERSION, load_bundle


class TestWorkspaceBundle(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.bundle = load_bundle()
		cls.provided = {
			doctype: {document["name"] for document in documents}
			for doctype, documents in cls.bundle["documents"].items()
		}

	def test_version_and_workspace_count(self):
		self.assertEqual(self.bundle["bundle_version"], BUNDLE_VERSION)
		self.assertEqual(len(self.bundle["documents"]["Workspace"]), 32)

	def test_document_names_are_unique(self):
		for doctype, documents in self.bundle["documents"].items():
			names = [document["name"] for document in documents]
			self.assertEqual(len(names), len(set(names)), doctype)

	def test_every_content_widget_is_bundled(self):
		widget_fields = {
			"chart": ("chart_name", "Dashboard Chart"),
			"number_card": ("number_card_name", "Number Card"),
			"custom_block": ("custom_block_name", "Custom HTML Block"),
		}
		missing = []
		for workspace in self.bundle["documents"]["Workspace"]:
			for block in json.loads(workspace.get("content") or "[]"):
				if block.get("type") not in widget_fields:
					continue
				fieldname, doctype = widget_fields[block["type"]]
				name = block.get("data", {}).get(fieldname)
				if name and name not in self.provided.get(doctype, set()):
					missing.append((workspace["name"], doctype, name))

		self.assertEqual(missing, [])

	def test_report_page_charts_are_bundled(self):
		charts = self.provided["Dashboard Chart"]
		self.assertIn("Balance Sheet", charts)
		self.assertIn("Cash Flow", charts)

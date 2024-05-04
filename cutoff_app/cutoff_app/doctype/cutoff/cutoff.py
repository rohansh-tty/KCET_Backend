# Copyright (c) 2024, Rohan Shetty  and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Cutoff(Document):
	pass


@frappe.whitelist(allow_guest=True)
def get_result(cutoff, branch, category, year, round):
    pass
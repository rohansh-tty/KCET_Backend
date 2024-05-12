# Copyright (c) 2024, Rohan Shetty  and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class College(Document):
	def on_update(self):
		# TODO: update Cutoff Doc of this college
		college_cutoff_list = frappe.db.get_all('Cutoff', filters={'college_code': self.college_code})
		for doc in college_cutoff_list:
			cutoff_doc = frappe.get_doc('Cutoff', doc['name'])
			cutoff_doc.college_name = self.college_name
			cutoff_doc.save()
			frappe.db.commit()
			print(f'updated {cutoff_doc.college_code} with {cutoff_doc.college_name} in cutoff db')
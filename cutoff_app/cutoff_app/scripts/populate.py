import json 
import frappe 


def add_college():
    with open('/workspace/development/frappe-bench/apps/cutoff_app/cutoff_app/cutoff_app/data/college.json') as f:
        college = json.load(f)
        college_list = college['data']
        for college in college_list:
            print(college)
            college_exists = frappe.db.exists('College', college['code'])
            if len(college['college_name'])>0 and not college_exists:
                print(f'inserting {college} ')
                new_college_doc = frappe.new_doc('College')
                new_college_doc.college_name =  college['college_name']
                new_college_doc.college_code = college['code']
                new_college_doc.location = college['location']
                new_college_doc.insert()
                new_college_doc.save()
                frappe.db.commit()
                print(f'inserted {college["college_name"]} to db')
                

def add_cutoff():
    with open('/workspace/development/frappe-bench/apps/cutoff_app/cutoff_app/cutoff_app/data/cutoff.json') as f:
        cutoff = json.load(f)
        cutoff_list = cutoff['data']
        for cutoff_info in cutoff_list:
            cutoff_doc_exists = frappe.db.exists({"doctype": "Cutoff", "college_code": cutoff_info['College Code'], "branch": cutoff_info['Branch'].strip().split(' ')[0], "category": cutoff_info['Category'], "year": cutoff_info['Year'], "cutoff": cutoff_info['Cutoff'], "round": cutoff_info['Round']})
            college_doc_exists = frappe.db.exists({"doctype": "College", "college_code": cutoff_info['College Code']})
            if not cutoff_info['Cutoff']  == "--":
                if not cutoff_doc_exists and college_doc_exists:
                    new_cutoff_doc = frappe.new_doc('Cutoff')
                    new_cutoff_doc.college_code = cutoff_info['College Code']
                    new_cutoff_doc.branch = cutoff_info['Branch'].strip().split(' ')[0]
                    new_cutoff_doc.category = cutoff_info['Category']
                    new_cutoff_doc.year = cutoff_info['Year']
                    new_cutoff_doc.cutoff = cutoff_info['Cutoff']
                    new_cutoff_doc.round = cutoff_info['Round']
                    new_cutoff_doc.insert()
                    new_cutoff_doc.save()
                    frappe.db.commit()
                    print(f'inserted {cutoff_info["Branch"].strip().split(" ")[0]} of {cutoff_info["College Code"]} with {cutoff_info["Cutoff"]} to cutoff db')
                elif not college_doc_exists:
                    print(f'College with code {cutoff_info["College Code"]} does not exist in College db')
                    
caste_category_columns = ['1G',
 '1K',
 '1R',
 '2AG',
 '2AK',
 '2AR',
 '2BG',
 '2BK',
 '2BR',
 '3AG',
 '3AK',
 '3AR',
 '3BG',
 '3BK',
 '3BR',
 'GM',
 'GMK',
 'GMR',
 'SCG',
 'SCK',
 'SCR',
 'STG',
 'STK',
 'STR']                 
def add_category():
    for category in caste_category_columns:
        category_doc_exists = frappe.db.exists({"doctype": "Category", "category_name": category})
        if not category_doc_exists:
            new_category_doc = frappe.new_doc('Category')
            new_category_doc.category_name = category
            new_category_doc.insert()
            new_category_doc.save()
            frappe.db.commit()
            print(f'inserted {category} to category db')
        else:
            print(f'{category} already exists in category db')
        
        
def add_branch():
    with open('/workspace/development/frappe-bench/apps/cutoff_app/cutoff_app/cutoff_app/data/cutoff.json') as f:
        cutoff = json.load(f)
        cutoff_list = cutoff['data']
        for cutoff_info in cutoff_list:
            branch_doc_exists = frappe.db.exists({"doctype": "Branch", "branch_short_name": cutoff_info['Branch'].strip().split(' ')[0]})
            
            if not branch_doc_exists:
                    new_branch_doc = frappe.new_doc('Branch')
                    new_branch_doc.branch_name = ' '.join(cutoff_info['Branch'].strip().split(' ')[1:])
                    new_branch_doc.branch_short_name = cutoff_info['Branch'].strip().split(' ')[0]
                    new_branch_doc.insert()
                    new_branch_doc.save()
                    frappe.db.commit()
                    print(f'inserted {cutoff_info["Branch"].strip().split(" ")[0]} of {cutoff_info["College Code"]} with {cutoff_info["Cutoff"]} to cutoff db')
            else:
                print(f'{cutoff_info["Branch"].strip().split(" ")[0]} already exists in branch db')
                
def add_college_name_in_cutoff():
    cutoff_list = frappe.db.get_all("Cutoff")
    for cutoff in cutoff_list:
        try:
            cutoff_doc = frappe.get_doc('Cutoff', cutoff['name'])
            college_doc = frappe.get_doc('College', {'college_code': cutoff_doc.college_code})
            cutoff_doc.college_name = college_doc.college_name
            cutoff_doc.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            print(f'faild to add college name to cutoff doc {cutoff["name"]}')
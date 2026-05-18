from logger_config import setup_logging
import logging
setup_logging(level=logging.INFO, log_file="app.log")

from agent_pipeline import SOPToCodeConverter
from tools_helper import load_tools_from_toolspec_json

#Load sop
#ToDo: Consider taking sop file path as user input
sop_dir='patient_intake_sop'
sop_file=f'/Users/maddukuri/Desktop/Papers/all_sops/{sop_dir}/sop.txt'
output_file=f'/Users/maddukuri/Desktop/Papers/all_sops/{sop_dir}/workflow_1.py'
with open(sop_file, 'r') as file:
    sop = file.read()

tools = load_tools_from_toolspec_json(f'/Users/maddukuri/Desktop/Papers/all_sops/{sop_dir}/toolspecs.json')
converter = SOPToCodeConverter()
result = converter.convert(sop, tools)

# Execute the workflow
input_data = {
    "patient_id": "P100045",
    "insurance_provider": "Blue Cross",
    "policy_number": "BC123456",
    "group_number": "GRP001",
    "coverage_start_date": "2024-01-01",
    "insurance_type": "Private",
    "preferred_pharmacy_name": "CVS Pharmacy",
    "preferred_pharmacy_address": "123 Main St",
    "pharmacy_phone": "555-0123",
    "smoking_status": "Never",
    "alcohol_consumption": "Occasional",
    "exercise_frequency": "3 times per week",
    "previous_surgeries": ["Appendectomy"],
    "chronic_conditions": ["Hypertension"]
}


input_data_2 = {
    "patient_id": "P100012",
    "insurance_provider": "Aetna",
    "policy_number": "INS567890",
    "group_number": "GRP789012",
    "coverage_start_date": "2023-06-01",
    "insurance_type": "Private",
    "preferred_pharmacy_name": "CVS Pharmacy",
    "preferred_pharmacy_address": "51414 Fake Street",
    "pharmacy_phone": "555-777-9999",
    "smoking_status": "Never",
    "alcohol_consumption": "Occasional",
    "exercise_frequency": "5 times per week",
    "previous_surgeries": ["None"],
    "chronic_conditions": ["None"]
}
with open(output_file, "w+") as f:
  f.write(result["code"])
#final_result = execute_workflow(result["code"], input_data)
#print(f"Result: {final_result}")



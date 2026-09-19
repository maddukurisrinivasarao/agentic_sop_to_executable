import argparse
import os

from logger_config import setup_logging
import logging
setup_logging(level=logging.INFO, log_file="app.log")

from agent_pipeline import SOPToCodeConverter
from tools_helper import load_tools_from_toolspec_json

parser = argparse.ArgumentParser(description="Convert an SOP into an executable workflow.")
parser.add_argument(
    "sop_dir",
    help="Path to the SOP directory (must contain sop.txt and toolspecs.json)",
)
args = parser.parse_args()

sop_dir = args.sop_dir
sop_file = os.path.join(sop_dir, "sop.txt")
output_file = os.path.join(sop_dir, "workflow.py")
with open(sop_file, 'r') as file:
    sop = file.read()

tools = load_tools_from_toolspec_json(os.path.join(sop_dir, "toolspecs.json"))
converter = SOPToCodeConverter()
result = converter.convert(sop, tools)

with open(output_file, "w+") as f:
  f.write(result["code"])
#final_result = execute_workflow(result["code"], input_data)
#print(f"Result: {final_result}")



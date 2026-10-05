from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # ---------- Input casting ----------
        po_number = input_data["po_number"]
        confirmed_product_id = input_data["confirmed_product_id"]
        received_product_bar_code = input_data["received_product_bar_code"]
        package_image_path = input_data["package_image_path"]
        ordered_quantity = int(input_data["ordered_quantity"])
        confirmed_quantity = int(input_data["confirmed_quantity"])
        received_quantity = int(input_data["received_quantity"])
        intended_warehouse_id = input_data["intended_warehouse_id"]
        actual_warehouse_id = input_data["actual_warehouse_id"]
        unit_cost = float(input_data["unit_cost"])
        chargeable_input = str(input_data["chargeable"]).strip().lower() == "true"

        # ---------- Step 1: Validate barcode ----------
        barcode_result = manager.validateBarcode(
            po_number=po_number,
            confirmed_product_id=confirmed_product_id,
            received_product_bar_code=received_product_bar_code,
        )
        barcode_match = barcode_result["barcode_match"]
        problem_type = list(barcode_result["problem_type"])  # may contain 'Wrong Item'
        resolution_status = barcode_result["resolution_status"]

        # ---------- Step 2: Assess package condition ----------
        condition_result = manager.assessPackageCondition(
            po_number=po_number,
            package_image_path=package_image_path,
        )
        package_condition = condition_result["package_condition"]
        # Append any condition problems
        problem_type.extend(condition_result["problem_type"])

        # If barcode mismatch, skip further quantitative checks and chargeback calculation
        if not barcode_match:
            # Ensure charge_back_amt is zero when barcode is wrong
            charge_back_amt = 0
            # Final resolution_status already set to "Returned to Vendor" by barcode step
            return {
                "problem_type": problem_type,
                "resolution_status": resolution_status,
                "package_condition": package_condition,
                "barcode_match": barcode_match,
                "charge_back_amt": charge_back_amt,
            }

        # ---------- Step 3: Calculate quantity variance ----------
        variance_result = manager.calculateQuantityVariance(
            po_number=po_number,
            ordered_quantity=ordered_quantity,
            confirmed_quantity=confirmed_quantity,
            received_quantity=received_quantity,
        )
        # quantity_variance = variance_result["quantity_variance"]  # not needed for output
        problem_type.extend(variance_result["problem_type"])

        # ---------- Step 4: Verify warehouse location ----------
        location_result = manager.verifyWarehouseLocation(
            po_number=po_number,
            intended_warehouse_id=intended_warehouse_id,
            actual_warehouse_id=actual_warehouse_id,
        )
        # location_match = location_result["location_match"]  # not needed for output
        problem_type.extend(location_result["problem_type"])

        # ---------- Step 5: Calculate chargeback amount ----------
        chargeback_result = manager.calculateChargeback(
            po_number=po_number,
            problem_type=problem_type,
            ordered_quantity=ordered_quantity,
            received_quantity=received_quantity,
            unit_cost=unit_cost,
        )
        charge_back_amt = chargeback_result["charge_amount"]

        # ---------- Step 6: Update resolution status ----------
        # Determine current status before update
        current_status = "Processing" if problem_type else "Pending"
        resolution_result = manager.updateResolutionStatus(
            po_number=po_number,
            problem_type=problem_type,
            current_status=current_status,
            chargeable=chargeable_input,
        )
        resolution_status = resolution_result["resolution_status"]

        # ---------- Final output assembly ----------
        return {
            "problem_type": problem_type,
            "resolution_status": resolution_status,
            "package_condition": package_condition,
            "barcode_match": barcode_match,
            "charge_back_amt": charge_back_amt,
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
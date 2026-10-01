from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # --- Input casting ---
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
        chargeable_flag = str(input_data["chargeable"]).strip().lower() == "true"
        vendor_id = input_data["vendor_id"]
        vendor_name = input_data["vendor_name"]
        product_name = input_data["product_name"]
        QVT = float(input_data["QVT"]) if "QVT" in input_data and input_data["QVT"] != "" else 5.0

        # Initialize aggregate containers
        aggregated_problems = []

        # Step 1: Validate received barcode against confirmed product ID
        barcode_res = manager.validateBarcode(
            po_number=po_number,
            confirmed_product_id=confirmed_product_id,
            received_product_bar_code=received_product_bar_code,
        )
        barcode_match = barcode_res["barcode_match"]
        if not barcode_match:
            aggregated_problems.extend(barcode_res["problem_type"])  # ['Wrong Item']
            resolution_status = barcode_res["resolution_status"]   # "Returned to Vendor"
        else:
            resolution_status = "Pending"

        # Step 2: Assess physical condition of the package (always executed)
        package_res = manager.assessPackageCondition(
            po_number=po_number,
            package_image_path=package_image_path,
        )
        package_condition = package_res["package_condition"]
        if package_res["problem_type"]:
            aggregated_problems.extend(package_res["problem_type"])  # e.g., ['Vendor Damaged']

        # Conditional steps only if barcode matched
        if barcode_match:
            # Step 3: Calculate quantity variance and identify quantity‑related problems
            qty_res = manager.calculateQuantityVariance(
                po_number=po_number,
                ordered_quantity=ordered_quantity,
                confirmed_quantity=confirmed_quantity,
                received_quantity=received_quantity,
                QVT=QVT,
            )
            if qty_res["problem_type"]:
                aggregated_problems.extend(qty_res["problem_type"])

            # Step 4: Verify shipment delivered to intended warehouse
            loc_res = manager.verifyWarehouseLocation(
                po_number=po_number,
                intended_warehouse_id=intended_warehouse_id,
                actual_warehouse_id=actual_warehouse_id,
            )
            if not loc_res["location_match"]:
                aggregated_problems.extend(loc_res["problem_type"])  # ['Wrong Warehouse']

            # Step 5: Calculate vendor chargeback amount based on identified problems
            charge_res = manager.calculateChargeback(
                po_number=po_number,
                problem_type=aggregated_problems,
                ordered_quantity=ordered_quantity,
                received_quantity=received_quantity,
                unit_cost=unit_cost,
            )
            charge_back_amt = charge_res["charge_amount"]

            # Step 6: Update resolution status according to problem list and chargeable flag
            upd_res = manager.updateResolutionStatus(
                po_number=po_number,
                problem_type=aggregated_problems,
                current_status=resolution_status,
                chargeable=chargeable_flag,
            )
            resolution_status = upd_res["resolution_status"]
        else:
            # Barcode mismatch path: skip quantity, location, and chargeback calculations
            charge_back_amt = 0

        # Final output assembly
        return {
            "problem_type": aggregated_problems,
            "resolution_status": resolution_status,
            "package_condition": package_condition,
            "barcode_match": barcode_match,
            "charge_back_amt": charge_back_amt,
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
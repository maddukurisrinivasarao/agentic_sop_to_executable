from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Cast and prepare input values
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
        QVT = float(input_data["QVT"]) if "QVT" in input_data and input_data["QVT"] != "" else 5.0

        # Step 1: Validate received product barcode against confirmed product ID
        barcode_res = manager.validateBarcode(
            po_number=po_number,
            confirmed_product_id=confirmed_product_id,
            received_product_bar_code=received_product_bar_code,
        )
        barcode_match = barcode_res["barcode_match"]
        problem_type = []  # will accumulate all identified problems
        problem_type.extend(barcode_res["problem_type"])

        # Step 2: Assess physical condition of the package (always executed)
        condition_res = manager.assessPackageCondition(
            po_number=po_number,
            package_image_path=package_image_path,
        )
        package_condition = condition_res["package_condition"]
        problem_type.extend(condition_res["problem_type"])

        # Early termination if barcode does NOT match (Wrong Item)
        if not barcode_match:
            # Resolve status is already set by barcode validation
            resolution_status = barcode_res["resolution_status"]
            charge_back_amt = 0

            # Generate problem report (optional, result not used further)
            manager.generateProblemReport(
                po_number=po_number,
                vendor_id=vendor_id,
                vendor_name=vendor_name,
                problem_type=problem_type,
                charge_amount=charge_back_amt,
                resolution_status=resolution_status,
            )

            return {
                "problem_type": problem_type,
                "resolution_status": resolution_status,
                "package_condition": package_condition,
                "barcode_match": barcode_match,
                "charge_back_amt": charge_back_amt,
            }

        # Step 3: Calculate quantity variance and identify quantity-related problems
        qty_var_res = manager.calculateQuantityVariance(
            po_number=po_number,
            ordered_quantity=ordered_quantity,
            confirmed_quantity=confirmed_quantity,
            received_quantity=received_quantity,
            QVT=QVT,
        )
        # quantity_variance = qty_var_res["quantity_variance"]  # not required for output
        problem_type.extend(qty_var_res["problem_type"])

        # Step 4: Verify shipment delivered to correct warehouse
        location_res = manager.verifyWarehouseLocation(
            po_number=po_number,
            intended_warehouse_id=intended_warehouse_id,
            actual_warehouse_id=actual_warehouse_id,
        )
        problem_type.extend(location_res["problem_type"])

        # Step 5: Calculate vendor chargeback amount based on identified problems
        chargeback_res = manager.calculateChargeback(
            po_number=po_number,
            problem_type=problem_type,
            ordered_quantity=ordered_quantity,
            received_quantity=received_quantity,
            unit_cost=unit_cost,
        )
        charge_back_amt = chargeback_res["charge_amount"]

        # Step 6: Update resolution status according to problem list and chargeable flag
        # Initialize current status as "Pending"
        update_res = manager.updateResolutionStatus(
            po_number=po_number,
            problem_type=problem_type,
            current_status="Pending",
            chargeable=chargeable_flag,
        )
        resolution_status = update_res["resolution_status"]

        # Step 7: Generate comprehensive problem classification report
        manager.generateProblemReport(
            po_number=po_number,
            vendor_id=vendor_id,
            vendor_name=vendor_name,
            problem_type=problem_type,
            charge_amount=charge_back_amt,
            resolution_status=resolution_status,
        )

        # Combine results into final output dictionary
        return {
            "problem_type": problem_type,
            "resolution_status": resolution_status,
            "package_condition": package_condition,
            "barcode_match": barcode_match,
            "charge_back_amt": charge_back_amt,
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
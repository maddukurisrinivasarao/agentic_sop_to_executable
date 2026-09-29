from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Extract and cast input parameters
        po_number = input_data["po_number"]
        confirmed_product_id = input_data["confirmed_product_id"]
        received_product_bar_code = input_data["received_product_bar_code"]
        package_image_path = input_data["package_image_path"]
        intended_warehouse_id = input_data["intended_warehouse_id"]
        actual_warehouse_id = input_data["actual_warehouse_id"]
        ordered_quantity = int(input_data["ordered_quantity"])
        confirmed_quantity = int(input_data["confirmed_quantity"])
        received_quantity = int(input_data["received_quantity"])
        unit_cost = float(input_data["unit_cost"])
        vendor_id = input_data["vendor_id"]
        vendor_name = input_data["vendor_name"]
        product_name = input_data["product_name"]
        QVT = float(input_data["QVT"]) if "QVT" in input_data and input_data["QVT"] != "" else 5.0

        # Step 1: Validate received barcode against confirmed product ID
        barcode_res = manager.validateBarcode(
            po_number=po_number,
            confirmed_product_id=confirmed_product_id,
            received_product_bar_code=received_product_bar_code,
        )
        barcode_match = barcode_res["barcode_match"]
        problem_type = list(barcode_res["problem_type"])
        resolution_status = barcode_res["resolution_status"]

        # Step 2: Assess physical condition of the package (always executed)
        package_res = manager.assessPackageCondition(
            po_number=po_number,
            package_image_path=package_image_path,
        )
        package_condition = package_res["package_condition"]
        problem_type.extend(package_res["problem_type"])

        # Early termination if barcode does not match
        if not barcode_match:
            charge_back_amt = 0
            return {
                "problem_type": problem_type,
                "resolution_status": resolution_status,
                "package_condition": package_condition,
                "barcode_match": barcode_match,
                "charge_back_amt": charge_back_amt,
            }

        # Step 3: Verify shipment delivered to intended warehouse
        location_res = manager.verifyWarehouseLocation(
            po_number=po_number,
            intended_warehouse_id=intended_warehouse_id,
            actual_warehouse_id=actual_warehouse_id,
        )
        problem_type.extend(location_res["problem_type"])

        # Step 4: Calculate quantity variance and related problems
        quantity_res = manager.calculateQuantityVariance(
            po_number=po_number,
            ordered_quantity=ordered_quantity,
            confirmed_quantity=confirmed_quantity,
            received_quantity=received_quantity,
            QVT=QVT,
        )
        problem_type.extend(quantity_res["problem_type"])

        # Step 5: Calculate chargeback amount for identified problems
        chargeback_res = manager.calculateChargeback(
            po_number=po_number,
            problem_type=problem_type,
            ordered_quantity=ordered_quantity,
            received_quantity=received_quantity,
            unit_cost=unit_cost,
        )
        charge_back_amt = chargeback_res["charge_amount"] if chargeback_res["chargeable"] else 0

        # Step 6: Update resolution status based on accumulated problems
        # Initialize status as Pending if not already set
        if not resolution_status:
            resolution_status = "Pending"
        update_res = manager.updateResolutionStatus(
            po_number=po_number,
            problem_type=problem_type,
            current_status=resolution_status,
        )
        resolution_status = update_res["resolution_status"]

        # Step 7: Generate final problem classification report (optional)
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
from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Validate aircraft identification and clearance
        aircraft_clearance_result = manager.VerifyAircraftClearance(
            aircraft_id=input_data["aircraft_id"],
            tail_number=input_data["tail_number"],
            maintenance_record_id=input_data["maintenance_record_id"],
            expected_departure_time=input_data["expected_departure_time"],
        )

        # Step 2: Inspect mechanical component details
        mechanical_inspection_result = manager.VerifyMechanicalComponents(
            aircraft_id=input_data["aircraft_id"],
            component_serial_number=input_data["component_serial_number"],
            inspection_location_id=input_data["inspection_location_id"],
            component_weight=float(input_data["component_weight"]),
            physical_condition_observation=input_data["physical_condition_observation"],
            installation_time=input_data["installation_time"],
        )

        # Step 3: Authenticate electrical systems
        electrical_inspection_result = manager.VerifyElectricalSystems(
            aircraft_id=input_data["aircraft_id"],
            battery_status=input_data["battery_status"],
            circuit_continuity_check=input_data["circuit_continuity_check"],
            avionics_diagnostics_response=input_data["avionics_diagnostics_response"],
        )

        # Step 4: Cross‑check component specifications
        cross_check_result = manager.CrossCheckSpecifications(
            aircraft_id=input_data["aircraft_id"],
            component_weight=float(input_data["component_weight"]),
            expected_component_weight=float(input_data["expected_component_weight"]),
            installation_time=input_data["installation_time"],
            actual_inspection_time=input_data["actual_inspection_time"],
        )

        # Step 5: Report any mechanical or electrical inspection incident
        component_incident_response = manager.ReportComponentIncident(
            aircraft_id=input_data["aircraft_id"],
            mechanical_inspection_result=mechanical_inspection_result,
            electrical_inspection_result=electrical_inspection_result,
        )

        # Step 6: Report component serial number mismatch (if any)
        component_mismatch_response = manager.ReportComponentMismatch(
            aircraft_id=input_data["aircraft_id"],
            component_serial_number=input_data["component_serial_number"],
            installed_component_serial_number=input_data["installed_component_serial_number"],
            inspection_location_id=input_data["inspection_location_id"],
        )

        # Step 7: Reconcile maintenance record discrepancies
        cross_check_reporting_response = manager.ReportCrossCheck(
            maintenance_record_id=input_data["maintenance_record_id"],
            aircraft_id=input_data["aircraft_id"],
            component_incident_response=component_incident_response,
            component_mismatch_response=component_mismatch_response,
        )

        # Determine overall aircraft readiness based on clearance result
        aircraft_ready = "TRUE" if str(aircraft_clearance_result).lower() == "success" else "FALSE"

        # Assemble final report matching SOP output fields
        return {
            "aircraft_id": input_data["aircraft_id"],
            "aircraft_ready": aircraft_ready,
            "VerifyShipment": aircraft_clearance_result,
            "mechanical_inspection_result": mechanical_inspection_result,
            "electrical_inspection_result": electrical_inspection_result,
            "component_incident_response": component_incident_response,
            "component_mismatch_response": component_mismatch_response,
            "cross_check_reporting_response": cross_check_reporting_response,
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
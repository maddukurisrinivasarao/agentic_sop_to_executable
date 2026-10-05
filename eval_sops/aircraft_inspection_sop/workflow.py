from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Validate aircraft identification and maintenance record
        aircraft_clearance = manager.VerifyAircraftClearance(
            aircraft_id=input_data["aircraft_id"],
            tail_number=input_data["tail_number"],
            maintenance_record_id=input_data["maintenance_record_id"],
            expected_departure_time=input_data["expected_departure_time"],
        )
        # aircraft_clearance contains: {"aircraft_ready": "True" or "False"}

        # Step 2: Inspect mechanical components
        mechanical_result = manager.VerifyMechanicalComponents(
            aircraft_id=input_data["aircraft_id"],
            component_serial_number=input_data["component_serial_number"],
            inspection_location_id=input_data["inspection_location_id"],
            component_weight=float(input_data["component_weight"]),
            physical_condition_observation=input_data["physical_condition_observation"],
            installation_time=input_data["installation_time"],
        )
        # mechanical_result contains: {"mechanical_inspection_result": "..."} 

        # Step 3: Authenticate electrical systems
        electrical_result = manager.VerifyElectricalSystems(
            aircraft_id=input_data["aircraft_id"],
            battery_status=input_data["battery_status"],
            circuit_continuity_check=input_data["circuit_continuity_check"],
            avionics_diagnostics_response=input_data["avionics_diagnostics_response"],
        )
        # electrical_result contains: {"electrical_inspection_result": "..."} 

        # Step 4: Cross‑check component specifications (weight & installation time)
        spec_cross_check = manager.CrossCheckSpecifications(
            aircraft_id=input_data["aircraft_id"],
            component_weight=float(input_data["component_weight"]),
            expected_component_weight=float(input_data["expected_component_weight"]),
            installation_time=input_data["installation_time"],
            actual_inspection_time=input_data["actual_inspection_time"],
        )
        # spec_cross_check contains: {"cross_check_response": "..."} 

        # Step 5: Report any mechanical or electrical inspection failures
        incident_report = manager.ReportComponentIncident(
            aircraft_id=input_data["aircraft_id"],
            mechanical_inspection_result=mechanical_result["mechanical_inspection_result"],
            electrical_inspection_result=electrical_result["electrical_inspection_result"],
        )
        # incident_report contains: {"component_incident_response": "..."} 

        # Step 6: Report component serial number mismatches
        mismatch_report = manager.ReportComponentMismatch(
            aircraft_id=input_data["aircraft_id"],
            component_serial_number=input_data["component_serial_number"],
            installed_component_serial_number=input_data["installed_component_serial_number"],
            inspection_location_id=input_data["inspection_location_id"],
        )
        # mismatch_report contains: {"component_mismatch_response": "..."} 

        # Step 7: Reconcile maintenance records and submit discrepancy report
        cross_check_report = manager.ReportCrossCheck(
            maintenance_record_id=input_data["maintenance_record_id"],
            aircraft_id=input_data["aircraft_id"],
            component_incident_response=incident_report["component_incident_response"],
            component_mismatch_response=mismatch_report["component_mismatch_response"],
        )
        # cross_check_report contains: {"cross_check_reporting_response": "..."} 

        # Assemble final output report
        return {
            "aircraft_id": input_data["aircraft_id"],
            "aircraft_ready": aircraft_clearance["aircraft_ready"],
            # The example uses a separate VerifyShipment flag; map it to aircraft readiness status
            "VerifyShipment": "success" if aircraft_clearance["aircraft_ready"] == "True" else "failed",
            "mechanical_inspection_result": mechanical_result["mechanical_inspection_result"],
            "electrical_inspection_result": electrical_result["electrical_inspection_result"],
            "component_incident_response": incident_report["component_incident_response"],
            "component_mismatch_response": mismatch_report["component_mismatch_response"],
            "cross_check_reporting_response": cross_check_report["cross_check_reporting_response"],
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
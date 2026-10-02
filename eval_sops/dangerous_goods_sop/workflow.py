from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Validate product ID format (must be P_XXXXX where X are digits)
        product_id = input_data["product_id"]
        if not (product_id.startswith("P_") and len(product_id) == 7 and product_id[2:].isdigit()):
            # Early termination due to invalid product ID
            xml_err = (
                "<result>"
                "<hazard_score>0</hazard_score>"
                "<hazard_class>Unable to Decide</hazard_class>"
                "</result>"
            )
            return {
                "hazard_score": 0,
                "hazard_class": "Unable to Decide",
                "registry_entry": None,
                "api_logs": {},
                "audit_trail": "Product ID validation failed.",
                "xml_output": xml_err,
                "status": "failed"
            }

        # Step 2: Calculate SDS label score
        sds_res = manager.calculate_sds_label_score(
            product_id=product_id,
            sds_label_text=input_data["sds_label_text"]
        )
        sds_score = sds_res["sds_label_score"]
        if sds_score < 0 or sds_score > 5:
            raise ValueError("SDS label score out of valid range (0-5)")

        # Step 3: Calculate handling score
        handling_params = {
            "product_id": product_id,
            "handling_and_storage_guidelines": input_data["handling_and_storage_guidelines"]
        }
        if "assessmentFormId" in input_data:
            handling_params["assessmentFormId"] = input_data["assessmentFormId"]
        handling_res = manager.calculate_handling_score(**handling_params)
        handling_score = handling_res["handling_score"]
        if handling_score < 0 or handling_score > 5:
            raise ValueError("Handling score out of valid range (0-5)")

        # Step 4: Calculate transportation score
        transport_res = manager.calculate_transportation_score(
            product_id=product_id,
            transportation_requirements=input_data["transportation_requirements"]
        )
        transport_score = transport_res["transportation_score"]
        if transport_score < 0 or transport_score > 5:
            raise ValueError("Transportation score out of valid range (0-5)")

        # Step 5: Calculate disposal score
        disposal_res = manager.calculate_disposal_score(
            product_id=product_id,
            disposal_guidelines=input_data["disposal_guidelines"]
        )
        disposal_score = disposal_res["disposal_score"]
        if disposal_score < 0 or disposal_score > 5:
            raise ValueError("Disposal score out of valid range (0-5)")

        # Step 6: Hazard score computation with imputation logic
        scores = {
            "safety": sds_score,
            "handling": handling_score,
            "transportation": transport_score,
            "disposal": disposal_score
        }
        missing_keys = [k for k, v in scores.items() if v == 0]

        if len(missing_keys) >= 2:
            hazard_score = 0
            hazard_class = "Unable to Decide"
        else:
            if len(missing_keys) == 1:
                # Impute missing component with max of the others
                max_other = max(v for v in scores.values() if v != 0)
                scores[missing_keys[0]] = max_other
            hazard_score = sum(scores.values())

            # Step 7: Hazard class determination
            if 4 <= hazard_score <= 7:
                hazard_class = "Hazard Class A"
            elif 8 <= hazard_score <= 14:
                hazard_class = "Hazard Class B"
            elif 15 <= hazard_score <= 16:
                hazard_class = "Hazard Class C"
            elif 17 <= hazard_score <= 20:
                hazard_class = "Hazard Class D"
            else:
                hazard_class = "Unable to Decide"

        # Assemble API logs
        api_logs = {
            "sds": sds_res,
            "handling": handling_res,
            "transportation": transport_res,
            "disposal": disposal_res
        }

        # Registry entry (digital record)
        registry_entry = {
            "product_id": product_id,
            "hazard_score": hazard_score,
            "hazard_class": hazard_class
        }

        # Audit trail documentation
        audit_trail = (
            f"Product ID validated. SDS score={sds_score}, "
            f"Handling score={handling_score}, Transportation score={transport_score}, "
            f"Disposal score={disposal_score}. Computed hazard_score={hazard_score}. "
            f"Determined {hazard_class}."
        )

        # XML formatted final output
        xml_output = (
            "<result>"
            f"<hazard_score>{hazard_score}</hazard_score>"
            f"<hazard_class>{hazard_class}</hazard_class>"
            "</result>"
        )

        # Final combined return
        return {
            "hazard_score": hazard_score,
            "hazard_class": hazard_class,
            "registry_entry": registry_entry,
            "api_logs": api_logs,
            "audit_trail": audit_trail,
            "xml_output": xml_output,
            "status": "success"
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
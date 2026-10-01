from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 0: Validate product_id format (P_XXXXX)
        product_id = input_data["product_id"]
        valid_id = False
        if isinstance(product_id, str) and product_id.startswith("P_"):
            suffix = product_id.split("_", 1)[1] if "_" in product_id else ""
            if len(suffix) == 5 and suffix.isalnum():
                valid_id = True
        if not valid_id:
            # Early termination due to invalid product ID
            return {
                "hazard_score": 0,
                "hazard_class": "Unable to Decide",
                "registry_record": {"product_id": product_id, "hazard_score": 0, "hazard_class": "Unable to Decide"},
                "api_logs": [],
                "audit_trail": {"product_id_validation": "failed"},
                "xml_output": "<hazard_score>0</hazard_score><hazard_class>Unable to Decide</hazard_class>"
            }

        # Step 1: Calculate SDS label score
        sds_result = manager.calculate_sds_label_score(
            product_id=product_id,
            sds_label_text=input_data["sds_label_text"]
        )
        sds_score = sds_result["sds_label_score"]
        # Validate SDS score (allow 0, reject <0 or >5)
        if sds_score < 0 or sds_score > 5:
            raise ValueError(f"SDS label score {sds_score} out of valid range 0-5")

        # Step 2: Calculate handling and storage score
        handling_result = manager.calculate_handling_score(
            product_id=product_id,
            handling_and_storage_guidelines=input_data["handling_and_storage_guidelines"],
            assessmentFormId=input_data.get("assessmentFormId")
        )
        handling_score = handling_result["handling_score"]
        if handling_score < 0 or handling_score > 5:
            raise ValueError(f"Handling score {handling_score} out of valid range 0-5")

        # Step 3: Calculate transportation score
        transportation_result = manager.calculate_transportation_score(
            product_id=product_id,
            transportation_requirements=input_data["transportation_requirements"]
        )
        transportation_score = transportation_result["transportation_score"]
        if transportation_score < 0 or transportation_score > 5:
            raise ValueError(f"Transportation score {transportation_score} out of valid range 0-5")

        # Step 4: Calculate disposal score
        disposal_result = manager.calculate_disposal_score(
            product_id=product_id,
            disposal_guidelines=input_data["disposal_guidelines"]
        )
        disposal_score = disposal_result["disposal_score"]
        if disposal_score < 0 or disposal_score > 5:
            raise ValueError(f"Disposal score {disposal_score} out of valid range 0-5")

        # Collect API logs for audit
        api_logs = [sds_result, handling_result, transportation_result, disposal_result]

        # Step 5: Hazard Score Computation with imputation rules
        scores = {
            "safety": sds_score,
            "handling": handling_score,
            "transportation": transportation_score,
            "disposal": disposal_score
        }
        missing_keys = [k for k, v in scores.items() if v == 0]

        if len(missing_keys) >= 2:
            hazard_score = 0
            hazard_class = "Unable to Decide"
        else:
            if len(missing_keys) == 1:
                # Impute the single missing component with max of the others
                max_other = max(v for v in scores.values() if v != 0)
                scores[missing_keys[0]] = max_other
            hazard_score = sum(scores.values())
            # Validate total score range (4-20)
            if hazard_score < 4 or hazard_score > 20:
                raise ValueError(f"Total hazard_score {hazard_score} out of acceptable range 4-20")
            # Step 6: Hazard Class Determination
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

        # Step 7: Build registry record
        registry_record = {
            "product_id": product_id,
            "hazard_score": hazard_score,
            "hazard_class": hazard_class
        }

        # Step 8: Assemble audit trail
        audit_trail = {
            "product_id_validation": "passed",
            "scores": {
                "sds_score": sds_score,
                "handling_score": handling_score,
                "transportation_score": transportation_score,
                "disposal_score": disposal_score,
                "imputed_missing": missing_keys
            }
        }

        # Step 9: Generate XML output
        xml_output = f"<hazard_score>{hazard_score}</hazard_score><hazard_class>{hazard_class}</hazard_class>"

        # Combine all SOP output fields into the final return dict
        return {
            "hazard_score": hazard_score,
            "hazard_class": hazard_class,
            "registry_record": registry_record,
            "api_logs": api_logs,
            "audit_trail": audit_trail,
            "xml_output": xml_output
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
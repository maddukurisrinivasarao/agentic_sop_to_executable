from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Validate product ID format
        product_id = input_data["product_id"]
        valid_id = False
        if isinstance(product_id, str) and product_id.startswith("P_"):
            suffix = product_id[2:]
            if len(suffix) == 5 and suffix.isalnum():
                valid_id = True

        # Initialize containers for logs and audit trail
        api_logs = {}
        audit_trail = []

        if not valid_id:
            # Invalid ID – set defaults per SOP
            hazard_score = 0
            hazard_class = "Unable to Decide"
            audit_trail.append("Product ID validation failed")
        else:
            audit_trail.append("Product ID validation passed")

            # Step 2: Calculate SDS label score
            sds_result = manager.calculate_sds_label_score(
                product_id=product_id,
                sds_label_text=input_data["sds_label_text"]
            )
            api_logs["sds_result"] = sds_result
            sds_score = sds_result["sds_label_score"]
            audit_trail.append("SDS label score calculated")

            # Step 3: Calculate handling and storage score
            handling_params = {
                "product_id": product_id,
                "handling_and_storage_guidelines": input_data["handling_and_storage_guidelines"]
            }
            if "assessment_form_id" in input_data and input_data["assessment_form_id"]:
                handling_params["assessmentFormId"] = input_data["assessment_form_id"]
            handling_result = manager.calculate_handling_score(**handling_params)
            api_logs["handling_result"] = handling_result
            handling_score = handling_result["handling_score"]
            audit_trail.append("Handling and storage score calculated")

            # Step 4: Calculate transportation score
            transportation_result = manager.calculate_transportation_score(
                product_id=product_id,
                transportation_requirements=input_data["transportation_requirements"]
            )
            api_logs["transportation_result"] = transportation_result
            transportation_score = transportation_result["transportation_score"]
            audit_trail.append("Transportation score calculated")

            # Step 5: Calculate disposal score
            disposal_result = manager.calculate_disposal_score(
                product_id=product_id,
                disposal_guidelines=input_data["disposal_guidelines"]
            )
            api_logs["disposal_result"] = disposal_result
            disposal_score = disposal_result["disposal_score"]
            audit_trail.append("Disposal score calculated")

            # Step 6: Validate individual scores are within 1-5
            for name, val in [("SDS", sds_score), ("Handling", handling_score),
                              ("Transportation", transportation_score), ("Disposal", disposal_score)]:
                if not (1 <= val <= 5):
                    raise ValueError(f"{name} score {val} out of valid range 1-5")

            # Step 7: Impute missing or zero scores
            scores = [sds_score, handling_score, transportation_score, disposal_score]
            missing_count = sum(1 for sc in scores if sc == 0)
            if missing_count > 2:
                hazard_score = 0
                hazard_class = "Unable to Decide"
                audit_trail.append("More than two component scores missing – unable to decide")
            else:
                # Impute zeros with max of non-zero scores
                non_zero_scores = [sc for sc in scores if sc != 0]
                max_score = max(non_zero_scores) if non_zero_scores else 0
                imputed_scores = [sc if sc != 0 else max_score for sc in scores]
                sds_score, handling_score, transportation_score, disposal_score = imputed_scores
                hazard_score = sum(imputed_scores)
                audit_trail.append("Missing scores imputed where necessary")

                # Step 8: Validate total hazard score range
                if not (4 <= hazard_score <= 20):
                    raise ValueError(f"Hazard score {hazard_score} out of acceptable range 4-20")

                # Step 9: Determine hazard class based on cumulative score
                if hazard_score <= 8:
                    hazard_class = "Hazard Class A"
                elif hazard_score <= 12:
                    hazard_class = "Hazard Class B"
                elif hazard_score <= 16:
                    hazard_class = "Hazard Class C"
                else:
                    hazard_class = "Hazard Class D"
                audit_trail.append("Hazard class determined")

        # Step 10: Create registry record
        registry_record = {
            "product_id": product_id,
            "hazard_score": hazard_score,
            "hazard_class": hazard_class
        }

        # Step 11: Build XML output
        xml_output = f"<hazard_score>{hazard_score}</hazard_score><hazard_class>{hazard_class}</hazard_class>"

        # Combine all required output fields
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
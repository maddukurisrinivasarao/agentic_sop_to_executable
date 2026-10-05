from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # --------------------------------------------------------------------
        # Step 0: Validate product ID format (P_XXXXX where X are alphanumeric)
        # --------------------------------------------------------------------
        product_id_raw = input_data["product_id"]
        pid_valid = False
        if isinstance(product_id_raw, str):
            if product_id_raw.startswith("P_"):
                suffix = product_id_raw[2:]
                if len(suffix) == 5 and suffix.isalnum():
                    pid_valid = True
        if not pid_valid:
            # Early termination: invalid product ID
            return {
                "hazard_score": 0,
                "hazard_class": "Unable to Decide",
                "registry_record": {},
                "api_logs": [],
                "audit_trail": ["Product ID validation failed"],
                "xml_output": "<hazard_score>0</hazard_score><hazard_class>Unable to Decide</hazard_class>"
            }

        # -------------------------------------------------
        # Step 1: Calculate SDS label severity score
        # -------------------------------------------------
        sds_res = manager.calculate_sds_label_score(
            product_id=product_id_raw,
            sds_label_text=input_data["sds_label_text"]
        )
        sds_score = sds_res.get("sds_label_score", 0)
        # Validation: score must be between 0 and 5 inclusive; negative or >5 is error
        if not isinstance(sds_score, int):
            raise ValueError("SDS score not integer")
        if sds_score < 0 or sds_score > 5:
            raise ValueError("SDS score out of valid range")

        # -------------------------------------------------
        # Step 2: Calculate handling and storage severity score
        # -------------------------------------------------
        handling_res = manager.calculate_handling_score(
            product_id=product_id_raw,
            handling_and_storage_guidelines=input_data["handling_and_storage_guidelines"]
        )
        handling_score = handling_res.get("handling_score", 0)
        if not isinstance(handling_score, int):
            raise ValueError("Handling score not integer")
        if handling_score < 0 or handling_score > 5:
            raise ValueError("Handling score out of valid range")

        # -------------------------------------------------
        # Step 3: Calculate transportation severity score
        # -------------------------------------------------
        transportation_res = manager.calculate_transportation_score(
            product_id=product_id_raw,
            transportation_requirements=input_data["transportation_requirements"]
        )
        transportation_score = transportation_res.get("transportation_score", 0)
        if not isinstance(transportation_score, int):
            raise ValueError("Transportation score not integer")
        if transportation_score < 0 or transportation_score > 5:
            raise ValueError("Transportation score out of valid range")

        # -------------------------------------------------
        # Step 4: Calculate disposal severity score
        # -------------------------------------------------
        disposal_res = manager.calculate_disposal_score(
            product_id=product_id_raw,
            disposal_guidelines=input_data["disposal_guidelines"]
        )
        disposal_score = disposal_res.get("disposal_score", 0)
        if not isinstance(disposal_score, int):
            raise ValueError("Disposal score not integer")
        if disposal_score < 0 or disposal_score > 5:
            raise ValueError("Disposal score out of valid range")

        # -------------------------------------------------
        # Step 5: Hazard Score Computation with imputation logic
        # -------------------------------------------------
        scores = {
            "sds": sds_score,
            "handling": handling_score,
            "transportation": transportation_score,
            "disposal": disposal_score
        }
        missing_count = sum(1 for v in scores.values() if v == 0)

        if missing_count >= 2:
            hazard_score = 0
            hazard_class = "Unable to Decide"
        else:
            # Impute if exactly one component is missing
            if missing_count == 1:
                # Find max of non‑zero scores
                max_score = max(v for v in scores.values() if v != 0)
                # Replace the zero with max_score
                for k, v in scores.items():
                    if v == 0:
                        scores[k] = max_score
                        break
            # Compute cumulative hazard score
            hazard_score = sum(scores.values())
            # Validate total range (4‑20)
            if hazard_score < 4 or hazard_score > 20:
                raise ValueError("Cumulative hazard score out of acceptable range (4‑20)")

            # -------------------------------------------------
            # Step 6: Hazard Class Determination
            # -------------------------------------------------
            if 4 <= hazard_score <= 7:
                hazard_class = "Hazard Class A"
            elif 8 <= hazard_score <= 14:
                hazard_class = "Hazard Class B"
            elif 15 <= hazard_score <= 16:
                hazard_class = "Hazard Class C"
            elif 17 <= hazard_score <= 20:
                hazard_class = "Hazard Class D"
            else:
                # This should not happen due to earlier validation
                hazard_class = "Unable to Decide"

        # -------------------------------------------------
        # Assemble output components
        # -------------------------------------------------
        registry_record = {
            "product_id": product_id_raw,
            "hazard_score": hazard_score,
            "hazard_class": hazard_class
        }

        api_logs = [
            {"step": "SDS", "response": sds_res},
            {"step": "Handling", "response": handling_res},
            {"step": "Transportation", "response": transportation_res},
            {"step": "Disposal", "response": disposal_res}
        ]

        audit_trail = [
            "Product ID validated",
            "SDS score calculated",
            "Handling score calculated",
            "Transportation score calculated",
            "Disposal score calculated",
            "Hazard score computed",
            "Hazard class determined"
        ]

        xml_output = (
            f"<hazard_score>{hazard_score}</hazard_score>"
            f"<hazard_class>{hazard_class}</hazard_class>"
        )

        # -------------------------------------------------
        # Final return mapping SOP output fields to values
        # -------------------------------------------------
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
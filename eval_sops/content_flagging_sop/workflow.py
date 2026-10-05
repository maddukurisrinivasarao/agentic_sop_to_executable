from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Helper functions for safe type conversion
        def to_int(value):
            if value is None or value == "" or (isinstance(value, float) and value != value):
                return None
            return int(float(value))

        def to_float(value):
            if value is None or value == "" or (isinstance(value, float) and value != value):
                return None
            return float(value)

        # -----------------------------------------------------------------
        # Step 1: Calculate Bot Probability Index and Device Consistency Score
        # -----------------------------------------------------------------
        bot_result = manager.calculateBotProbabilityIndex(
            userid=input_data["userid"],
            is_possible_bot=to_float(input_data["is_possible_bot"]),
            Captcha_tries=to_int(input_data["Captcha_tries"]),
            device_type=input_data["device_type"],
            os=input_data["os"],
            browser=input_data["browser"]
        )
        # Expected returns: {'bot_probability_index': number, 'device_consistency_score': number}
        bot_probability_index = bot_result["bot_probability_index"]
        device_consistency_score = bot_result["device_consistency_score"]

        # --------------------------------------------------------------
        # Step 2: Calculate User Trust Score (UTC)
        # --------------------------------------------------------------
        # Optional geographic coordinates are handled safely
        latitude = to_float(input_data.get("Latitude"))
        longitude = to_float(input_data.get("Longitude"))

        user_trust_score = manager.calculate_user_trust_score(
            userid=input_data["userid"],
            NumberofPreviousPosts=to_int(input_data["NumberofPreviousPosts"]),
            CountofFlaggedPosts=to_int(input_data["CountofFlaggedPosts"]),
            Latitude=latitude,
            Longitude=longitude,
            bot_probability_index=bot_probability_index,
            device_consistency_score=device_consistency_score
        )
        # Expected return: scalar integer (0‑100)

        # --------------------------------------------------------------
        # Step 3: Calculate Content Severity Index (CSI)
        # --------------------------------------------------------------
        # Prepare optional secondary violation parameters
        secondary_type = input_data.get("SecondaryViolationType")
        secondary_conf = input_data.get("SecondaryViolation_Confidence")
        # Convert confidence scores to float if present
        primary_confidence = to_float(input_data["PrimaryViolation_Confidence"])
        secondary_confidence = to_float(secondary_conf) if secondary_conf not in (None, "") else None

        content_severity_index = manager.calculateContentSeverityIndex(
            content_id=input_data["content_id"],
            PrimaryViolationType=input_data["PrimaryViolationType"],
            PrimaryViolation_Confidence=primary_confidence,
            SecondaryViolationType=secondary_type,
            SecondaryViolation_Confidence=secondary_confidence
        )
        # Expected return: scalar integer (0‑100)

        # --------------------------------------------------------------
        # Step 4: Determine Final Decision for Content
        # --------------------------------------------------------------
        final_decision = manager.determineFinalDecision(
            content_id=input_data["content_id"],
            user_trust_score=user_trust_score,
            content_severity_index=content_severity_index,
            bot_probability_index=bot_probability_index,
            NumberofPreviousPosts=to_int(input_data["NumberofPreviousPosts"]),
            CountofFlaggedPosts=to_int(input_data["CountofFlaggedPosts"])
        )
        # Expected return: string disposition ("removed", "warning", "user_banned", "allowed")

        # --------------------------------------------------------------
        # Assemble final output as required by SOP
        # --------------------------------------------------------------
        return {
            "user_trust_score": user_trust_score,
            "content_severity_index": content_severity_index,
            "final_decision": final_decision
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
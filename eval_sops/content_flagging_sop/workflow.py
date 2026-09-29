from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Calculate Bot Probability Index and Device Consistency Score
        bot_result = manager.calculateBotProbabilityIndex(
            userid=input_data["userid"],
            is_possible_bot=float(input_data["is_possible_bot"]),
            Captcha_tries=int(input_data["Captcha_tries"]),
            device_type=input_data["device_type"],
            os=input_data["os"],
            browser=input_data["browser"]
        )
        bot_probability_index = bot_result["bot_probability_index"]
        device_consistency_score = bot_result["device_consistency_score"]

        # Step 2: Calculate User Trust Score (UTC)
        user_trust_score = manager.calculate_user_trust_score(
            userid=input_data["userid"],
            NumberofPreviousPosts=int(input_data["NumberofPreviousPosts"]),
            CountofFlaggedPosts=int(input_data["CountofFlaggedPosts"]),
            Latitude=float(input_data["Latitude"]),
            Longitude=float(input_data["Longitude"]),
            bot_probability_index=bot_probability_index,
            device_consistency_score=device_consistency_score
        )

        # Step 3: Calculate Content Severity Index (CSI)
        content_severity_index = manager.calculateContentSeverityIndex(
            content_id=input_data["content_id"],
            PrimaryViolationType=input_data["PrimaryViolationType"],
            SecondaryViolationType=input_data.get("SecondaryViolationType"),
            PrimaryViolation_Confidence=float(input_data["PrimaryViolation_Confidence"]),
            SecondaryViolation_Confidence=float(input_data["SecondaryViolation_Confidence"]) if input_data.get("SecondaryViolation_Confidence") is not None else None
        )

        # Step 4: Determine Final Decision and Disposition
        final_decision = manager.determineFinalDecision(
            content_id=input_data["content_id"],
            user_trust_score=int(user_trust_score),
            content_severity_index=int(content_severity_index),
            bot_probability_index=bot_probability_index,
            NumberofPreviousPosts=int(input_data["NumberofPreviousPosts"]),
            CountofFlaggedPosts=int(input_data["CountofFlaggedPosts"])
        )

        # Combine results as required by the SOP output specification
        return {
            "user_trust_score": int(user_trust_score),
            "content_severity_index": int(content_severity_index),
            "final_decision": final_decision
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
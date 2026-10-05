from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Validate video technical metadata (VVP) and compute format_validated
        validation = manager.validateVideo(
            video_id=input_data["video_id"],
            video_path=input_data["video_path"],
        )
        # Normalize codec string
        raw_format = validation.get("format", "")
        fmt = "" if raw_format is None else str(raw_format).lower().replace(" ", "").replace(".", "").replace("-", "")
        codec_supported = fmt in {"mp4", "h264", "hevc"}
        # Parse resolution and check size
        res_str = validation.get("resolution", "")
        res_ok = False
        if isinstance(res_str, str):
            parts = res_str.lower().split("x")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                width = int(parts[0])
                height = int(parts[1])
                if width * height >= 1280 * 720:
                    res_ok = True
        format_validated = codec_supported and res_ok

        # Early termination if technical validation fails
        if not format_validated:
            return {
                "escalated": False,
                "moderation_actions": [],
                "content_warning_applied": False,
                "final_decision": "Remove",
            }

        # Step 2: Retrieve uploader history (optional, not used later)
        uploader_history_resp = manager.checkUserHistory(
            uploader_id=validation.get("uploader_id")
        )

        # Step 3: Assign initial reviewer based on language and region
        reviewer_assign = manager.assignReviewer(
            video_id=validation.get("video_id"),
            video_language=validation.get("video_language"),
            region=validation.get("region")
        )
        initial_reviewer_id = reviewer_assign.get("initial_reviewer_id")

        # Step 4: Fetch review results
        review = manager.getReview(
            video_id=validation.get("video_id"),
            initial_reviewer_id=initial_reviewer_id
        )
        detected_categories = review.get("detected_categories", [])
        confidence_scores = review.get("confidence_scores", [])

        # Step 5: Determine escalation (ETM) and possibly submit moderation
        escalated = False
        moderation_actions = []
        if detected_categories and confidence_scores:
            max_conf = max(confidence_scores) if confidence_scores else 0
            if max_conf > 0.70:
                escalated = True
                # Submit content moderation record
                submit_resp = manager.submitContentModeration(
                    video_id=validation.get("video_id"),
                    initial_reviewer_id=initial_reviewer_id
                )
                moderator_id = submit_resp.get("moderator_id")
                # Implement moderation actions
                manager.implementModeration(
                    video_id=validation.get("video_id"),
                    moderator_id=moderator_id
                )
                # Apply Moderation Action Matrix (MAM) based on categories
                cat_set = set(detected_categories)
                if {"Hate Speech", "Illegal activities", "Misinformation", "Nudity"} & cat_set:
                    moderation_actions = ["Remove", "Strike Issued"]
                elif detected_categories == ["Violence"]:
                    moderation_actions = ["Age Restrict", "Warning"]
                elif detected_categories == ["Bullying"]:
                    moderation_actions = ["Remove", "Warning"]
                else:
                    # No explicit rule; keep empty list
                    moderation_actions = []
        # If not escalated, moderation_actions stays empty

        # Step 6: Retrieve content warning flag
        warning_resp = manager.generateContentWarnings(
            video_id=validation.get("video_id")
        )
        content_warning_applied = warning_resp.get("content_warning_applied", False)

        # Step 7: Retrieve pre-recorded age rating
        age_resp = manager.assessAgeRating(
            video_id=validation.get("video_id")
        )
        age_rating = age_resp.get("age_rating")

        # Step 8: Determine final decision per SOP hierarchy
        if not format_validated:
            final_decision = "Remove"
        elif escalated:
            if detected_categories == ["Violence"]:
                final_decision = "Age Restrict"
            else:
                final_decision = "Remove"
        else:
            if age_rating == "13+":
                final_decision = "Age Restrict"
            else:
                final_decision = "Allow"

        # Combine results into output
        return {
            "escalated": escalated,
            "moderation_actions": moderation_actions,
            "content_warning_applied": content_warning_applied,
            "final_decision": final_decision,
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
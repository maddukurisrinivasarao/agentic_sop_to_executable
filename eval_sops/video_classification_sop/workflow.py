from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Validate video format and extract technical metadata
        video_validation = manager.validateVideo(
            video_id=input_data["video_id"],
            video_path=input_data["video_path"]
        )

        # Step 2: Validate metadata tags
        metadata_validation = manager.validateMetadataTags(
            video_id=input_data["video_id"],
            metadata_tags=input_data["metadata_tags"]
        )

        # Step 3: Check uploader's historical behavior
        user_history = manager.checkUserHistory(
            uploader_id=input_data["uploader_id"]
        )

        # Step 4: Assign an initial reviewer based on language and region
        reviewer_assignment = manager.assignReviewer(
            video_id=input_data["video_id"],
            video_language=input_data["video_language"],
            region=input_data["region"]
        )
        initial_reviewer_id = reviewer_assignment["initial_reviewer_id"]

        # Step 5: Fetch initial review results
        review_result = manager.getReview(
            video_id=input_data["video_id"],
            initial_reviewer_id=initial_reviewer_id
        )
        detected_categories = review_result.get("detected_categories", [])
        confidence_scores = review_result.get("confidence_scores", [])

        # Determine escalation (ETM) – triggered when there is at least one detected category
        escalated = bool(detected_categories)

        # Conditional Step 6: Record moderation findings if escalation is required
        if escalated:
            moderation_record = manager.submitContentModeration(
                video_id=input_data["video_id"],
                initial_reviewer_id=initial_reviewer_id
            )
            moderator_id = moderation_record["moderator_id"]
            # Step 7: Implement moderation decision
            moderation_implementation = manager.implementModeration(
                video_id=input_data["video_id"],
                moderator_id=moderator_id
            )
        # No escalation – skip submitContentModeration and implementModeration

        # Step 8: Assess appropriate age rating
        manager.assessAgeRating(video_id=input_data["video_id"])

        # Step 9: Generate content warning flag
        manager.generateContentWarnings(video_id=input_data["video_id"])

        # Step 10: Verify regional compliance
        manager.checkRegionalCompliance(
            video_id=input_data["video_id"],
            region=input_data["region"]
        )

        # Step 11: Detect explicit visual content
        manager.detectExplicitContent(video_id=input_data["video_id"])

        # Step 12: Detect hate speech in audio/video
        manager.detectHateSpeech(video_id=input_data["video_id"])

        # Step 13: Analyze audio track for violations
        manager.analyzeAudioContent(video_id=input_data["video_id"])

        # Step 14: Check video thumbnail compliance
        manager.checkVideoThumbnail(video_id=input_data["video_id"])

        # Step 15: Scan for copyright infringements
        manager.scanForCopyright(video_id=input_data["video_id"])

        # Step 16: Detect synthetic (AI‑generated) content
        manager.detectSyntheticContent(video_id=input_data["video_id"])

        # Step 17: Assess overall video quality
        manager.assessVideoQuality(video_id=input_data["video_id"])

        # Step 18: Validate subtitles for compliance
        manager.validateSubtitles(video_id=input_data["video_id"])

        # Step 19: Review comment section for policy violations
        manager.reviewCommentSection(video_id=input_data["video_id"])

        # Step 20: Detect spam content or behavior
        manager.detectSpam(video_id=input_data["video_id"])

        # Step 21: Assess thumbnail compliance with regional rules
        manager.assessThumbnailCompliance(video_id=input_data["video_id"])

        # Step 22: Validate video description text
        manager.validateDescription(video_id=input_data["video_id"])

        # Step 23: Check streaming quality metrics
        manager.checkStreamingQuality(video_id=input_data["video_id"])

        # Step 24: Detect inappropriate advertisements
        manager.detectInappropriateAds(video_id=input_data["video_id"])

        # Step 25 (original Step 8): Generate content warning flag (simple rule: warning if escalated)
        content_warning_applied = escalated

        # Step 26 (original Step 9): Determine final decision
        format_validated = str(input_data["format_validated"]).strip().lower() == "true"
        if not format_validated:
            final_decision = "Remove"
        elif escalated:
            final_decision = "Remove"
        else:
            final_decision = "Allow"

        # Step 27 (original Step 10): Assemble moderation actions list (empty if no escalation)
        moderation_actions = []  # No explicit actions derived from tools in this simplified flow

        return {
            "escalated": escalated,
            "moderation_actions": moderation_actions,
            "content_warning_applied": content_warning_applied,
            "final_decision": final_decision
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
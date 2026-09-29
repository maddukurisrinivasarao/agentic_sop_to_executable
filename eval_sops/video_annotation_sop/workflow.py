from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Validate video format and metadata against SOP specifications
        video_format_res = manager.validateVideoFormat(
            video_id=input_data["video_id"]
        )

        # Step 2: Validate environmental weather conditions (must be acceptable daylight)
        weather_res = manager.validateWeatherConditions(
            video_id=input_data["video_id"],
            weather=input_data["weather"]
        )

        # Step 3: Validate scene context (must be urban)
        scene_res = manager.validateSceneContext(
            video_id=input_data["video_id"],
            scene_type=input_data["scene_type"]
        )

        # Step 4: Validate number of color channels in the video (minimum 3)
        channel_res = manager.validateChannelCount(
            video_id=input_data["video_id"],
            channel_count=int(input_data["channel_count"])
        )

        # Step 5: Validate LiDAR data completeness and synchronization
        lidar_res = manager.validateLidarData(
            video_id=input_data["video_id"],
            video_path=input_data["video_path"]
        )

        # Step 6: Synchronize LiDAR timestamps with video frames
        sync_res = manager.synchronizeLidarTimestamp(
            video_id=input_data["video_id"],
            time_offset=float(input_data["time_offset"])
        )

        # Step 7: Calibrate camera sensors for accurate spatial alignment
        calibrate_res = manager.calibrateCameraSensors(
            video_id=input_data["video_id"],
            camera_position=input_data["camera_position"]
        )

        # Step 8: Validate availability of camera intrinsic parameters
        intrinsics_res = manager.validateCameraIntrinsics(
            video_id=input_data["video_id"],
            camera_intrinsics_available=str(input_data["camera_intrinsics_available"]).lower() == "true"
        )

        # Step 9: Execute object detection on validated video
        detection_res = manager.performObjectDetection(
            video_id=input_data["video_id"],
            video_path=input_data["video_path"]
        )

        # Step 10: Validate object detection output format (e.g., COCO)
        output_format_res = manager.validateOutputFormat(
            video_id=input_data["video_id"],
            output_format_object_detection=input_data["output_format_object_detection"]
        )

        # Step 11: Optimize tracking configuration based on detection settings
        tracking_opt_res = manager.optimizeTrackingSettings(
            video_id=input_data["video_id"],
            tracking_enabled=str(input_data["tracking_enabled"]).lower() == "true"
        )

        # Step 12: Perform segmentation on detected objects
        segmentation_res = manager.executeSegmentation(
            video_id=input_data["video_id"],
            predicted_object=input_data["predicted_object"],
            object_detection_output_path=input_data["object_detection_output_path"],
            output_format_object_detection=input_data["output_format_object_detection"]
        )

        # Step 13: Run automated quality control checks
        automated_qc_res = manager.runAutomatedQC(
            video_id=input_data["video_id"],
            video_path=input_data["video_path"],
            predicted_object=input_data["predicted_object"],
            predicted_iou=float(input_data["predicted_iou"]),
            segmentation_output_path=input_data["segmentation_output_path"],
            object_detection_output_path=input_data["object_detection_output_path"]
        )

        # Step 14: Conduct human‑in‑the‑loop validation
        human_val_res = manager.performHumanValidation(
            video_id=input_data["video_id"],
            predicted_object=input_data["predicted_object"],
            predicted_iou=float(input_data["predicted_iou"]),
            segmentation_output_path=input_data["segmentation_output_path"],
            object_detection_output_path=input_data["object_detection_output_path"]
        )

        # Step 15: Validate spatial accuracy against ground truth
        spatial_acc_res = manager.checkSpatialAccuracy(
            video_id=input_data["video_id"],
            spatial_accuracy_score=float(input_data["spatial_accuracy_score"])
        )

        # Step 16: Validate temporal consistency of the processed video
        temporal_cons_res = manager.validateTemporalConsistency(
            video_id=input_data["video_id"],
            temporal_consistency_score=float(input_data["temporal_consistency_score"])
        )

        # Step 17: Validate inter‑annotator agreement score
        annotator_score_res = manager.validateAnnotatorScores(
            video_id=input_data["video_id"],
            inter_annotator_score=float(input_data["inter_annotator_score"])
        )

        # ------------------------------------------------------------
        # Determine final status based on all validation results and thresholds
        # ------------------------------------------------------------
        # Helper to extract boolean from tool responses (they all return a dict with 'is_valid')
        def _ok(res):
            return res.get("is_valid", False)

        thresholds_met = (
            _ok(video_format_res) and
            _ok(weather_res) and
            _ok(scene_res) and
            _ok(channel_res) and
            _ok(lidar_res) and
            _ok(sync_res) and
            _ok(calibrate_res) and
            _ok(intrinsics_res) and
            _ok(detection_res) and
            _ok(output_format_res) and
            _ok(tracking_opt_res) and
            _ok(segmentation_res) and
            _ok(automated_qc_res) and
            _ok(human_val_res) and
            _ok(spatial_acc_res) and
            _ok(temporal_cons_res) and
            _ok(annotator_score_res) and
            float(input_data["spatial_accuracy_score"]) >= 0.85 and
            float(input_data["temporal_consistency_score"]) >= 0.80 and
            float(input_data["inter_annotator_score"]) >= 0.75
        )

        if thresholds_met:
            final_status = True
            reason = None
        else:
            final_status = False
            # Build a concise reason based on which check failed first
            if not _ok(video_format_res):
                reason = "Video format validation failed"
            elif not _ok(weather_res):
                reason = "Weather condition validation failed"
            elif not _ok(scene_res):
                reason = "Scene context validation failed"
            elif not _ok(channel_res):
                reason = "Channel count validation failed"
            elif not _ok(lidar_res):
                reason = "LiDAR data validation failed"
            elif not _ok(sync_res):
                reason = "LiDAR timestamp synchronization failed"
            elif not _ok(calibrate_res):
                reason = "Camera calibration failed"
            elif not _ok(intrinsics_res):
                reason = "Camera intrinsics unavailable"
            elif not _ok(detection_res):
                reason = "Object detection failed"
            elif not _ok(output_format_res):
                reason = "Object detection output format invalid"
            elif not _ok(tracking_opt_res):
                reason = "Tracking configuration invalid"
            elif not _ok(segmentation_res):
                reason = "Segmentation processing failed"
            elif not _ok(automated_qc_res):
                reason = "Automated QC failed"
            elif not _ok(human_val_res):
                reason = "Human validation failed"
            elif not _ok(spatial_acc_res) or float(input_data["spatial_accuracy_score"]) < 0.85:
                reason = "Spatial accuracy below threshold"
            elif not _ok(temporal_cons_res) or float(input_data["temporal_consistency_score"]) < 0.80:
                reason = "Temporal consistency below threshold"
            elif not _ok(annotator_score_res) or float(input_data["inter_annotator_score"]) < 0.75:
                reason = "Inter‑annotator agreement below threshold"
            else:
                reason = "Unknown validation failure"

        # ------------------------------------------------------------
        # Assemble final output dictionary matching SOP output fields
        # ------------------------------------------------------------
        return {
            "final_status": final_status,
            "coco_json_path": input_data["object_detection_output_path"] if final_status else None,
            "segmentation_mask_path": input_data["segmentation_output_path"] if final_status else None,
            "inter_annotator_score": float(input_data["inter_annotator_score"]) if final_status else None,
            "reason": reason
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
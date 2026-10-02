from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Helper conversions
        def to_bool(val):
            return str(val).strip().lower() == "true"

        def to_int(val):
            return int(float(val))

        def to_float(val):
            return float(val)

        # Step 1: Validate video format and metadata
        step1 = manager.validateVideoFormat(
            video_id=input_data["video_id"]
        )
        if not step1["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Video format validation failed"
            }

        # Step 2: Validate LiDAR data integrity and synchronization
        step2 = manager.validateLidarData(
            video_id=input_data["video_id"],
            video_path=input_data["video_path"]
        )
        if not step2["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "LiDAR data validation failed"
            }

        # Step 3: Calibrate camera sensors
        step3 = manager.calibrateCameraSensors(
            video_id=input_data["video_id"],
            camera_position=input_data["camera_position"]
        )
        if not step3["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Camera sensor calibration failed"
            }

        # Step 4: Synchronize LiDAR timestamps with video frames
        step4 = manager.synchronizeLidarTimestamp(
            video_id=input_data["video_id"],
            time_offset=to_float(input_data["time_offset"])
        )
        if not step4["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "LiDAR timestamp synchronization failed"
            }

        # Step 5: Validate camera intrinsic parameters
        step5 = manager.validateCameraIntrinsics(
            video_id=input_data["video_id"],
            camera_intrinsics_available=to_bool(input_data["camera_intrinsics_available"])
        )
        if not step5["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Camera intrinsics validation failed"
            }

        # Step 6: Validate recorded scene context
        step6 = manager.validateSceneContext(
            video_id=input_data["video_id"],
            scene_type=input_data["scene_type"]
        )
        if not step6["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Scene context validation failed"
            }

        # Step 7: Validate weather conditions
        step7 = manager.validateWeatherConditions(
            video_id=input_data["video_id"],
            weather=input_data["weather"]
        )
        if not step7["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Weather condition validation failed"
            }

        # Step 8: Adjust video bit depth if necessary
        step8 = manager.adjustBitDepth(
            video_id=input_data["video_id"],
            bit_depth=to_int(input_data["bit_depth"])
        )
        if not step8["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Bit depth adjustment failed"
            }

        # Step 9: Validate number of color channels
        step9 = manager.validateChannelCount(
            video_id=input_data["video_id"],
            channel_count=to_int(input_data["channel_count"])
        )
        if not step9["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Channel count validation failed"
            }

        # Step 10: Optimize video frame rate
        step10 = manager.optimizeFrameRate(
            video_id=input_data["video_id"],
            frame_rate=to_float(input_data["frame_rate"])
        )
        if not step10["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Frame rate optimization failed"
            }

        # Step 11: Process high‑resolution video
        step11 = manager.processHighResolution(
            video_id=input_data["video_id"],
            resolution_width=to_int(input_data["resolution_width"]),
            resolution_height=to_int(input_data["resolution_height"])
        )
        if not step11["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "High‑resolution processing failed"
            }

        # Step 12: Perform object detection
        step12 = manager.performObjectDetection(
            video_id=input_data["video_id"],
            video_path=input_data["video_path"]
        )
        if not step12["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Object detection failed"
            }

        # Step 13: Validate object‑detection output format
        step13 = manager.validateOutputFormat(
            video_id=input_data["video_id"],
            output_format_object_detection=input_data["output_format_object_detection"]
        )
        if not step13["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Object detection output format validation failed"
            }

        # Step 14: Optimize tracking settings
        step14 = manager.optimizeTrackingSettings(
            video_id=input_data["video_id"],
            tracking_enabled=to_bool(input_data["tracking_enabled"])
        )
        if not step14["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Tracking settings optimization failed"
            }

        # Step 15: Execute segmentation
        step15 = manager.executeSegmentation(
            video_id=input_data["video_id"],
            predicted_object=input_data["predicted_object"],
            object_detection_output_path=input_data["object_detection_output_path"],
            output_format_object_detection=input_data["output_format_object_detection"]
        )
        if not step15["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Segmentation execution failed"
            }

        # Step 16: Run automated quality control checks
        step16 = manager.runAutomatedQC(
            video_id=input_data["video_id"],
            video_path=input_data["video_path"],
            predicted_object=input_data["predicted_object"],
            predicted_iou=to_float(input_data["predicted_iou"]),
            segmentation_output_path=input_data["segmentation_output_path"],
            object_detection_output_path=input_data["object_detection_output_path"]
        )
        if not step16["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Automated QC failed"
            }

        # Step 17: Perform human‑in‑the‑loop validation
        step17 = manager.performHumanValidation(
            video_id=input_data["video_id"],
            predicted_object=input_data["predicted_object"],
            predicted_iou=to_float(input_data["predicted_iou"]),
            segmentation_output_path=input_data["segmentation_output_path"],
            object_detection_output_path=input_data["object_detection_output_path"]
        )
        if not step17["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Human validation failed"
            }

        # Step 18: Check spatial accuracy against ground truth
        step18 = manager.checkSpatialAccuracy(
            video_id=input_data["video_id"],
            spatial_accuracy_score=to_float(input_data["spatial_accuracy_score"])
        )
        if not step18["is_valid"] or step18["spatial_accuracy_score"] < 0.85:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Spatial accuracy below threshold"
            }

        # Step 19: Validate temporal consistency of final annotations
        step19 = manager.validateTemporalConsistency(
            video_id=input_data["video_id"],
            temporal_consistency_score=to_float(input_data["temporal_consistency_score"])
        )
        if not step19["is_valid"] or step19["temporal_consistency_score"] < 0.80:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Temporal consistency below threshold"
            }

        # Step 20: Validate inter‑annotator agreement score
        step20 = manager.validateAnnotatorScores(
            video_id=input_data["video_id"],
            inter_annotator_score=to_float(input_data["inter_annotator_score"])
        )
        if not step20["is_valid"] or step20["inter_annotator_score"] < 0.75:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": step20["inter_annotator_score"],
                "reason": "Inter‑annotator score below threshold"
            }

        # All checks passed – assemble final output
        return {
            "final_status": True,
            "coco_json_path": input_data["object_detection_output_path"],
            "segmentation_mask_path": input_data["segmentation_output_path"],
            "inter_annotator_score": step20["inter_annotator_score"],
            "reason": "All validations passed"
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
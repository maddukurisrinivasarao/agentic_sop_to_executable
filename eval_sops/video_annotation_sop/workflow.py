from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Helper to normalize boolean strings
        def to_bool(val):
            return str(val).strip().lower() == "true"

        # Extract and cast input parameters
        video_id = input_data["video_id"]
        video_path = input_data["video_path"]
        weather = input_data["weather"]
        scene_type = input_data["scene_type"]
        channel_count = int(input_data["channel_count"])
        resolution_width = int(input_data["resolution_width"])
        resolution_height = int(input_data["resolution_height"])
        bit_depth = int(input_data["bit_depth"])
        frame_rate = float(input_data["frame_rate"])
        camera_intrinsics_available = to_bool(input_data["camera_intrinsics_available"])
        camera_position = input_data["camera_position"]
        lidar_point_cloud_path = input_data["lidar_point_cloud_path"]
        time_offset = float(input_data["time_offset"])
        object_detection_output_path = input_data["object_detection_output_path"]
        output_format_object_detection = input_data["output_format_object_detection"]
        tracking_enabled = to_bool(input_data["tracking_enabled"])
        predicted_object = input_data["predicted_object"]
        predicted_iou = float(input_data["predicted_iou"])
        segmentation_output_path = input_data["segmentation_output_path"]
        spatial_accuracy_score = float(input_data["spatial_accuracy_score"])
        temporal_consistency_score = float(input_data["temporal_consistency_score"])
        inter_annotator_score = float(input_data["inter_annotator_score"])

        # Step 1: Validate video format and metadata
        step1 = manager.validateVideoFormat(video_id=video_id)
        if not step1["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Video format validation failed"
            }

        # Step 2: Validate recorded weather conditions
        step2 = manager.validateWeatherConditions(video_id=video_id, weather=weather)
        if not step2["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Weather condition validation failed"
            }

        # Step 3: Validate scene context (urban required)
        step3 = manager.validateSceneContext(video_id=video_id, scene_type=scene_type)
        if not step3["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Scene context validation failed"
            }

        # Step 4: Validate number of color channels
        step4 = manager.validateChannelCount(video_id=video_id, channel_count=channel_count)
        if not step4["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Channel count validation failed"
            }

        # Step 5: Process high‑resolution video if needed
        step5 = manager.processHighResolution(
            video_id=video_id,
            resolution_width=resolution_width,
            resolution_height=resolution_height
        )
        if not step5["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "High‑resolution processing failed"
            }

        # Step 6: Adjust video bit depth
        step6 = manager.adjustBitDepth(video_id=video_id, bit_depth=bit_depth)
        if not step6["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Bit depth adjustment failed"
            }

        # Step 7: Optimize frame rate to required range
        step7 = manager.optimizeFrameRate(video_id=video_id, frame_rate=frame_rate)
        if not step7["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Frame rate optimization failed"
            }

        # Step 8: Validate camera intrinsic parameters availability
        step8 = manager.validateCameraIntrinsics(
            video_id=video_id,
            camera_intrinsics_available=camera_intrinsics_available
        )
        if not step8["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Camera intrinsics validation failed"
            }

        # Step 9: Calibrate front‑camera sensors
        step9 = manager.calibrateCameraSensors(
            video_id=video_id,
            camera_position=camera_position
        )
        if not step9["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Camera calibration failed"
            }

        # Step 10: Analyze camera stability and vibration
        step10 = manager.analyzeCameraStability(
            video_id=video_id,
            camera_position=camera_position
        )
        if not step10["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Camera stability analysis failed"
            }

        # Step 11: Validate LiDAR data completeness and synchronization
        step11 = manager.validateLidarData(video_id=video_id, video_path=video_path)
        if not step11["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "LiDAR data validation failed"
            }

        # Step 12: Synchronize LiDAR timestamps with video
        step12 = manager.synchronizeLidarTimestamp(
            video_id=video_id,
            time_offset=time_offset
        )
        if not step12["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "LiDAR timestamp synchronization failed"
            }

        # Step 13: Generate depth map from LiDAR point cloud
        step13 = manager.generateDepthMap(
            video_id=video_id,
            lidar_point_cloud_path=lidar_point_cloud_path
        )
        if not step13["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Depth map generation failed"
            }

        # Step 14: Perform object detection on validated video
        step14 = manager.performObjectDetection(
            video_id=video_id,
            video_path=video_path
        )
        if not step14["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Object detection failed"
            }

        # Step 15: Validate object‑detection output format (COCO required)
        step15 = manager.validateOutputFormat(
            video_id=video_id,
            output_format_object_detection=output_format_object_detection
        )
        if not step15["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Object detection output format validation failed"
            }

        # Step 16: Optimize tracking settings based on flag
        step16 = manager.optimizeTrackingSettings(
            video_id=video_id,
            tracking_enabled=tracking_enabled
        )
        if not step16["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Tracking settings optimization failed"
            }

        # Step 17: Track object motion across frames
        step17 = manager.trackObjectMotion(
            video_id=video_id,
            predicted_object=predicted_object
        )
        if not step17["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Object motion tracking failed"
            }

        # Step 18: Execute segmentation on detected objects
        step18 = manager.executeSegmentation(
            video_id=video_id,
            predicted_object=predicted_object,
            object_detection_output_path=object_detection_output_path,
            output_format_object_detection=output_format_object_detection
        )
        if not step18["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Segmentation execution failed"
            }

        # Step 19: Run automated quality control checks
        step19 = manager.runAutomatedQC(
            video_id=video_id,
            video_path=video_path,
            predicted_object=predicted_object,
            predicted_iou=predicted_iou,
            segmentation_output_path=segmentation_output_path,
            object_detection_output_path=object_detection_output_path
        )
        if not step19["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Automated QC failed"
            }

        # Step 20: Perform human‑in‑the‑loop validation
        step20 = manager.performHumanValidation(
            video_id=video_id,
            predicted_object=predicted_object,
            predicted_iou=predicted_iou,
            segmentation_output_path=segmentation_output_path,
            object_detection_output_path=object_detection_output_path
        )
        if not step20["is_valid"]:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Human validation failed"
            }

        # Step 21: Check spatial accuracy against ground truth
        step21 = manager.checkSpatialAccuracy(
            video_id=video_id,
            spatial_accuracy_score=spatial_accuracy_score
        )
        if not step21["is_valid"] or spatial_accuracy_score < 0.85:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Spatial accuracy below threshold"
            }

        # Step 22: Validate temporal consistency metric
        step22 = manager.validateTemporalConsistency(
            video_id=video_id,
            temporal_consistency_score=temporal_consistency_score
        )
        if not step22["is_valid"] or temporal_consistency_score < 0.80:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Temporal consistency below threshold"
            }

        # Step 23: Validate inter‑annotator agreement score
        step23 = manager.validateAnnotatorScores(
            video_id=video_id,
            inter_annotator_score=inter_annotator_score
        )
        if not step23["is_valid"] or inter_annotator_score < 0.75:
            return {
                "final_status": False,
                "coco_json_path": None,
                "segmentation_mask_path": None,
                "inter_annotator_score": None,
                "reason": "Inter‑annotator score below threshold"
            }

        # All checks passed – assemble final output
        return {
            "final_status": True,
            "coco_json_path": object_detection_output_path,
            "segmentation_mask_path": segmentation_output_path,
            "inter_annotator_score": inter_annotator_score,
            "reason": "All validation and quality checks passed"
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
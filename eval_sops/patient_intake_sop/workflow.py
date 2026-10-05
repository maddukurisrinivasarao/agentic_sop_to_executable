from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Validate primary insurance coverage
        insurance_res = manager.validateInsurance(
            patient_id=input_data["patient_id"],
            insurance_provider=input_data["insurance_provider"],
            policy_number=input_data["policy_number"],
            group_number=input_data["group_number"],
            coverage_start_date=input_data["coverage_start_date"],
            insurance_type=input_data["insurance_type"]
        )
        insurance_validation = insurance_res["insurance_validation"]

        # Step 2: Validate prescription insurance benefits
        prescription_res = manager.validatePrescriptionBenefits(
            patient_id=input_data["patient_id"],
            insurance_provider=input_data["insurance_provider"],
            policy_number=input_data["policy_number"]
        )
        prescription_insurance_validation = prescription_res["prescription_insurance_validation"]

        # Step 3: Calculate lifestyle risk level
        lifestyle_res = manager.calculateLifestyleRisk(
            patient_id=input_data["patient_id"],
            smoking_status=input_data["smoking_status"],
            alcohol_consumption=input_data["alcohol_consumption"],
            exercise_frequency=input_data["exercise_frequency"]
        )
        life_style_risk_level = lifestyle_res["life_style_risk_level"]

        # Step 4: Calculate overall clinical risk level
        overall_risk_res = manager.calculateOverallRisk(
            patient_id=input_data["patient_id"],
            previous_surgeries=input_data["previous_surgeries"],
            chronic_conditions=input_data["chronic_conditions"],
            life_style_risk_level=life_style_risk_level
        )
        overall_risk_level = overall_risk_res["overall_risk_level"]

        # Step 5: Verify preferred pharmacy network participation
        pharmacy_res = manager.verifyPharmacy(
            patient_id=input_data["patient_id"],
            preferred_pharmacy_name=input_data["preferred_pharmacy_name"],
            preferred_pharmacy_address=input_data["preferred_pharmacy_address"],
            pharmacy_phone=input_data["pharmacy_phone"]
        )
        pharmacy_check = pharmacy_res["pharmacy_check"]

        # Step 6: Complete patient registration
        registration_res = manager.registerPatient(
            patient_id=input_data["patient_id"],
            insurance_validation=insurance_validation,
            prescription_insurance_validation=prescription_insurance_validation,
            life_style_risk_level=life_style_risk_level,
            overall_risk_level=overall_risk_level,
            pharmacy_check=pharmacy_check
        )
        user_registration = registration_res["user_registration"]

        # Combine every step's result as defined in SOP Output section
        return {
            "insurance_validation": insurance_validation,
            "prescription_insurance_validation": prescription_insurance_validation,
            "pharmacy_check": pharmacy_check,
            "life_style_risk_level": life_style_risk_level,
            "overall_risk_level": overall_risk_level,
            "user_registration": user_registration
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
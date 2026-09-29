from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Validate primary insurance using provided insurance details
        insurance_validation = manager.validateInsurance(
            patient_id=input_data["patient_id"],
            insurance_provider=input_data["insurance_provider"],
            policy_number=input_data["policy_number"],
            group_number=input_data["group_number"],
            coverage_start_date=input_data["coverage_start_date"],
            insurance_type=input_data["insurance_type"],
        )

        # Step 2: Validate prescription benefits via PBM using insurance information
        prescription_insurance_validation = manager.validatePrescriptionBenefits(
            patient_id=input_data["patient_id"],
            insurance_provider=input_data["insurance_provider"],
            policy_number=input_data["policy_number"],
        )

        # Step 3: Calculate lifestyle risk based on smoking, alcohol, and exercise data
        life_style_risk_level = manager.calculateLifestyleRisk(
            patient_id=input_data["patient_id"],
            smoking_status=input_data["smoking_status"],
            alcohol_consumption=input_data["alcohol_consumption"],
            exercise_frequency=input_data["exercise_frequency"],
        )

        # Step 4: Calculate overall clinical risk incorporating surgeries, chronic conditions, and lifestyle risk
        overall_risk_level = manager.calculateOverallRisk(
            patient_id=input_data["patient_id"],
            previous_surgeries=input_data["previous_surgeries"],
            chronic_conditions=input_data["chronic_conditions"],
            life_style_risk_level=life_style_risk_level,
        )

        # Step 5: Verify that the preferred pharmacy participates in the network
        pharmacy_check = manager.verifyPharmacy(
            patient_id=input_data["patient_id"],
            preferred_pharmacy_name=input_data["preferred_pharmacy_name"],
            preferred_pharmacy_address=input_data["preferred_pharmacy_address"],
            pharmacy_phone=input_data["pharmacy_phone"],
        )

        # Step 6: Register the patient after all validations and risk assessments succeed
        registration_status = manager.registerPatient(
            patient_id=input_data["patient_id"],
            insurance_validation=insurance_validation,
            prescription_insurance_validation=prescription_insurance_validation,
            life_style_risk_level=life_style_risk_level,
            overall_risk_level=overall_risk_level,
            pharmacy_check=pharmacy_check,
        )

        # Combine every step's result as required by the SOP output section
        return {
            "insurance_validation": insurance_validation,
            "prescription_insurance_validation": prescription_insurance_validation,
            "life_style_risk_level": life_style_risk_level,
            "overall_risk_level": overall_risk_level,
            "pharmacy_check": pharmacy_check,
            "registration_status": registration_status,
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
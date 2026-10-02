from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Retrieve complete business profile
        business_profile = manager.getBusinessProfile(
            business_id=input_data["business_id"]
        )

        # Step 2: Retrieve UBO ownership data
        ownership_data = manager.getOwnershipData(
            business_id=input_data["business_id"]
        )
        ubo_list = ownership_data["ubo_list"]

        # Step 3: Execute sanctions and PEP screening for all UBOs
        sanctions_result = manager.performSanctionsCheck(
            business_id=input_data["business_id"],
            ubo_list=ubo_list
        )
        sanction_status_list = sanctions_result["sanction_check_status"]
        pep_status_list = sanctions_result["pep_status"]

        # Step 4: Validate business registration and licensing
        registration_result = manager.verifyBusinessRegistration(
            business_id=input_data["business_id"],
            registration_number=business_profile["registration_number"],
            business_registration_state=business_profile["business_registration_state"],
            license_number=business_profile["license_number"]
        )
        license_expiry_date = registration_result["license_expiry_date"]

        # Step 5: Assess UBO structure and jurisdiction risk
        ubo_verification = manager.verifyUBO(
            business_id=input_data["business_id"],
            ubo_list=ubo_list
        )
        shell_company_suspected = ubo_verification["shell_company_suspected"]
        offshore_jurisdiction_flag = ubo_verification["offshore_jurisdiction_flag"]

        # Step 6: Retrieve bank account details
        bank_data = manager.getBankData(
            business_id=input_data["business_id"]
        )
        bank_account_number = bank_data["bank_account_number"]
        banking_institution = bank_data["banking_institution"]
        bank_account_type = bank_data["bank_account_type"]

        # Step 7: Verify bank account ownership and status
        bank_verification = manager.verifyBankAccount(
            business_id=input_data["business_id"],
            bank_account_number=bank_account_number,
            banking_institution=banking_institution,
            bank_account_type=bank_account_type
        )
        bank_verification_status = bank_verification["bank_verification_status"]

        # Step 8: Calculate overall risk score (not used for decision per SOP)
        risk_result = manager.calculateRiskScore(
            business_id=input_data["business_id"]
        )
        risk_score = risk_result["risk_score"]

        # -----------------------------------------------------------------
        # Decision Logic for escalation_status and reason
        # -----------------------------------------------------------------

        # a) Incomplete screening takes priority
        pending_screening = any(
            entry.get("status") == "Pending" for entry in sanction_status_list
        )
        if pending_screening:
            escalation_status = "awaiting information"
            reason = "Pending sanctions screening for one or more UBO(s)."
        else:
            # b) Evaluate escalation triggers
            # Tax ID format validation
            tax_id = business_profile["tax_id"]
            tax_id_invalid = False
            if not tax_id.startswith("TIN"):
                tax_id_invalid = True
            else:
                digits_part = tax_id[3:]
                if len(digits_part) != 6 or not digits_part.isdigit():
                    tax_id_invalid = True
                elif len(set(digits_part)) == 1:  # all digits identical
                    tax_id_invalid = True

            # License expiry check (simple presence check)
            license_expired = not license_expiry_date or license_expiry_date.strip() == ""

            # Sanctions match check
            sanctions_matched = any(
                entry.get("status") == "Matched" for entry in sanction_status_list
            )

            # PEP identified check
            pep_identified = any(
                entry.get("status") == "Yes" for entry in pep_status_list
            )

            # Bank verification failure check
            bank_failed = bank_verification_status != "Verified"

            # Determine if any trigger fires
            trigger_reason = None
            if tax_id_invalid:
                trigger_reason = "Invalid Tax ID format."
            elif license_expired:
                trigger_reason = "Business license has expired or missing expiry date."
            elif sanctions_matched:
                trigger_reason = "Sanctions match found for a UBO."
            elif pep_identified:
                trigger_reason = "Politically Exposed Person (PEP) identified among UBOs."
            elif shell_company_suspected:
                trigger_reason = "Shell company suspected based on ownership structure."
            elif offshore_jurisdiction_flag:
                trigger_reason = "Offshore jurisdiction flagged."
            elif bank_failed:
                trigger_reason = "Bank account verification failed or flagged."

            if trigger_reason:
                escalation_status = "escalate"
                reason = trigger_reason
            else:
                # c) Approved when no pending screening and no triggers
                escalation_status = "approved"
                reason = "All verification checks passed."

        # -----------------------------------------------------------------
        # Assemble final output
        # -----------------------------------------------------------------
        return {
            "business_id": input_data["business_id"],
            "escalation_status": escalation_status,
            "reason": reason,
            "risk_score": risk_score,  # optional audit field
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
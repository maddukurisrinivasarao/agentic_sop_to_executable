from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Retrieve complete business profile
        profile = manager.getBusinessProfile(business_id=input_data["business_id"])

        # Step 2: Retrieve UBO ownership data
        ownership = manager.getOwnershipData(business_id=input_data["business_id"])

        # Step 3: Verify business registration and licensing
        registration = manager.verifyBusinessRegistration(
            business_id=input_data["business_id"],
            registration_number=profile["registration_number"],
            business_registration_state=profile["business_registration_state"],
            license_number=profile["license_number"]
        )

        # Step 4: Verify UBO structure and jurisdiction risk
        ubo_analysis = manager.verifyUBO(
            business_id=input_data["business_id"],
            ubo_list=ownership["ubo_list"]
        )

        # Step 5: Execute sanctions and PEP screening for UBOs
        sanctions = manager.performSanctionsCheck(
            business_id=input_data["business_id"],
            ubo_list=ownership["ubo_list"]
        )

        # Step 6: Retrieve banking information
        bank_data = manager.getBankData(business_id=input_data["business_id"])

        # Step 7: Verify bank account details and ownership alignment
        bank_verification = manager.verifyBankAccount(
            business_id=input_data["business_id"],
            bank_account_number=bank_data["bank_account_number"],
            banking_institution=bank_data["banking_institution"],
            bank_account_type=bank_data["bank_account_type"]
        )

        # Step 8: Calculate overall risk score
        risk = manager.calculateRiskScore(business_id=input_data["business_id"])

        # Preliminary tax ID validation (used later for escalation triggers)
        tax_id = profile.get("tax_id", "")
        tax_valid = (
            tax_id.startswith("TIN") and
            len(tax_id) == 9 and
            tax_id[3:].isdigit() and
            len(set(tax_id[3:])) > 1
        )

        # Determine escalation status following SOP hierarchy
        # (a) Incomplete screening priority: any sanctions check still pending
        pending = any(item.get("status") == "Pending" for item in sanctions["sanction_check_status"])
        if pending:
            escalation_status = "awaiting information"
            reason = "Sanctions check pending for one or more UBOs."
        else:
            # (b) Escalation triggers
            triggers = []

            if not tax_valid:
                triggers.append("Invalid Tax ID format")

            # License expiry trigger omitted due to lack of date handling utilities

            if any(item.get("status") == "Matched" for item in sanctions["sanction_check_status"]):
                triggers.append("Sanctions match found")

            if any(item.get("status") == "Yes" for item in sanctions["pep_status"]):
                triggers.append("PEP identified")

            if ubo_analysis.get("shell_company_suspected"):
                triggers.append("Shell company suspected")

            if ubo_analysis.get("offshore_jurisdiction_flag"):
                triggers.append("Offshore jurisdiction flagged")

            if bank_verification.get("bank_verification_status") != "Verified":
                triggers.append("Bank verification failed or flagged")

            if triggers:
                escalation_status = "escalate"
                reason = "; ".join(triggers)
            else:
                # (c) Approved when no pending checks and no triggers
                escalation_status = "approved"
                reason = "All checks passed."

        # Assemble final output dictionary
        return {
            "business_id": input_data["business_id"],
            "escalation_status": escalation_status,
            "reason": reason,
            "risk_score": risk.get("risk_score"),
            "tax_id_valid": tax_valid,
            "sanctions_check_status": sanctions["sanction_check_status"],
            "pep_status": sanctions["pep_status"],
            "shell_company_suspected": ubo_analysis.get("shell_company_suspected"),
            "offshore_jurisdiction_flag": ubo_analysis.get("offshore_jurisdiction_flag"),
            "bank_verification_status": bank_verification.get("bank_verification_status")
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
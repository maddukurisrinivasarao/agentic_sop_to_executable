from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Helper: parse ISO date string to year, month, day integers
        def _parse_date(date_str):
            if not date_str:
                return None, None, None
            date_part = date_str.split(' ')[0]
            parts = date_part.split('-')
            if len(parts) != 3:
                return None, None, None
            return int(parts[0]), int(parts[1]), int(parts[2])

        # Helper: compute days since a fixed epoch (1970-01-01) accounting for leap years
        def _days_since_epoch(y, m, d):
            if y is None:
                return None
            days = 0
            for yr in range(1970, y):
                days += 366 if (yr % 4 == 0 and (yr % 100 != 0 or yr % 400 == 0)) else 365
            month_lengths = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
                month_lengths[1] = 29
            for mo in range(1, m):
                days += month_lengths[mo - 1]
            days += d
            return days

        # Step 1: Retrieve complete business profile
        profile = manager.getBusinessProfile(
            business_id=input_data["business_id"]
        )
        # Extract needed fields
        business_name = profile.get("business_name")
        business_website = profile.get("business_website")
        business_address = profile.get("business_address")
        business_email = profile.get("business_email")
        registration_number = profile.get("registration_number")
        license_number = profile.get("license_number")
        tax_id = profile.get("tax_id")
        business_registration_state = profile.get("business_registration_state")

        # Step 2: Obtain Ultimate Beneficial Owner data
        ownership = manager.getOwnershipData(
            business_id=input_data["business_id"]
        )
        ubo_list = ownership.get("ubo_list", [])

        # Step 3: Validate business registration and licensing
        registration_info = manager.verifyBusinessRegistration(
            business_id=input_data["business_id"],
            registration_number=registration_number,
            business_registration_state=business_registration_state,
            license_number=license_number
        )
        registration_status = registration_info.get("registration_status")
        date_of_entry_str = registration_info.get("date_of_entry")
        license_expiry_str = registration_info.get("license_expiry_date")

        # Step 4: Screen UBOs against sanctions and PEP lists
        sanctions_result = manager.performSanctionsCheck(
            business_id=input_data["business_id"],
            ubo_list=ubo_list
        )
        sanction_check_status = sanctions_result.get("sanction_check_status", [])
        pep_status_list = sanctions_result.get("pep_status", [])

        # Step 5: Retrieve banking information
        bank_data = manager.getBankData(
            business_id=input_data["business_id"]
        )
        bank_account_number = bank_data.get("bank_account_number")
        banking_institution = bank_data.get("banking_institution")
        bank_account_type = bank_data.get("bank_account_type")

        # Step 6: Validate bank account details
        bank_verification = manager.verifyBankAccount(
            business_id=input_data["business_id"],
            bank_account_number=bank_account_number,
            banking_institution=banking_institution,
            bank_account_type=bank_account_type
        )
        bank_verification_status = bank_verification.get("bank_verification_status")

        # Step 7: Analyze ownership structure and jurisdiction risk
        ubo_analysis = manager.verifyUBO(
            business_id=input_data["business_id"],
            ubo_list=ubo_list
        )
        shell_company_suspected = ubo_analysis.get("shell_company_suspected")
        ownership_layer_count = ubo_analysis.get("ownership_layer_count")
        offshore_jurisdiction_flag = ubo_analysis.get("offshore_jurisdiction_flag")

        # Step 8: Calculate overall risk score (not used for final decision)
        risk_info = manager.calculateRiskScore(
            business_id=input_data["business_id"]
        )
        risk_score = risk_info.get("risk_score")

        # ---------- Decision Logic ----------
        # Initial escalation status and reason placeholders
        escalation_status = "approved"
        reason = "All checks passed."

        # Tax ID validation
        tax_id_valid = False
        if isinstance(tax_id, str):
            tax_id = tax_id.strip()
            if tax_id.startswith("TIN"):
                digits = tax_id[3:]
                if len(digits) == 6 and digits.isdigit() and len(set(digits)) > 1:
                    tax_id_valid = True
        if not tax_id_valid:
            escalation_status = "escalate"
            reason = "Invalid Tax ID format."

        # License expiry check (only if still approved)
        if escalation_status == "approved":
            y_entry, m_entry, d_entry = _parse_date(date_of_entry_str)
            y_exp, m_exp, d_exp = _parse_date(license_expiry_str)
            entry_days = _days_since_epoch(y_entry, m_entry, d_entry)
            expiry_days = _days_since_epoch(y_exp, m_exp, d_exp)
            if entry_days is not None and expiry_days is not None:
                if (entry_days - expiry_days) > 42:
                    escalation_status = "escalate"
                    reason = "Business license expired more than 42 days ago."

        # Pending sanctions check overrides all other escalations
        pending_found = any(
            isinstance(item, dict) and item.get("status") == "Pending"
            for item in sanction_check_status
        )
        if pending_found:
            escalation_status = "awaiting information"
            reason = "Sanctions check pending for one or more UBOs."
        else:
            # After confirming no pending, evaluate other triggers if still approved
            if escalation_status == "approved":
                # Sanctions Matched
                matched_found = any(
                    isinstance(item, dict) and item.get("status") == "Matched"
                    for item in sanction_check_status
                )
                if matched_found:
                    escalation_status = "escalate"
                    reason = "Sanctions match found for UBO."
                else:
                    # PEP identification
                    pep_yes = any(
                        isinstance(item, dict) and item.get("status") == "Yes"
                        for item in pep_status_list
                    )
                    if pep_yes:
                        escalation_status = "escalate"
                        reason = "PEP identified among UBOs."
                    else:
                        # Offshore jurisdiction flag
                        if offshore_jurisdiction_flag:
                            escalation_status = "escalate"
                            reason = "Entity registered in offshore jurisdiction."
                        else:
                            # Shell company suspicion
                            if shell_company_suspected:
                                escalation_status = "escalate"
                                reason = "Shell company suspected based on ownership structure."
        # Combine final output fields
        return {
            "business_id": input_data["business_id"],
            "escalation_status": escalation_status,
            "reason": reason
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
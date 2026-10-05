from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Validate Account ID format
        validate_resp = manager.validateAccount(
            account_id=input_data["account_id"]
        )
        is_account_id_valid = validate_resp["is account id valid"]
        # Early termination if Account ID format is invalid
        if not is_account_id_valid:
            return {
                "is_account_id_valid": is_account_id_valid,
                "is_authenticated": False,
                "ticket_id": "",
                "account_status": "",
                "account_suspension_status": "",
                "eligible_for_support": False,
                "outage_detected": False,
                "diagnostic_needed": False,
                "latency_issue": False,
                "stability_issue": False,
                "bandwidth_issue": False,
                "metrics_improved_post_troubleshooting": False,
                "escalation_required": False,
                "escalation_ticket_id": "",
                "resolution_summary": "Account ID validation failed; process terminated.",
                "final_resolution_status": "FAILED"
            }

        # Step 2: Retrieve authentication details
        auth_resp = manager.getAuthenticationDetails(
            account_id=input_data["account_id"],
            is_account_id_valid=is_account_id_valid
        )
        auth_records = auth_resp["authentication records"]
        login_status = auth_records["login_status"]
        recovery_status = auth_records["account_recovery_status"]
        # Determine authentication success
        is_authenticated = (
            login_status == "SUCCESS" or
            (login_status == "FAILURE" and recovery_status == "SUCCESS")
        )
        # Early termination if authentication fails
        if not is_authenticated:
            return {
                "is_account_id_valid": is_account_id_valid,
                "is_authenticated": is_authenticated,
                "ticket_id": "",
                "account_status": "",
                "account_suspension_status": "",
                "eligible_for_support": False,
                "outage_detected": False,
                "diagnostic_needed": False,
                "latency_issue": False,
                "stability_issue": False,
                "bandwidth_issue": False,
                "metrics_improved_post_troubleshooting": False,
                "escalation_required": False,
                "escalation_ticket_id": "",
                "resolution_summary": "Authentication failed; process terminated.",
                "final_resolution_status": "FAILED"
            }

        # Step 3: Create session token and open service ticket
        session_ticket_resp = manager.createSessionAndOpenTicket(
            account_id=input_data["account_id"],
            is_account_id_valid=is_account_id_valid,
            is_authenticated=is_authenticated
        )
        session_token = session_ticket_resp["session token"]
        ticket_id = session_ticket_resp["ticket identifer"]

        # Step 4: Check current account status
        status_resp = manager.checkAccountStatus(
            account_id=input_data["account_id"],
            session_token=session_token
        )
        account_status = status_resp["account status"]
        status_reason = status_resp["reason"]

        # Early termination if account is terminated
        if account_status == "TERMINATED":
            return {
                "is_account_id_valid": is_account_id_valid,
                "is_authenticated": is_authenticated,
                "ticket_id": ticket_id,
                "account_status": account_status,
                "account_suspension_status": "",
                "eligible_for_support": False,
                "outage_detected": False,
                "diagnostic_needed": False,
                "latency_issue": False,
                "stability_issue": False,
                "bandwidth_issue": False,
                "metrics_improved_post_troubleshooting": False,
                "escalation_required": False,
                "escalation_ticket_id": "",
                "resolution_summary": f"Account terminated ({status_reason}); no support possible.",
                "final_resolution_status": "FAILED"
            }

        # Step 5: Verify account suspension status (if applicable)
        suspension_resp = manager.checkAccountSuspensionStatus(
            account_id=input_data["account_id"],
            session_token=session_token
        )
        account_suspension_status = suspension_resp["account suspension status"]

        eligible_for_support = True
        suspension_block = False

        if account_status == "SUSPENDED":
            # If still suspended, determine cause
            if account_suspension_status == "SUSPENDED":
                suspension_block = True
                # Check if reason relates to non‑payment
                if "payment" in status_reason.lower() or "non‑payment" in status_reason.lower():
                    payment_resp = manager.checkPaymentStatus(
                        account_id=input_data["account_id"],
                        session_token=session_token
                    )
                    payment_status = payment_resp["overdue payment status"]
                    # Assign to Accounts Payable (no further action in code)
                    eligible_for_support = False
                else:
                    # Non‑payment reason other than payment issue – ineligible
                    eligible_for_support = False
                # Early termination for suspended accounts that are not lifted
                return {
                    "is_account_id_valid": is_account_id_valid,
                    "is_authenticated": is_authenticated,
                    "ticket_id": ticket_id,
                    "account_status": account_status,
                    "account_suspension_status": account_suspension_status,
                    "eligible_for_support": eligible_for_support,
                    "outage_detected": False,
                    "diagnostic_needed": False,
                    "latency_issue": False,
                    "stability_issue": False,
                    "bandwidth_issue": False,
                    "metrics_improved_post_troubleshooting": False,
                    "escalation_required": False,
                    "escalation_ticket_id": "",
                    "resolution_summary": f"Account suspended ({status_reason}); support not eligible.",
                    "final_resolution_status": "FAILED"
                }
            else:
                # Suspension lifted (status ACTIVE or empty) – continue
                pass

        # If account is ACTIVE, continue
        # Step 6: Search for regional service outages
        outage_resp = manager.checkServiceAreaOutage(
            account_id=input_data["account_id"],
            session_token=session_token,
            service_area_code=input_data["service_area_code"]
        )
        outage_detected = outage_resp["outage detected"]
        # If outage detected, no further diagnostics needed
        if outage_detected:
            return {
                "is_account_id_valid": is_account_id_valid,
                "is_authenticated": is_authenticated,
                "ticket_id": ticket_id,
                "account_status": account_status,
                "account_suspension_status": account_suspension_status,
                "eligible_for_support": eligible_for_support,
                "outage_detected": outage_detected,
                "diagnostic_needed": False,
                "latency_issue": False,
                "stability_issue": False,
                "bandwidth_issue": False,
                "metrics_improved_post_troubleshooting": False,
                "escalation_required": False,
                "escalation_ticket_id": "",
                "resolution_summary": f"Outage detected (ID: {outage_resp.get('outage id','')}); awaiting resolution.",
                "final_resolution_status": "PENDING_ACTION"
            }

        # Step 7: Run technical diagnostics
        diag_resp = manager.performTechnicalDiagnostics(
            account_id=input_data["account_id"],
            session_token=session_token,
            service_type=input_data["service_type"],
            subscribed_bandwidth=input_data["subscribed_bandwidth"]
        )
        service_metrics = diag_resp["service metrics"]
        latency = service_metrics["latency"]
        jitter = service_metrics["jitter"]
        bandwidth = service_metrics["bandwidth"]
        root_causes = diag_resp["root causes"]

        # Determine issues based on thresholds
        latency_issue = latency > 100
        stability_issue = jitter > 30

        # Parse subscribed bandwidth numeric value
        bw_str = input_data["subscribed_bandwidth"]
        bw_numeric = float(''.join(ch for ch in bw_str if (ch.isdigit() or ch == '.')))
        bandwidth_issue = bandwidth < bw_numeric

        # Step 8: Execute automated troubleshooting
        troubleshoot_resp = manager.executeTroubleshooting(
            account_id=input_data["account_id"],
            session_token=session_token,
            root_causes=root_causes
        )
        updated_metrics = troubleshoot_resp["updated service metrics"]
        updated_latency = updated_metrics["latency"]
        updated_jitter = updated_metrics["jitter"]
        # Determine if metrics improved post‑troubleshooting
        metrics_improved_post_troubleshooting = (
            updated_latency <= 100 and updated_jitter <= 30
        )

        # Step 9: Escalation if needed
        escalation_required = not metrics_improved_post_troubleshooting
        escalation_ticket_id = ""
        if escalation_required:
            escalation_resp = manager.createEscalation(
                session_token=session_token,
                ticket_id=ticket_id,
                metrics_improved_post_troubleshooting=metrics_improved_post_troubleshooting,
                escalation_required=escalation_required
            )
            escalation_ticket_id = escalation_resp["escalation ticket"]
            # escalation team and reason are captured but not required in final output

        # Build resolution summary
        summary_parts = [
            f"Account ID: {input_data['account_id']}",
            f"Ticket ID: {ticket_id}",
            f"Account status: {account_status}",
            f"Suspension status: {account_suspension_status or 'None'}",
            f"Outage detected: {outage_detected}",
            f"Diagnostic metrics – latency: {latency}ms (issue: {latency_issue}), "
            f"jitter: {jitter}ms (issue: {stability_issue}), "
            f"bandwidth: {bandwidth}Mbps (subscribed: {bw_numeric}Mbps, issue: {bandwidth_issue})",
            f"Post‑troubleshooting metrics – latency: {updated_latency}ms, jitter: {updated_jitter}ms",
            f"Metrics improved post‑troubleshooting: {metrics_improved_post_troubleshooting}",
            f"Escalation required: {escalation_required}",
            f"Escalation ticket ID: {escalation_ticket_id or 'N/A'}"
        ]
        resolution_summary = " | ".join(summary_parts)

        # Determine final resolution status
        if not is_account_id_valid or not is_authenticated or account_status == "TERMINATED":
            final_resolution_status = "FAILED"
        elif outage_detected:
            final_resolution_status = "PENDING_ACTION"
        elif metrics_improved_post_troubleshooting:
            final_resolution_status = "RESOLVED"
        elif escalation_required:
            final_resolution_status = "ESCALATED"
        else:
            final_resolution_status = "FAILED"

        return {
            "is_account_id_valid": is_account_id_valid,
            "is_authenticated": is_authenticated,
            "ticket_id": ticket_id,
            "account_status": account_status,
            "account_suspension_status": account_suspension_status,
            "eligible_for_support": eligible_for_support,
            "outage_detected": outage_detected,
            "diagnostic_needed": True,
            "latency_issue": latency_issue,
            "stability_issue": stability_issue,
            "bandwidth_issue": bandwidth_issue,
            "metrics_improved_post_troubleshooting": metrics_improved_post_troubleshooting,
            "escalation_required": escalation_required,
            "escalation_ticket_id": escalation_ticket_id,
            "resolution_summary": resolution_summary,
            "final_resolution_status": final_resolution_status
        }

    except Exception as e:
        return {"error": str(e), "status": "failed"}
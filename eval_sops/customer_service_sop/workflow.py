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
        # Early termination if Account ID is invalid
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
                "resolution_summary": "Account ID format validation failed. Process terminated.",
                "final_resolution_status": "FAILED"
            }

        # Step 2: Retrieve authentication history
        auth_resp = manager.getAuthenticationDetails(
            account_id=input_data["account_id"],
            is_account_id_valid=is_account_id_valid
        )
        auth_record = auth_resp["authentication records"]
        login_status = auth_record["login_status"]
        recovery_status = auth_record["account_recovery_status"]
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
                "resolution_summary": "Authentication failed. Process terminated.",
                "final_resolution_status": "FAILED"
            }

        # Step 3: Create session token and open service ticket
        session_resp = manager.createSessionAndOpenTicket(
            account_id=input_data["account_id"],
            is_account_id_valid=is_account_id_valid,
            is_authenticated=is_authenticated
        )
        session_token = session_resp["session token"]
        ticket_id = session_resp["ticket identifer"]

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
                "resolution_summary": f"Account terminated: {status_reason}. Process concluded.",
                "final_resolution_status": "FAILED"
            }

        # Step 5: Verify account suspension status
        suspension_resp = manager.checkAccountSuspensionStatus(
            account_id=input_data["account_id"],
            session_token=session_token
        )
        account_suspension_status = suspension_resp["account suspension status"]

        # Determine eligibility based on suspension
        eligible_for_support = True
        if account_status == "SUSPENDED":
            if account_suspension_status == "SUSPENDED":
                # Suspension still active
                if "non-payment" in status_reason.lower():
                    payment_resp = manager.checkPaymentStatus(
                        account_id=input_data["account_id"],
                        session_token=session_token
                    )
                    overdue_status = payment_resp["overdue payment status"]
                    if overdue_status == "PAID":
                        eligible_for_support = True
                        account_suspension_status = "ACTIVE"
                    else:
                        eligible_for_support = False
                else:
                    eligible_for_support = False
            elif account_suspension_status == "ACTIVE":
                # Suspension lifted
                eligible_for_support = True
            else:  # '' meaning no record
                eligible_for_support = True
        else:
            # ACTIVE status
            eligible_for_support = True

        # Early termination if not eligible for support
        if not eligible_for_support:
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
                "resolution_summary": "Account not eligible for support. Process concluded.",
                "final_resolution_status": "FAILED"
            }

        # Step 6: Detect service area outage
        outage_resp = manager.checkServiceAreaOutage(
            account_id=input_data["account_id"],
            session_token=session_token,
            service_area_code=input_data["service_area_code"]
        )
        outage_detected = outage_resp["outage detected"]
        # If outage detected, conclude diagnostics
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
                "resolution_summary": f"Outage detected (ID: {outage_resp['outage id']}). Awaiting resolution.",
                "final_resolution_status": "PENDING_ACTION"
            }

        # Step 7: Perform technical diagnostics
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

        latency_issue = latency > 100
        stability_issue = jitter > 30

        # Parse subscribed bandwidth numeric value
        bw_numeric_str = ''.join(ch for ch in input_data["subscribed_bandwidth"] if ch.isdigit() or ch == '.')
        subscribed_bw_mbps = float(bw_numeric_str) if bw_numeric_str else 0.0
        bandwidth_issue = bandwidth < subscribed_bw_mbps

        diagnostic_needed = True

        # Step 8: Execute troubleshooting steps
        troubleshoot_resp = manager.executeTroubleshooting(
            account_id=input_data["account_id"],
            session_token=session_token,
            root_causes=root_causes
        )
        updated_metrics = troubleshoot_resp["updated service metrics"]
        post_latency = updated_metrics["latency"]
        post_jitter = updated_metrics["jitter"]

        metrics_improved_post_troubleshooting = (post_latency <= 100) and (post_jitter <= 30)

        escalation_required = not metrics_improved_post_troubleshooting

        # Step 9: Create escalation ticket if needed
        escalation_ticket_id = ""
        if escalation_required:
            escalation_resp = manager.createEscalation(
                session_token=session_token,
                ticket_id=ticket_id,
                metrics_improved_post_troubleshooting=metrics_improved_post_troubleshooting,
                escalation_required=escalation_required
            )
            escalation_ticket_id = escalation_resp["escalation ticket"]

        # Build resolution summary
        summary_parts = [
            f"Account ID {input_data['account_id']} processed.",
            f"Authentication {'succeeded' if is_authenticated else 'failed'}.",
            f"Account status: {account_status}.",
            f"Suspension status: {account_suspension_status}.",
            f"Outage detected: {outage_detected}.",
            f"Diagnostic metrics - latency: {latency}ms (issue: {latency_issue}), jitter: {jitter}ms (issue: {stability_issue}), bandwidth: {bandwidth}Mbps (issue: {bandwidth_issue}).",
            f"Post‑troubleshooting metrics - latency: {post_latency}ms, jitter: {post_jitter}ms.",
            f"Metrics improved: {metrics_improved_post_troubleshooting}.",
            f"Escalation required: {escalation_required}."
        ]
        resolution_summary = " ".join(summary_parts)

        # Determine final resolution status
        if escalation_required:
            final_resolution_status = "ESCALATED"
        elif metrics_improved_post_troubleshooting:
            final_resolution_status = "RESOLVED"
        else:
            final_resolution_status = "FAILED"

        # Combine every step's result into the final output dict
        return {
            "is_account_id_valid": is_account_id_valid,
            "is_authenticated": is_authenticated,
            "ticket_id": ticket_id,
            "account_status": account_status,
            "account_suspension_status": account_suspension_status,
            "eligible_for_support": eligible_for_support,
            "outage_detected": outage_detected,
            "diagnostic_needed": diagnostic_needed,
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
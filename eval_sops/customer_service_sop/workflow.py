from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Validate Account ID format
        validation_res = manager.validateAccount(
            account_id=input_data["account_id"]
        )
        is_account_id_valid = validation_res["is account id valid"]
        # Early termination if Account ID is invalid
        if not is_account_id_valid:
            return {
                "is_account_id_valid": False,
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
                "resolution_summary": "Account ID format invalid. Process terminated.",
                "final_resolution_status": "FAILED"
            }

        # Step 2: Retrieve authentication history
        auth_res = manager.getAuthenticationDetails(
            account_id=input_data["account_id"],
            is_account_id_valid=is_account_id_valid
        )
        # The tool returns an object under key 'authentication records'.
        # For this SOP we assume authentication succeeds if records exist.
        authentication_records = auth_res["authentication records"]
        is_authenticated = bool(authentication_records)
        if not is_authenticated:
            return {
                "is_account_id_valid": True,
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
                "resolution_summary": "Authentication failed. Process terminated.",
                "final_resolution_status": "FAILED"
            }

        # Step 3: Create session token and open service ticket
        session_ticket_res = manager.createSessionAndOpenTicket(
            account_id=input_data["account_id"],
            is_account_id_valid=is_account_id_valid,
            is_authenticated=is_authenticated
        )
        session_token = session_ticket_res["session token"]
        ticket_id = session_ticket_res["ticket identifer"]

        # Step 4: Check current account status
        status_res = manager.checkAccountStatus(
            account_id=input_data["account_id"],
            session_token=session_token
        )
        account_status = status_res["account status"]
        suspension_reason = status_res["reason"]

        # Determine eligibility based on account status
        if account_status == "TERMINATED":
            return {
                "is_account_id_valid": True,
                "is_authenticated": True,
                "ticket_id": ticket_id,
                "account_status": "TERMINATED",
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
                "resolution_summary": "Account is terminated. No support eligible.",
                "final_resolution_status": "FAILED"
            }

        # Step 5: Verify suspension status if account is suspended
        account_suspension_status = ""
        if account_status == "SUSPENDED":
            suspension_status_res = manager.checkAccountSuspensionStatus(
                account_id=input_data["account_id"],
                session_token=session_token
            )
            account_suspension_status = suspension_status_res["account suspension status"]
            # If suspension not lifted, terminate
            if account_suspension_status != "ACTIVE":
                return {
                    "is_account_id_valid": True,
                    "is_authenticated": True,
                    "ticket_id": ticket_id,
                    "account_status": "SUSPENDED",
                    "account_suspension_status": account_suspension_status,
                    "eligible_for_support": False,
                    "outage_detected": False,
                    "diagnostic_needed": False,
                    "latency_issue": False,
                    "stability_issue": False,
                    "bandwidth_issue": False,
                    "metrics_improved_post_troubleshooting": False,
                    "escalation_required": False,
                    "escalation_ticket_id": "",
                    "resolution_summary": "Account suspension remains. No support eligible.",
                    "final_resolution_status": "FAILED"
                }
            # If suspension reason is non‑payment, verify payment status
            if "NON-PAYMENT" in suspension_reason.upper() or "PAYMENT" in suspension_reason.upper():
                payment_res = manager.checkPaymentStatus(
                    account_id=input_data["account_id"],
                    session_token=session_token
                )
                overdue_status = payment_res["overdue payment status"]
                if overdue_status != "PAID":
                    return {
                        "is_account_id_valid": True,
                        "is_authenticated": True,
                        "ticket_id": ticket_id,
                        "account_status": "SUSPENDED",
                        "account_suspension_status": account_suspension_status,
                        "eligible_for_support": False,
                        "outage_detected": False,
                        "diagnostic_needed": False,
                        "latency_issue": False,
                        "stability_issue": False,
                        "bandwidth_issue": False,
                        "metrics_improved_post_troubleshooting": False,
                        "escalation_required": False,
                        "escalation_ticket_id": "",
                        "resolution_summary": "Outstanding payment prevents support.",
                        "final_resolution_status": "FAILED"
                    }
        else:
            # Account is ACTIVE
            account_suspension_status = "ACTIVE"

        # At this point the account is eligible for support
        eligible_for_support = True

        # Step 6: Detect regional outage
        outage_res = manager.checkServiceAreaOutage(
            account_id=input_data["account_id"],
            session_token=session_token,
            service_area_code=input_data["service_area_code"]
        )
        outage_detected = outage_res["outage detected"]
        if outage_detected:
            # Outage found – conclude diagnostics
            return {
                "is_account_id_valid": True,
                "is_authenticated": True,
                "ticket_id": ticket_id,
                "account_status": account_status,
                "account_suspension_status": account_suspension_status,
                "eligible_for_support": True,
                "outage_detected": True,
                "diagnostic_needed": False,
                "latency_issue": False,
                "stability_issue": False,
                "bandwidth_issue": False,
                "metrics_improved_post_troubleshooting": False,
                "escalation_required": False,
                "escalation_ticket_id": "",
                "resolution_summary": f"Outage detected (ID: {outage_res['outage id']}). Issue pending resolution.",
                "final_resolution_status": "PENDING_ACTION"
            }

        # Step 7: Run initial technical diagnostics
        diag_res_initial = manager.performTechnicalDiagnostics(
            account_id=input_data["account_id"],
            session_token=session_token,
            service_type=input_data["service_type"],
            subscribed_bandwidth=input_data["subscribed_bandwidth"]
        )
        service_metrics_initial = diag_res_initial["service metrics"]
        # Expected metric keys: latency, jitter, bandwidth
        latency = float(service_metrics_initial.get("latency", 0))
        jitter = float(service_metrics_initial.get("jitter", 0))
        bandwidth = float(service_metrics_initial.get("bandwidth", 0))

        # Parse subscribed bandwidth numeric value
        subscribed_bw_str = "".join(ch for ch in input_data["subscribed_bandwidth"] if (ch.isdigit() or ch == "."))
        subscribed_bw = float(subscribed_bw_str) if subscribed_bw_str else 0

        latency_issue = latency > 100
        stability_issue = jitter > 30
        bandwidth_issue = bandwidth < subscribed_bw

        diagnostic_needed = True

        # Step 8: Execute troubleshooting based on root causes
        root_causes = diag_res_initial["root causes"]
        troubleshooting_res = manager.executeTroubleshooting(
            account_id=input_data["account_id"],
            session_token=session_token,
            root_causes=root_causes
        )
        # Updated metrics after troubleshooting (may be same shape)
        updated_metrics = troubleshooting_res["updated service metrics"]
        # Step 9: Run post‑troubleshooting diagnostics
        diag_res_post = manager.performTechnicalDiagnostics(
            account_id=input_data["account_id"],
            session_token=session_token,
            service_type=input_data["service_type"],
            subscribed_bandwidth=input_data["subscribed_bandwidth"]
        )
        service_metrics_post = diag_res_post["service metrics"]
        post_latency = float(service_metrics_post.get("latency", 0))
        post_jitter = float(service_metrics_post.get("jitter", 0))

        metrics_improved_post_troubleshooting = (
            post_latency <= 100 and post_jitter <= 30
        )

        # Determine if escalation is required
        escalation_required = not metrics_improved_post_troubleshooting

        escalation_ticket_id = ""
        escalation_summary = ""
        if escalation_required:
            escalation_res = manager.createEscalation(
                session_token=session_token,
                ticket_id=ticket_id,
                metrics_improved_post_troubleshooting=metrics_improved_post_troubleshooting,
                escalation_required=escalation_required
            )
            escalation_ticket_id = escalation_res["escalation ticket"]
            escalation_summary = f"Escalated to {escalation_res['escalation team']}."

        # Step 10: Compile resolution summary
        resolution_parts = [
            f"Account ID validated and authenticated.",
            f"Ticket ID: {ticket_id}.",
            f"Account status: {account_status}.",
            f"Suspension status: {account_suspension_status}.",
            f"Outage detected: {outage_detected}.",
            f"Initial metrics – latency: {latency} ms, jitter: {jitter} ms, bandwidth: {bandwidth} Mbps.",
            f"Identified issues – latency_issue: {latency_issue}, stability_issue: {stability_issue}, bandwidth_issue: {bandwidth_issue}.",
            f"Troubleshooting executed. Post‑troubleshoot metrics – latency: {post_latency} ms, jitter: {post_jitter} ms.",
            f"Metrics improved: {metrics_improved_post_troubleshooting}.",
        ]
        if escalation_required:
            resolution_parts.append(escalation_summary)
        resolution_summary = " ".join(resolution_parts)

        # Determine final resolution status
        if escalation_required:
            final_resolution_status = "ESCALATED"
        elif outage_detected:
            final_resolution_status = "PENDING_ACTION"
        elif metrics_improved_post_troubleshooting:
            final_resolution_status = "RESOLVED"
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
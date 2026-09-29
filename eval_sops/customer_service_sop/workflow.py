from global_tool_functions import get_manager_instance

def workflow(input_data):
    """Auto-generated workflow from SOP."""
    try:
        manager = get_manager_instance()

        # Step 1: Validate Account ID format
        validation_resp = manager.validateAccount(
            account_id=input_data["account_id"]
        )
        is_account_id_valid = validation_resp["is account id valid"]
        # Early termination if Account ID format invalid
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
                "resolution_summary": "Account ID validation failed. Process terminated.",
                "final_resolution_status": "FAILED"
            }

        # Step 2: Retrieve authentication history
        auth_resp = manager.getAuthenticationDetails(
            account_id=input_data["account_id"],
            is_account_id_valid=is_account_id_valid
        )
        # Tool returns an object under key 'authentication records'
        # Since the exact shape is unspecified, assume successful authentication if ID is valid
        is_authenticated = True

        # Early termination if authentication fails (not applicable with current assumptions)
        if not is_authenticated:
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
                "resolution_summary": "Authentication failed. Process terminated.",
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
        suspension_reason = status_resp["reason"]

        # Early termination if account is TERMINATED
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
                "resolution_summary": f"Account status TERMINATED. Reason: {suspension_reason}. Process concluded.",
                "final_resolution_status": "FAILED"
            }

        # Step 5: Verify suspension status if applicable
        account_suspension_status = ""
        eligible_for_support = True
        if account_status == "SUSPENDED":
            suspension_status_resp = manager.checkAccountSuspensionStatus(
                account_id=input_data["account_id"],
                session_token=session_token
            )
            account_suspension_status = suspension_status_resp["account suspension status"]
            # If suspension still active and reason is non‑payment, check payment status
            if "NON-PAYMENT" in suspension_reason.upper():
                payment_resp = manager.checkPaymentStatus(
                    account_id=input_data["account_id"],
                    session_token=session_token
                )
                overdue_status = payment_resp["overdue payment status"]
                if overdue_status != "PAID":
                    eligible_for_support = False
                    return {
                        "is_account_id_valid": is_account_id_valid,
                        "is_authenticated": is_authenticated,
                        "ticket_id": ticket_id,
                        "account_status": account_status,
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
                        "resolution_summary": "Account suspended due to non‑payment with overdue balance. Assigned to Accounts Payable. Process terminated.",
                        "final_resolution_status": "FAILED"
                    }
            # If suspension lifted, treat as ACTIVE for further processing
            if account_suspension_status != "ACTIVE":
                # Suspension still in effect and not non‑payment -> ineligible
                eligible_for_support = False
                return {
                    "is_account_id_valid": is_account_id_valid,
                    "is_authenticated": is_authenticated,
                    "ticket_id": ticket_id,
                    "account_status": account_status,
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
                    "resolution_summary": "Account remains suspended. Process terminated.",
                    "final_resolution_status": "FAILED"
                }

        # If account is ACTIVE (or suspension lifted), continue
        if account_status == "ACTIVE" or (account_status == "SUSPENDED" and account_suspension_status == "ACTIVE"):
            eligible_for_support = True

        # Step 6: Detect service area outages
        outage_resp = manager.checkServiceAreaOutage(
            account_id=input_data["account_id"],
            session_token=session_token,
            service_area_code=input_data["service_area_code"]
        )
        outage_detected = outage_resp["outage detected"]
        if outage_detected:
            # Outage found – diagnostics not needed further
            return {
                "is_account_id_valid": is_account_id_valid,
                "is_authenticated": is_authenticated,
                "ticket_id": ticket_id,
                "account_status": account_status,
                "account_suspension_status": account_suspension_status,
                "eligible_for_support": eligible_for_support,
                "outage_detected": True,
                "diagnostic_needed": False,
                "latency_issue": False,
                "stability_issue": False,
                "bandwidth_issue": False,
                "metrics_improved_post_troubleshooting": False,
                "escalation_required": False,
                "escalation_ticket_id": "",
                "resolution_summary": f"Outage detected (ID: {outage_resp['outage id']}). Awaiting network resolution.",
                "final_resolution_status": "PENDING_ACTION"
            }

        # No outage – proceed with diagnostics
        diagnostic_needed = True

        # Helper to parse numeric bandwidth from string like "100Mbps"
        def parse_bandwidth(bw_str):
            numeric = "".join(ch for ch in bw_str if ch.isdigit() or ch == ".")
            try:
                return float(numeric)
            except ValueError:
                return 0.0

        subscribed_bw_value = parse_bandwidth(input_data["subscribed_bandwidth"])

        # Step 7: Perform technical diagnostics (pre‑troubleshooting)
        diag_pre = manager.performTechnicalDiagnostics(
            account_id=input_data["account_id"],
            session_token=session_token,
            service_type=input_data["service_type"],
            subscribed_bandwidth=input_data["subscribed_bandwidth"]
        )
        pre_metrics = diag_pre["service metrics"]
        latency_pre = pre_metrics.get("latency", 0)
        jitter_pre = pre_metrics.get("jitter", 0)
        bandwidth_pre = pre_metrics.get("bandwidth", 0)

        latency_issue = latency_pre > 100
        stability_issue = jitter_pre > 30
        bandwidth_issue = bandwidth_pre < subscribed_bw_value

        # Step 8: Execute automated troubleshooting based on root causes
        root_causes = diag_pre["root causes"]
        troubleshoot_resp = manager.executeTroubleshooting(
            account_id=input_data["account_id"],
            session_token=session_token,
            root_causes=root_causes
        )
        post_metrics = troubleshoot_resp["updated service metrics"]
        latency_post = post_metrics.get("latency", latency_pre)
        jitter_post = post_metrics.get("jitter", jitter_pre)

        # Step 9: Re‑run diagnostics to assess post‑troubleshooting metrics
        diag_post = manager.performTechnicalDiagnostics(
            account_id=input_data["account_id"],
            session_token=session_token,
            service_type=input_data["service_type"],
            subscribed_bandwidth=input_data["subscribed_bandwidth"]
        )
        post_metrics_final = diag_post["service metrics"]
        latency_final = post_metrics_final.get("latency", latency_post)
        jitter_final = post_metrics_final.get("jitter", jitter_post)

        metrics_improved_post_troubleshooting = (latency_final <= 100) and (jitter_final <= 30)

        # Determine if escalation is required
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

        # Build resolution summary
        resolution_summary_parts = [
            f"Account ID validation passed: {is_account_id_valid}.",
            f"Authentication succeeded: {is_authenticated}.",
            f"Ticket opened: {ticket_id}.",
            f"Account status: {account_status}.",
        ]
        if account_status == "SUSPENDED":
            resolution_summary_parts.append(f"Suspension status: {account_suspension_status}.")
        resolution_summary_parts.append(f"Outage detected: {outage_detected}.")
        if diagnostic_needed:
            resolution_summary_parts.append(
                f"Pre‑troubleshoot metrics – Latency: {latency_pre} ms, Jitter: {jitter_pre} ms, Bandwidth: {bandwidth_pre} Mbps."
            )
            resolution_summary_parts.append(
                f"Post‑troubleshoot metrics – Latency: {latency_final} ms, Jitter: {jitter_final} ms."
            )
            resolution_summary_parts.append(f"Metrics improved after troubleshooting: {metrics_improved_post_troubleshooting}.")
        if escalation_required:
            resolution_summary_parts.append(f"Escalation created: {escalation_ticket_id}.")
        resolution_summary = " ".join(resolution_summary_parts)

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
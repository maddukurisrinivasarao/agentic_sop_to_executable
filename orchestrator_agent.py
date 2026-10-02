import json
import logging
import difflib
from typing import Literal
from sop_state import SOPConverterState

logger = logging.getLogger(__name__)


class OrchestratorError(Exception):
    """Custom exception for OrchestratorAgent failures."""
    pass


# ============================================================================
# AGENT 5: ORCHESTRATOR AGENT
# ============================================================================

class OrchestratorAgent:
    """
    Orchestrator that inspects the validation result and decides:
      - complete : code is valid, pipeline is done
      - retry    : issues are recoverable, regenerate
      - failed   : max retries hit or issues are unrecoverable

    Severity classification drives the retry/fail decision so transient
    LLM mistakes get a second chance while structural failures stop early.
    """

    # Issues containing these keywords are unrecoverable — no point retrying
    UNRECOVERABLE_PATTERNS = [
        "dangerous pattern",
        "syntax error",
        "missing required import",
        "missing required function",
        "unknown tool",
        "prompt injection",
    ]

    # Weights for scoring issue severity (higher = worse)
    SEVERITY_WEIGHTS = {
        "critical": 10,   # unrecoverable patterns above
        "high":      5,   # missing steps, wrong tool names
        "medium":    2,   # incorrect key extraction, missing error handling
        "low":       1,   # style, suggestions
    }

    def __call__(self, state: SOPConverterState) -> SOPConverterState:
        print("\n" + "=" * 80)
        print("🎯 ORCHESTRATOR AGENT: Making decision...")
        print("=" * 80)

        # ── 1. INPUT GUARDRAILS ───────────────────────────────────────────────
        self._validate_input(state)

        validation  = state.get("validation_result", {})
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        issues      = validation.get("issues", [])
        suggestions = validation.get("suggestions", [])

        print(f"  Retry count   : {retry_count}/{max_retries}")
        print(f"  Validation    : {'PASS' if validation.get('is_valid') else 'FAIL'}")
        print(f"  Issues        : {len(issues)}")
        print(f"  Suggestions   : {len(suggestions)}")

        # ── 2. FAST PATH — validation passed ─────────────────────────────────
        if validation.get("is_valid"):
            return self._decide(
                state,
                status="complete",
                reason="Validation passed — code is correct and safe.",
                retry_count=retry_count,
            )

        # ── 3. MAX RETRIES CHECK ──────────────────────────────────────────────
        if retry_count >= max_retries:
            return self._decide(
                state,
                status="failed",
                reason=f"Max retries ({max_retries}) reached without valid code.",
                retry_count=retry_count,
                issues=issues,
            )

        # ── 4. SEVERITY ANALYSIS ──────────────────────────────────────────────
        severity_report = self._classify_issues(issues)
        print(f"  Severity      : {severity_report['label']} "
              f"(score={severity_report['score']})")
        for item in severity_report["classified"]:
            print(f"    [{item['severity'].upper():8s}] {item['issue']}")

        # ── 5. UNRECOVERABLE CHECK ────────────────────────────────────────────
        if severity_report["has_unrecoverable"]:
            unrecoverable = [
                i["issue"] for i in severity_report["classified"]
                if i["severity"] == "critical"
            ]
            return self._decide(
                state,
                status="failed",
                reason="Unrecoverable issues detected — retrying would not help.",
                retry_count=retry_count,
                issues=unrecoverable,
            )

        # ── 6. RETRY — CHOOSE TARGET ──────────────────────────────────────────
        # Default target is the generator (the only behavior that existed
        # before this escalation logic). Escalate to schema or planner only
        # when the SAME high/critical issue already survived one generator-
        # only retry — i.e. codegen already had its shot at this exact issue
        # and didn't fix it, which is evidence the problem lives upstream
        # (a wrong/missing schema field, or a wrong plan) rather than in how
        # the code was written.
        feedback = self._build_feedback(issues, suggestions, severity_report)
        retry_target, escalation_reason = self._choose_retry_target(
            state, issues, severity_report
        )

        state["retry_feedback"]    = feedback   # CodeGeneratorAgent/SchemaAgent/PlannerAgent can read this
        state["retry_count"]       = retry_count + 1
        state["retry_target"]      = retry_target
        state["last_retry_target"] = retry_target
        state.setdefault("issue_history", []).append(list(issues))

        if retry_target == "planner":
            # Snapshot the plan that led to this escalation so PlanDiffChecker
            # can tell, after PlannerAgent re-runs, whether anything actually
            # changed before spending tokens on schema/codegen/validator again.
            state["previous_api_plan"] = state.get("api_plan")
            state["plan_retries"] = state.get("plan_retries", 0) + 1
        elif retry_target == "schema":
            state["schema_retries"] = state.get("schema_retries", 0) + 1

        print(f"  Escalation   : {escalation_reason}")

        return self._decide(
            state,
            status="retry",
            reason=(
                f"Recoverable issues found (severity={severity_report['label']}). "
                f"Attempt {retry_count + 1}/{max_retries}. {escalation_reason}"
            ),
            retry_count=retry_count + 1,
            issues=issues,
            retry_target=retry_target,
        )

    # =========================================================================
    # ESCALATION TARGET SELECTION
    # =========================================================================

    # Keyword heuristics for classifying a validation issue's likely root
    # cause, same style/spirit as SEVERITY_WEIGHTS' keyword classification.
    PLAN_SHAPE_KEYWORDS = [
        "wrong tool", "missing step", "step order", "tool name",
        "out of order", "skipped step", "wrong sequence", "extra step",
        "steps are missing",
    ]
    SCHEMA_SHAPE_KEYWORDS = [
        "parameter", "input_data", "missing field", "input schema",
        "schema", "required param",
    ]

    def _choose_retry_target(
        self,
        state: SOPConverterState,
        issues: list[str],
        severity_report: dict,
    ) -> tuple[str, str]:
        """Decide whether this retry should target generator, schema, or planner."""

        last_target = state.get("last_retry_target")
        history = state.get("issue_history", [])
        max_plan_retries = state.get("max_plan_retries", 1)
        max_schema_retries = state.get("max_schema_retries", 1)

        persisted = (
            last_target == "generator"
            and bool(history)
            and self._issues_persisted(issues, history[-1])
        )

        if not persisted:
            return "generator", "First attempt at this issue — retrying codegen."

        top_issue = self._top_issue(issues, severity_report)
        shape = self._classify_issue_shape(top_issue)

        if shape == "plan" and state.get("plan_retries", 0) < max_plan_retries:
            return (
                "planner",
                f"Issue persisted through a codegen retry and looks "
                f"plan-shaped ('{top_issue}') — escalating to planner.",
            )
        if shape == "schema" and state.get("schema_retries", 0) < max_schema_retries:
            return (
                "schema",
                f"Issue persisted through a codegen retry and looks "
                f"schema-shaped ('{top_issue}') — escalating to schema.",
            )

        return (
            "generator",
            "Issue persisted but is code-shaped (or escalation budget "
            "already spent) — retrying codegen again.",
        )

    def _issues_persisted(self, current_issues: list[str], previous_issues: list[str]) -> bool:
        """True if any current issue closely resembles any issue from last round."""
        if not current_issues or not previous_issues:
            return False
        for cur in current_issues:
            for prev in previous_issues:
                if difflib.SequenceMatcher(None, cur.lower(), prev.lower()).ratio() > 0.6:
                    return True
        return False

    def _top_issue(self, issues: list[str], severity_report: dict) -> str:
        """The most severe issue string, for shape classification."""
        for item in severity_report["classified"]:
            if item["severity"] in ("critical", "high"):
                return item["issue"]
        return issues[0] if issues else ""

    def _classify_issue_shape(self, issue_text: str) -> str:
        """Heuristic: does this issue look plan-shaped, schema-shaped, or code-shaped?"""
        text = issue_text.lower()
        if any(kw in text for kw in self.PLAN_SHAPE_KEYWORDS):
            return "plan"
        if any(kw in text for kw in self.SCHEMA_SHAPE_KEYWORDS):
            return "schema"
        return "code"

    # =========================================================================
    # INPUT GUARDRAILS
    # =========================================================================

    def _validate_input(self, state: SOPConverterState) -> None:
        """Ensure all required upstream state is present before deciding."""

        # --- validation_result ---
        validation = state.get("validation_result")
        if not isinstance(validation, dict):
            raise OrchestratorError(
                "Input guardrail: 'validation_result' must be a dict. "
                "Ensure ValidatorAgent ran successfully."
            )
        if "is_valid" not in validation:
            raise OrchestratorError(
                "Input guardrail: 'validation_result' is missing 'is_valid' key."
            )
        if not isinstance(validation["is_valid"], bool):
            raise OrchestratorError(
                "Input guardrail: 'validation_result.is_valid' must be a boolean."
            )

        # --- retry_count and max_retries ---
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        if not isinstance(retry_count, int) or retry_count < 0:
            raise OrchestratorError(
                f"Input guardrail: 'retry_count' must be a non-negative integer, "
                f"got {retry_count!r}."
            )
        if not isinstance(max_retries, int) or max_retries < 1:
            raise OrchestratorError(
                f"Input guardrail: 'max_retries' must be a positive integer, "
                f"got {max_retries!r}."
            )

        # --- generated_code still present ---
        if not state.get("generated_code"):
            raise OrchestratorError(
                "Input guardrail: 'generated_code' is missing. "
                "Ensure CodeGeneratorAgent ran successfully."
            )

        logger.info("OrchestratorAgent input validation passed.")

    # =========================================================================
    # SEVERITY CLASSIFIER
    # =========================================================================

    def _classify_issues(self, issues: list[str]) -> dict:
        """
        Classify each issue string into critical / high / medium / low severity
        and compute an aggregate score.
        """
        classified = []
        has_unrecoverable = False
        total_score = 0

        for issue in issues:
            issue_lower = issue.lower()

            if any(p in issue_lower for p in self.UNRECOVERABLE_PATTERNS):
                severity = "critical"
                has_unrecoverable = True
            elif any(kw in issue_lower for kw in [
                "missing step", "not implemented", "wrong tool", "tool name"
            ]):
                severity = "high"
            elif any(kw in issue_lower for kw in [
                "key", "extraction", "error handling", "parameter", "input_data"
            ]):
                severity = "medium"
            else:
                severity = "low"

            weight = self.SEVERITY_WEIGHTS[severity]
            total_score += weight
            classified.append({"issue": issue, "severity": severity, "weight": weight})

        # Aggregate label
        if has_unrecoverable or total_score >= 10:
            label = "CRITICAL"
        elif total_score >= 5:
            label = "HIGH"
        elif total_score >= 2:
            label = "MEDIUM"
        else:
            label = "LOW"

        return {
            "classified": classified,
            "score": total_score,
            "label": label,
            "has_unrecoverable": has_unrecoverable,
        }

    # =========================================================================
    # FEEDBACK BUILDER
    # =========================================================================

    def _build_feedback(
        self,
        issues: list[str],
        suggestions: list[str],
        severity_report: dict,
    ) -> str:
        """
        Build a concise feedback string that CodeGeneratorAgent can inject
        into its retry prompt to fix the specific problems found.
        """
        lines = ["The previous code had the following issues that must be fixed:"]

        for item in severity_report["classified"]:
            lines.append(f"  [{item['severity'].upper()}] {item['issue']}")

        if suggestions:
            lines.append("\nAdditional suggestions:")
            for s in suggestions:
                lines.append(f"  - {s}")

        lines.append(
            "\nAddress ALL issues above. Pay special attention to CRITICAL and HIGH items."
        )
        return "\n".join(lines)

    # =========================================================================
    # DECISION WRITER
    # =========================================================================

    def _decide(
        self,
        state: SOPConverterState,
        status: str,
        reason: str,
        retry_count: int,
        issues: list[str] | None = None,
        retry_target: str | None = None,
    ) -> SOPConverterState:
        """Write the orchestrator decision to state and print it."""

        decision = {
            "status":       status,
            "reason":       reason,
            "retry_count":  retry_count,
            "issues":       issues or [],
            "retry_target": retry_target,
        }

        state["status"]                = status
        state["orchestrator_decision"] = decision
        state["retry_target"]          = retry_target

        icon = {"complete": "✅", "retry": "🔄", "failed": "❌"}.get(status, "❓")
        print(f"\n  Decision: {icon} {status.upper()}")
        print(f"  Reason  : {reason}")
        if issues:
            print(f"  Issues  : {issues}")

        logger.info(f"OrchestratorAgent decision: {json.dumps(decision)}")
        return state
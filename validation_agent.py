import re
import ast
import json
import time
import logging
from typing import Optional
from client import ClientSingleton
from sop_state import SOPConverterState

logger = logging.getLogger(__name__)

REQUIRED_IMPORT   = "from global_tool_functions import execute_tool_with_structured_output"
REQUIRED_FUNCTION = "workflow"
REQUIRED_TOOL_CALL = "execute_tool_with_structured_output"
MAX_RETRIES       = 3
MAX_CODE_LINES    = 500
MIN_CODE_LINES    = 5

DANGEROUS_PATTERNS = {
    r"\beval\s*\("       : "eval()",
    r"\bexec\s*\("       : "exec()",
    r"\bos\.system\s*\(" : "os.system()",
    r"\bsubprocess\."    : "subprocess.*",
    r"\b__import__\s*\(" : "__import__()",
    r"\bopen\s*\("       : "open()",
}


class ValidatorAgentError(Exception):
    """Custom exception for ValidatorAgent failures."""
    pass


class ValidatorAgent:
    """
    Agent responsible for validating and refining generated code.
    Includes:
      - Input guardrails  (state fields + generated code sanity)
      - LLM call with retry
      - Safe JSON parsing
      - Output guardrails (validation result schema + corrected code checks)
      - AST syntax check & dangerous pattern scan on any corrected code
    """

    def __call__(self, state: SOPConverterState) -> SOPConverterState:
        print("\n" + "=" * 80)
        print("🤖 VALIDATOR AGENT: Validating code...")
        print("=" * 80)

        # ── 1. INPUT GUARDRAILS ───────────────────────────────────────────────
        self._validate_input(state)

        # ── 2. BUILD PROMPT ───────────────────────────────────────────────────
        prompt = self._build_prompt(state)
        messages = [
            {"role": "system", "content": "You are an expert code reviewer and validator."},
            {"role": "user",   "content": prompt},
        ]

        # ── 3. LLM CALL WITH RETRY ────────────────────────────────────────────
        response = self._call_with_retry(messages)

        # ── 4. SAFE JSON PARSING ──────────────────────────────────────────────
        validation = self._parse_response(response)

        # ── 5. OUTPUT GUARDRAILS (validation result schema) ───────────────────
        validation = self._validate_result_schema(validation)

        # ── 6. RESOLVE FINAL CODE ─────────────────────────────────────────────
        final_code = self._resolve_final_code(validation, state)

        # ── 7. COMMIT TO STATE ────────────────────────────────────────────────
        state["validation_result"] = validation
        state["final_code"]        = final_code
        state["status"]            = "complete" if validation["is_valid"] else "validating"

        self._print_summary(validation)
        return state

    # =========================================================================
    # INPUT GUARDRAILS
    # =========================================================================

    def _validate_input(self, state: SOPConverterState) -> None:
        """Validate all upstream state before touching the LLM."""

        # --- generated_code ---
        code = state.get("generated_code")
        if not code or not isinstance(code, str) or not code.strip():
            raise ValidatorAgentError(
                "Input guardrail: 'generated_code' is missing or empty. "
                "Ensure CodeGeneratorAgent ran successfully."
            )

        lines = code.splitlines()
        if len(lines) < MIN_CODE_LINES:
            raise ValidatorAgentError(
                f"Input guardrail: generated_code is suspiciously short "
                f"({len(lines)} lines, minimum {MIN_CODE_LINES})."
            )
        if len(lines) > MAX_CODE_LINES:
            raise ValidatorAgentError(
                f"Input guardrail: generated_code exceeds maximum length "
                f"({len(lines)} lines, maximum {MAX_CODE_LINES})."
            )

        # Syntax-check before sending to LLM — no point reviewing broken code
        try:
            ast.parse(code)
        except SyntaxError as exc:
            raise ValidatorAgentError(
                f"Input guardrail: generated_code has a syntax error — fix "
                f"CodeGeneratorAgent first.\nLine {exc.lineno}: {exc.text}"
            )

        # --- api_plan ---
        api_plan = state.get("api_plan")
        if not isinstance(api_plan, list) or not api_plan:
            raise ValidatorAgentError(
                "Input guardrail: 'api_plan' is missing or empty. "
                "Ensure PlannerAgent ran successfully."
            )

        # --- input_schema ---
        input_schema = state.get("input_schema")
        if not isinstance(input_schema, list) or not input_schema:
            raise ValidatorAgentError(
                "Input guardrail: 'input_schema' is missing or empty. "
                "Ensure SchemaAgent ran successfully."
            )

        logger.info("ValidatorAgent input validation passed.")

    # =========================================================================
    # PROMPT BUILDER
    # =========================================================================

    def _build_prompt(self, state: SOPConverterState) -> str:
        expected_tools = [step["tool"] for step in state["api_plan"]]
        param_names    = [p["name"] for p in state["input_schema"]]

        return f"""Review this generated Python workflow code for correctness and best practices.

Generated Code:
```python
{state['generated_code']}
```

API Plan:
{json.dumps(state['api_plan'], indent=2)}

Input Schema:
{json.dumps(state['input_schema'], indent=2)}

Check ALL of the following:
1. Every step in the API plan is implemented in the code
2. Only these tools are used (verbatim): {expected_tools}
3. Every tool is called via execute_tool_with_structured_output(tool_name, tool_input)
4. Output values are extracted with correct key names from each tool's result dict
5. Only these input_data keys are accessed: {param_names}
6. try/except block is present and returns {{"error": str(e), "status": "failed"}}
7. The function is named exactly 'workflow' and accepts a single dict argument
8. First line is: from global_tool_functions import execute_tool_with_structured_output
9. No dangerous calls: eval, exec, os.system, subprocess, open, __import__
10. Logical execution order matches the SOP dependencies

Return ONLY a JSON object with this exact schema:
{{
  "is_valid": true,
  "issues": [],
  "suggestions": [],
  "corrected_code": null
}}

Rules:
- "is_valid": boolean — true only if code is correct and safe as-is
- "issues": array of strings — every problem found; empty array if none
- "suggestions": array of strings — improvements even if code is valid; empty array if none
- "corrected_code": string with the full corrected Python code if is_valid is false, else null
- Return ONLY the JSON object — no markdown fences, no explanation"""

    # =========================================================================
    # LLM CALL WITH RETRY
    # =========================================================================

    def _call_with_retry(self, messages: list) -> object:
        last_exc: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    f"ValidatorAgent LLM call attempt {attempt}/{MAX_RETRIES}"
                )
                response = ClientSingleton.execute(messages)
                if not response or not hasattr(response, "content"):
                    raise ValidatorAgentError(
                        "LLM returned empty or malformed response."
                    )
                if not isinstance(response.content, str) or not response.content.strip():
                    raise ValidatorAgentError("LLM response content is blank.")
                return response

            except ValidatorAgentError:
                raise
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    f"ValidatorAgent LLM call failed (attempt {attempt}): "
                    f"{exc}. Retrying in {wait}s..."
                )
                time.sleep(wait)

        raise ValidatorAgentError(
            f"LLM call failed after {MAX_RETRIES} attempts. Last error: {last_exc}"
        )

    # =========================================================================
    # SAFE JSON PARSING
    # =========================================================================

    def _parse_response(self, response) -> dict:
        """Robustly extract a JSON object from the LLM response."""
        raw = response.content.strip()

        # Strip markdown fences
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"```$", "", raw).strip()

        # Direct parse
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fallback: extract first {...} block
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError as exc:
                raise ValidatorAgentError(
                    f"Parse guardrail: Found JSON object but could not decode it: {exc}\n"
                    f"Raw snippet: {json_match.group(0)[:300]}"
                )

        raise ValidatorAgentError(
            f"Parse guardrail: No JSON object found in LLM response.\n"
            f"Response (first 500 chars): {raw[:500]}"
        )

    # =========================================================================
    # OUTPUT GUARDRAILS — validation result schema
    # =========================================================================

    def _validate_result_schema(self, validation: dict) -> dict:
        """Validate the structure of the LLM's validation result."""

        # --- Required keys ---
        required_keys = {"is_valid", "issues", "suggestions", "corrected_code"}
        missing = required_keys - validation.keys()
        if missing:
            raise ValidatorAgentError(
                f"Output guardrail: Validation result missing keys: {missing}"
            )

        # --- is_valid: must be boolean ---
        if not isinstance(validation["is_valid"], bool):
            # Attempt lenient coercion
            raw_val = validation["is_valid"]
            if isinstance(raw_val, str) and raw_val.lower() in ("true", "false"):
                validation["is_valid"] = raw_val.lower() == "true"
                logger.warning(
                    f"Output guardrail: Coerced 'is_valid' from string '{raw_val}' to bool."
                )
            else:
                raise ValidatorAgentError(
                    f"Output guardrail: 'is_valid' must be a boolean, got {type(raw_val)}."
                )

        # --- issues: must be a list of strings ---
        if not isinstance(validation["issues"], list):
            raise ValidatorAgentError(
                "Output guardrail: 'issues' must be a list."
            )
        validation["issues"] = [
            str(i).strip() for i in validation["issues"] if str(i).strip()
        ]

        # --- suggestions: must be a list of strings ---
        if not isinstance(validation["suggestions"], list):
            raise ValidatorAgentError(
                "Output guardrail: 'suggestions' must be a list."
            )
        validation["suggestions"] = [
            str(s).strip() for s in validation["suggestions"] if str(s).strip()
        ]

        # --- Consistency: if is_valid=false, issues must be non-empty ---
        if not validation["is_valid"] and not validation["issues"]:
            raise ValidatorAgentError(
                "Output guardrail: 'is_valid' is false but 'issues' is empty. "
                "The LLM must specify what is wrong."
            )

        # --- Consistency: if is_valid=true, corrected_code should be null ---
        if validation["is_valid"] and validation.get("corrected_code"):
            logger.warning(
                "Output guardrail: 'is_valid' is true but 'corrected_code' is present. "
                "Ignoring corrected_code — original code will be used."
            )
            validation["corrected_code"] = None

        logger.info("ValidatorAgent result schema validation passed.")
        return validation

    # =========================================================================
    # RESOLVE FINAL CODE
    # =========================================================================

    def _resolve_final_code(self, validation: dict, state: SOPConverterState) -> str:
        """
        Decide which code becomes final_code and run full safety checks on it.
        - is_valid=true              → use generated_code as-is
        - is_valid=false + correction → validate & use corrected_code
        """
        if validation["is_valid"]:
            logger.info("Code passed validation — using generated_code as final.")
            return state["generated_code"]

        corrected = validation.get("corrected_code")
        if corrected and isinstance(corrected, str) and corrected.strip():
            logger.info("Validation failed — running guardrails on corrected_code.")
            return self._validate_corrected_code(corrected.strip(), state)

        # No correction provided — warn and fall back
        logger.warning(
            "Validation failed and no corrected_code provided. "
            "Falling back to original generated_code."
        )
        return state["generated_code"]

    def _validate_corrected_code(self, code: str, state: SOPConverterState) -> str:
        """Run the same structural + safety checks on corrected_code as CodeGeneratorAgent would."""

        lines = code.splitlines()

        # --- Length bounds ---
        if len(lines) < MIN_CODE_LINES:
            raise ValidatorAgentError(
                f"Corrected code guardrail: Too short ({len(lines)} lines, "
                f"minimum {MIN_CODE_LINES})."
            )
        if len(lines) > MAX_CODE_LINES:
            raise ValidatorAgentError(
                f"Corrected code guardrail: Too long ({len(lines)} lines, "
                f"maximum {MAX_CODE_LINES})."
            )

        # --- Required import ---
        if REQUIRED_IMPORT not in code:
            raise ValidatorAgentError(
                f"Corrected code guardrail: Missing required import.\n"
                f"Expected: {REQUIRED_IMPORT}"
            )

        # --- Required function ---
        if not re.search(r"def\s+workflow\s*\(", code):
            raise ValidatorAgentError(
                "Corrected code guardrail: Missing 'def workflow(' function definition."
            )

        # --- Required tool call pattern ---
        if REQUIRED_TOOL_CALL not in code:
            raise ValidatorAgentError(
                f"Corrected code guardrail: Missing '{REQUIRED_TOOL_CALL}' calls."
            )

        # --- try/except ---
        if "try:" not in code or "except" not in code:
            raise ValidatorAgentError(
                "Corrected code guardrail: Missing try/except block."
            )

        # --- AST syntax check ---
        try:
            ast.parse(code)
            logger.info("Corrected code guardrail: AST syntax check passed.")
        except SyntaxError as exc:
            raise ValidatorAgentError(
                f"Corrected code guardrail: Syntax error in corrected code: {exc}\n"
                f"Line {exc.lineno}: {exc.text}"
            )

        # --- Dangerous patterns ---
        for pattern, label in DANGEROUS_PATTERNS.items():
            if re.search(pattern, code):
                raise ValidatorAgentError(
                    f"Corrected code guardrail: Dangerous pattern '{label}' "
                    f"in corrected code."
                )

        # --- Tool name whitelist ---
        expected_tools = {step["tool"] for step in state.get("api_plan", [])}
        used_tools = set(re.findall(r'tool_name\s*=\s*["\']([^"\']+)["\']', code))
        unknown = used_tools - expected_tools
        if unknown:
            raise ValidatorAgentError(
                f"Corrected code guardrail: Unknown tools in corrected code: {unknown}. "
                f"Expected: {expected_tools}"
            )

        # --- Input key whitelist (warn only) ---
        schema_names = {p["name"] for p in state.get("input_schema", [])}
        used_keys = set(re.findall(r'input_data\s*\[\s*["\']([^"\']+)["\']\s*\]', code))
        unknown_keys = used_keys - schema_names
        if unknown_keys:
            logger.warning(
                f"Corrected code guardrail: Accessing undeclared input_data keys: "
                f"{unknown_keys}. Schema keys: {schema_names}"
            )

        logger.info(
            f"Corrected code guardrail: All checks passed ({len(lines)} lines)."
        )
        return code

    # =========================================================================
    # SUMMARY PRINTER
    # =========================================================================

    def _print_summary(self, validation: dict) -> None:
        if validation["is_valid"]:
            print("✓ Code validation passed")
        else:
            issues = validation.get("issues", [])
            print(f"⚠️  Found {len(issues)} issue(s):")
            for issue in issues:
                print(f"   - {issue}")

        suggestions = validation.get("suggestions", [])
        if suggestions:
            print(f"💡 {len(suggestions)} suggestion(s):")
            for s in suggestions:
                print(f"   - {s}")

        corrected = validation.get("corrected_code")
        if corrected:
            print("✓ Corrected code accepted and validated")
        elif not validation["is_valid"]:
            print("⚠️  No corrected code provided — falling back to original")
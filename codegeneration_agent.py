import re
import ast
import time
import logging
from typing import Optional
from client import ClientSingleton
from sop_state import SOPConverterState

logger = logging.getLogger(__name__)

REQUIRED_IMPORT = "from global_tool_functions import execute_tool_with_structured_output"
REQUIRED_FUNCTION = "workflow"
REQUIRED_TOOL_CALL = "execute_tool_with_structured_output"
MAX_RETRIES = 3
MAX_CODE_LINES = 500
MIN_CODE_LINES = 5


class CodeGeneratorAgentError(Exception):
    """Custom exception for CodeGeneratorAgent failures."""
    pass


class CodeGeneratorAgent:
    """
    Agent responsible for generating executable Python code.
    Includes input validation, output validation, syntax checking, and retry logic.
    """

    def __call__(self, state: SOPConverterState) -> SOPConverterState:
        print("\n" + "=" * 80)
        print("🤖 CODE GENERATOR AGENT: Generating Python code...")
        print("=" * 80)

        # ── 1. INPUT GUARDRAILS ───────────────────────────────────────────────
        self._validate_input(state)

        # ── 2. BUILD PROMPT ───────────────────────────────────────────────────
        prompt = self._build_prompt(state)
        messages = [
            {"role": "system", "content": "You are an expert Python code generator specializing in workflow automation."},
            {"role": "user",   "content": prompt},
        ]

        # ── 3. LLM CALL WITH RETRY ────────────────────────────────────────────
        response = self._call_with_retry(messages)

        # ── 4. SAFE EXTRACTION ────────────────────────────────────────────────
        code = self._extract_code(response)

        # ── 5. OUTPUT GUARDRAILS ──────────────────────────────────────────────
        code = self._validate_output(code, state)

        # ── 6. COMMIT TO STATE ────────────────────────────────────────────────
        line_count = len(code.splitlines())
        print(f"✓ Generated {line_count} lines of code")

        state["generated_code"] = code
        state["status"] = "generating"
        return state

    # =========================================================================
    # INPUT GUARDRAILS
    # =========================================================================

    def _validate_input(self, state: SOPConverterState) -> None:
        """Validate all upstream state fields before touching the LLM."""

        # --- SOP ---
        sop = state.get("sop")
        if not sop or not isinstance(sop, str) or not sop.strip():
            raise CodeGeneratorAgentError(
                "Input guardrail: 'sop' must be a non-empty string."
            )

        # --- api_plan: non-empty list with required keys ---
        api_plan = state.get("api_plan")
        if not isinstance(api_plan, list) or not api_plan:
            raise CodeGeneratorAgentError(
                "Input guardrail: 'api_plan' is missing or empty. "
                "Ensure PlannerAgent ran successfully."
            )

        # --- input_schema: non-empty list with required keys ---
        input_schema = state.get("input_schema")
        if not isinstance(input_schema, list) or not input_schema:
            raise CodeGeneratorAgentError(
                "Input guardrail: 'input_schema' is missing or empty. "
                "Ensure SchemaAgent ran successfully."
            )
        for i, param in enumerate(input_schema):
            if not isinstance(param, dict):
                raise CodeGeneratorAgentError(
                    f"Input guardrail: input_schema[{i}] is not a dict."
                )
            for key in ("name", "type", "required", "description"):
                if key not in param:
                    raise CodeGeneratorAgentError(
                        f"Input guardrail: input_schema[{i}] missing key '{key}'."
                    )

        # --- tools_formatted ---
        tools_formatted = state.get("tools_formatted")
        if not tools_formatted or not isinstance(tools_formatted, str):
            raise CodeGeneratorAgentError(
                "Input guardrail: 'tools_formatted' must be a non-empty string."
            )

        # --- Prompt injection check on SOP ---
        injection_markers = [
            "ignore previous instructions",
            "ignore all instructions",
            "disregard the above",
            "forget everything",
            "you are now",
        ]
        for marker in injection_markers:
            if marker in sop.lower():
                raise CodeGeneratorAgentError(
                    f"Input guardrail: Potential prompt injection in SOP: '{marker}'."
                )

        logger.info("CodeGeneratorAgent input validation passed.")

    # =========================================================================
    # PROMPT BUILDER
    # =========================================================================

    def _build_prompt(self, state: SOPConverterState) -> str:
        param_names = [p["name"] for p in state["input_schema"]]
        tool_names  = [step["tool"] for step in state["api_plan"]]

        return f"""Generate executable Python code for this workflow.

SOP:
{state['sop']}

API Plan:
{json.dumps(state['api_plan'], indent=2)}

Input Parameters:
{json.dumps(state['input_schema'], indent=2)}

Available Tools:
{state['tools_formatted']}

CRITICAL REQUIREMENTS:
1. First line must be: from global_tool_functions import execute_tool_with_structured_output
2. ALWAYS call execute_tool_with_structured_output(tool_name, tool_input) — never call tools directly
3. Create a function named exactly 'workflow' that accepts a single dict argument named 'input_data'
4. Access inputs ONLY from these keys: {param_names}
5. Use ONLY these tool names (verbatim): {tool_names}
6. Extract results from the returned dict using the correct key names
7. Wrap the entire body in try/except — catch Exception as e and return {{"error": str(e), "status": "failed"}}
8. Add a descriptive comment above every step
9. Return the final result as the last statement inside try
10. Return ONLY raw Python code — no markdown fences, no explanation

TEMPLATE:
from global_tool_functions import execute_tool_with_structured_output

def workflow(input_data):
    \"\"\"Auto-generated workflow from SOP.\"\"\"
    try:
        # Step 1: <description>
        result1 = execute_tool_with_structured_output(
            tool_name="toolName",
            tool_input={{
                "param1": input_data["param1"],
            }}
        )
        value1 = result1["output_key"]

        # ... continue for all steps ...

        return final_result

    except Exception as e:
        return {{"error": str(e), "status": "failed"}}

Maximum {MAX_CODE_LINES} lines."""

    # =========================================================================
    # LLM CALL WITH RETRY
    # =========================================================================

    def _call_with_retry(self, messages: list) -> object:
        last_exc: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    f"CodeGeneratorAgent LLM call attempt {attempt}/{MAX_RETRIES}"
                )
                response = ClientSingleton.execute(messages)
                if not response or not hasattr(response, "content"):
                    raise CodeGeneratorAgentError(
                        "LLM returned empty or malformed response."
                    )
                if not isinstance(response.content, str) or not response.content.strip():
                    raise CodeGeneratorAgentError("LLM response content is blank.")
                return response

            except CodeGeneratorAgentError:
                raise
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    f"CodeGeneratorAgent LLM call failed (attempt {attempt}): "
                    f"{exc}. Retrying in {wait}s..."
                )
                time.sleep(wait)

        raise CodeGeneratorAgentError(
            f"LLM call failed after {MAX_RETRIES} attempts. Last error: {last_exc}"
        )

    # =========================================================================
    # SAFE CODE EXTRACTION
    # =========================================================================

    def _extract_code(self, response) -> str:
        """Strip markdown fences and return clean Python code."""
        raw = response.content.strip()

        # Strip ```python ... ``` or ``` ... ```
        fenced = re.search(r"```(?:python)?\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
        if fenced:
            return fenced.group(1).strip()

        # No fences — return as-is
        return raw

    # =========================================================================
    # OUTPUT GUARDRAILS
    # =========================================================================

    def _validate_output(self, code: str, state: SOPConverterState) -> str:
        """Validate and sanitize generated code before writing to state."""

        if not code or not code.strip():
            raise CodeGeneratorAgentError(
                "Output guardrail: Generated code is empty."
            )

        lines = code.splitlines()

        # --- Line count bounds ---
        if len(lines) < MIN_CODE_LINES:
            raise CodeGeneratorAgentError(
                f"Output guardrail: Code is suspiciously short ({len(lines)} lines). "
                f"Minimum is {MIN_CODE_LINES}."
            )
        if len(lines) > MAX_CODE_LINES:
            raise CodeGeneratorAgentError(
                f"Output guardrail: Code exceeds maximum length "
                f"({len(lines)} > {MAX_CODE_LINES} lines)."
            )

        # --- Required import ---
        if REQUIRED_IMPORT not in code:
            raise CodeGeneratorAgentError(
                f"Output guardrail: Missing required import.\n"
                f"Expected: {REQUIRED_IMPORT}"
            )

        # --- Required function definition ---
        if not re.search(r"def\s+workflow\s*\(", code):
            raise CodeGeneratorAgentError(
                "Output guardrail: Missing required function 'workflow'. "
                "The generated code must define 'def workflow(input_data)'."
            )

        # --- Required tool call pattern ---
        if REQUIRED_TOOL_CALL not in code:
            raise CodeGeneratorAgentError(
                f"Output guardrail: Missing required tool call pattern "
                f"'{REQUIRED_TOOL_CALL}'. Tools must not be called directly."
            )

        # --- try/except present ---
        if "try:" not in code or "except" not in code:
            raise CodeGeneratorAgentError(
                "Output guardrail: Generated code is missing try/except error handling."
            )

        # --- Syntax check via AST parse ---
        try:
            ast.parse(code)
            logger.info("Output guardrail: AST syntax check passed.")
        except SyntaxError as exc:
            raise CodeGeneratorAgentError(
                f"Output guardrail: Generated code has a syntax error: {exc}\n"
                f"Line {exc.lineno}: {exc.text}"
            )

        # --- Dangerous built-in check ---
        self._check_dangerous_patterns(code)

        # --- Tool name whitelist ---
        self._check_tool_names(code, state)

        # --- Input key whitelist ---
        self._check_input_keys(code, state)

        logger.info(f"CodeGeneratorAgent output validation passed: {len(lines)} lines.")
        return code.strip()

    def _check_dangerous_patterns(self, code: str) -> None:
        """
        Reject code containing dangerous built-ins or shell calls.
        Protects against prompt-injected malicious code generation.
        """
        dangerous = {
            r"\beval\s*\("        : "eval()",
            r"\bexec\s*\("        : "exec()",
            r"\bos\.system\s*\("  : "os.system()",
            r"\bsubprocess\."     : "subprocess.*",
            r"\b__import__\s*\("  : "__import__()",
            r"\bopen\s*\("        : "open()  — file I/O not allowed in generated workflow",
        }
        for pattern, label in dangerous.items():
            if re.search(pattern, code):
                raise CodeGeneratorAgentError(
                    f"Output guardrail: Dangerous pattern detected in generated code: '{label}'. "
                    f"This may indicate prompt injection via the SOP."
                )

    def _check_tool_names(self, code: str, state: SOPConverterState) -> None:
        """Verify every tool name passed to execute_tool_with_structured_output is in the plan."""
        expected_tools = {step["tool"] for step in state.get("api_plan", [])}
        if not expected_tools:
            return

        # Find all tool_name="..." values in the generated code
        used_tools = set(re.findall(r'tool_name\s*=\s*["\']([^"\']+)["\']', code))
        unknown = used_tools - expected_tools
        if unknown:
            raise CodeGeneratorAgentError(
                f"Output guardrail: Generated code references unknown tools: {unknown}. "
                f"Expected tools from plan: {expected_tools}"
            )

    def _check_input_keys(self, code: str, state: SOPConverterState) -> None:
        """Warn if generated code accesses input_data keys not in the schema."""
        schema_names = {p["name"] for p in state.get("input_schema", [])}
        if not schema_names:
            return

        # Find all input_data["..."] or input_data['...'] accesses
        used_keys = set(re.findall(r'input_data\s*\[\s*["\']([^"\']+)["\']\s*\]', code))
        unknown_keys = used_keys - schema_names
        if unknown_keys:
            # Warn rather than hard-fail — LLM may access derived keys legitimately
            logger.warning(
                f"Output guardrail: Generated code accesses input_data keys not in schema: "
                f"{unknown_keys}. Schema keys: {schema_names}. Review before execution."
            )
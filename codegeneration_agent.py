import re
import ast
import time
import json
import logging
from typing import Optional
from client import ClientSingleton
from sop_state import SOPConverterState

logger = logging.getLogger(__name__)

REQUIRED_IMPORT = "from global_tool_functions import get_manager_instance"
REQUIRED_FUNCTION = "workflow"
REQUIRED_MANAGER_CALL = "get_manager_instance()"
ALLOWED_IMPORT_MODULES = {"global_tool_functions"}
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
        required    = [p["name"] for p in state["input_schema"] if p.get("required")]
        optional    = [p["name"] for p in state["input_schema"] if not p.get("required")]
        tool_names  = [step["tool"] for step in state["api_plan"]]

        # OrchestratorAgent writes retry_feedback specifically so this prompt
        # can fix the issues that were actually found last attempt, instead
        # of blindly regenerating from the same inputs and hoping a
        # different sample happens to avoid them.
        feedback_section = ""
        retry_feedback = state.get("retry_feedback")
        if retry_feedback:
            previous_code = state.get("generated_code", "")
            # Embedding the full previous attempt is only safe for small
            # workflows. For larger domains (many tool steps -> hundreds of
            # lines) this alone can push the retry prompt over Groq's 8000
            # TPM limit, causing every retry to 413 before the model ever
            # sees the feedback (customer_service_sop, 10 tools, hit this
            # on 3 consecutive retries: 9498/9981/9132/9267 tokens
            # requested). Past this size, drop the code and rely on the
            # feedback text plus the SOP/plan/tools already in this same
            # prompt — the model can reconstruct correct code from those
            # without needing its own prior (flawed) draft verbatim.
            MAX_PREVIOUS_CODE_CHARS = 4000
            if len(previous_code) > MAX_PREVIOUS_CODE_CHARS:
                feedback_section = f"""
RETRY — YOUR PREVIOUS ATTEMPT FAILED VALIDATION:
{retry_feedback}

Your previous attempt was too long to include here again — fix every issue
listed above using the SOP, API plan, and tool docs below; don't repeat the
same mistakes.
"""
            else:
                feedback_section = f"""
RETRY — YOUR PREVIOUS ATTEMPT FAILED VALIDATION:
{retry_feedback}

Your previous code (fix its specific issues above — don't just rewrite from
scratch and hope the same mistake doesn't recur):
```python
{previous_code}
```
"""

        return f"""Generate executable Python code for this workflow.

SOP:
{state['sop']}

API Plan:
{json.dumps(state['api_plan'], indent=2)}

Input Parameters:
{json.dumps(state['input_schema'], indent=2)}

CRITICAL — INPUT DATA KEYS:
You MUST access input_data using ONLY these exact key names:
  Required : {required}
  Optional : {optional}

Available Tools:
{state['tools_formatted']}
{feedback_section}
CRITICAL REQUIREMENTS:
1. First line: from global_tool_functions import get_manager_instance
2. Call get_manager_instance() ONCE; call each tool directly as manager.toolName(...) — never via a generic string dispatcher
3. Function named exactly 'workflow', one dict argument 'input_data'
4. Access inputs ONLY from these keys: {param_names}
5. Use ONLY these tool names (verbatim), as manager.<toolName>(...): {tool_names}
6. Tool parameters are keyword arguments matching the tool's documented parameter names
7. Wrap the whole body in try/except — catch Exception as e, return {{"error": str(e), "status": "failed"}}
8. A descriptive comment above every step
9. FINAL RETURN MUST COMBINE EVERY STEP'S RESULT, NOT JUST THE LAST CALL: one dict with a key for every field the SOP's Output section names, mapped from whichever step/variable computed it (including values only used to feed a later step) — before writing it, list the SOP's Output fields and match each to its source; fewer keys than the SOP lists is almost always a bug.
10. Return ONLY raw Python code — no markdown fences, no explanation
11. No imports besides get_manager_instance from global_tool_functions
12. CROSS-STEP PARAMETERS: a tool parameter absent from input_data must come from an earlier step's return, using that field's EXACT name per that step's tool's "Returns:" — the producer's field name and the consumer's parameter name can differ, map them explicitly rather than assuming they match.
13. TYPE SAFETY ON CHAINED VALUES: never `.get()`/index into a previous step's return or an input_data field without knowing its type. Only treat a return as a dict if its "Returns:" documents named fields; if undocumented or scalar-shaped, use it directly as a scalar. An input_data array field may already be a real list/dict — don't `.get()` it as if it were a tool response.
14. DECISION LOGIC FOLLOWS NAMED CONDITIONS, NOT A SHORTCUT: implement each condition the SOP names for a decision/status field as its own explicit check on the specific field named — don't collapse several into one threshold/default unless told to. Individual trigger conditions are often stated inline in earlier, unrelated-looking sections ("if ID format invalid, escalate"), not restated in the section that makes the final call — read the WHOLE SOP for "if <condition>, <status>" sentences before writing the branching, not just the decision section. If the SOP calls a score unreliable, don't base the decision on it alone.
15. OUTPUT VALUES USE THE SOP'S OWN TERMINOLOGY: when the SOP names output values as a compound phrase (e.g. "the Hazard Class A, B, C and D" — the names ARE "Hazard Class A" etc., not bare "A"), output that fuller phrasing, not just the varying part — a later short parenthetical naming which variant applies isn't redefining the format.
16. OUTPUT DICT KEYS ARE FLAT, SHORT, CANONICAL NAMES — NOT OUTPUT-SECTION PROSE: don't turn a prose deliverable description ("Final hazard class designation") into a key (`final_hazard_class_designation`) or nest it in a sub-dict — use the short name used elsewhere (SOP body, tool Parameters/Returns, or your own variable, e.g. `hazard_class`) at the top level.
17. NEVER BRANCH ON A KEY ABSENT FROM A TOOL'S DOCUMENTED "Returns:": don't invent a plausible generic key like `.get("status")` — if the signal is nested (e.g. a list of {{name, status}} objects), read it from there. A check on a key that's never present just silently never fires, with no error.
18. DON'T REUSE ONE FIELD'S COMPARISON ON A DIFFERENT FIELD, EVEN IF SAME SHAPE: two fields can share a shape (both lists of {{name, status}}) with different value vocabularies (Clear/Pending/Matched vs. Yes/No) — check each field's own "Returns:" values before comparing, don't copy a check onto a similar-looking sibling a few lines later.
19. VERIFY EVERY TOOL CALL AGAINST ITS OWN FULL "Parameters:" LIST: after each `manager.<toolName>(...)` call, confirm every required parameter is passed, including ones taken straight from input_data. The SOP's prose naming one input ("using the validated product_id") names the key input for a reader, not an exhaustive parameter list — the tool's own "Parameters:" is always authoritative regardless of the SOP's phrasing.
20. CLASSIFYING FREE TEXT (e.g. email intent): don't gate a category on one exact phrase — match several plausible phrasings/synonyms per category, since real text paraphrases the SOP's wording ("isn't listed yet" vs. "not listed").
21. IF THE SOP SAYS "REGULAR EXPRESSIONS"/"PATTERN MATCHING", DO NOT IMPORT `re` (not whitelisted, rule 11) — implement the same check with `.startswith()`/`.split()`/slicing/`.isdigit()`/`.isalnum()` etc.; every fixed-format pattern is expressible this way.

TEMPLATE:
from global_tool_functions import get_manager_instance

def workflow(input_data):
    \"\"\"Auto-generated workflow from SOP.\"\"\"
    try:
        manager = get_manager_instance()

        # Step 1: <description>
        value1 = manager.toolName(
            param1=input_data["param1"],
        )

        # Step 2: <description> — value1 came from Step 1; extract the exact
        # field name Step 1's tool documents under "Returns:", then pass it
        # under whatever name Step 2's tool documents under "Parameters:"
        value2 = manager.otherTool(
            producer_field_mapped_to_consumer_param=value1["exact_returned_field_name"],
        )

        # ... continue for all steps ...

        # Combine every step's result the SOP's Output section names as a
        # field — not just the last tool call's return value.
        return {{
            "field_name_from_sop_output_section": value1,
            "another_field_from_sop_output_section": value2,
            # ... one key per SOP output field, however many steps that spans ...
        }}

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
                # Higher than the client default: generated code can run up
                # to MAX_CODE_LINES=500 in validation_agent.py. Tried 3000
                # (truncated customer_service_sop's 10-tool workflow), then
                # 3500 (still truncated it on one run) — no value under 4000
                # reliably avoids truncation for this domain, and 4000 makes
                # retries land right at Groq's 8000 TPM ceiling
                # (8331-9329 requested, sometimes clears on retry, sometimes
                # doesn't). Truncation is the harder failure (guaranteed
                # rejection, not just a maybe-blocked request), so 4000
                # stays — see program.md/sop_autoresearch.md for the actual
                # fix this domain needs (fewer tools per generation, or a
                # bigger-TPM provider/tier), which prompt tuning alone can't
                # solve.
                response = ClientSingleton.execute(messages, max_tokens=4000)
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

        # --- Required manager call pattern ---
        if REQUIRED_MANAGER_CALL not in code:
            raise CodeGeneratorAgentError(
                f"Output guardrail: Missing required call pattern "
                f"'{REQUIRED_MANAGER_CALL}'."
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

        # --- Import whitelist ---
        self._check_imports(code)

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

    def _check_imports(self, code: str) -> None:
        """Only allow importing from global_tool_functions — no direct tools.py or module access."""
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root not in ALLOWED_IMPORT_MODULES:
                        raise CodeGeneratorAgentError(
                            f"Output guardrail: Disallowed import '{alias.name}'. "
                            f"Only {ALLOWED_IMPORT_MODULES} may be imported."
                        )
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root not in ALLOWED_IMPORT_MODULES:
                    raise CodeGeneratorAgentError(
                        f"Output guardrail: Disallowed import from '{node.module}'. "
                        f"Only {ALLOWED_IMPORT_MODULES} may be imported."
                    )

    def _check_tool_names(self, code: str, state: SOPConverterState) -> None:
        """Verify every method called on the manager instance is a planned tool."""
        expected_tools = {step["tool"] for step in state.get("api_plan", [])}
        if not expected_tools:
            return

        tree = ast.parse(code)

        # Find variables assigned directly from get_manager_instance()
        manager_vars = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Name) and func.id == "get_manager_instance":
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            manager_vars.add(target.id)

        if not manager_vars:
            raise CodeGeneratorAgentError(
                "Output guardrail: No variable assigned from get_manager_instance()."
            )

        # Find every manager.<method>(...) call
        used_tools = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in manager_vars
            ):
                used_tools.add(node.func.attr)

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
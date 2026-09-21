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
1. First line must be: from global_tool_functions import get_manager_instance
2. Call get_manager_instance() ONCE to get the tool manager, then invoke each tool as a direct method call on it — e.g. manager.toolName(param1=...) — never through a generic string dispatcher
3. Create a function named exactly 'workflow' that accepts a single dict argument named 'input_data'
4. Access inputs ONLY from these keys: {param_names}
5. Use ONLY these tool method names (verbatim), called as manager.<toolName>(...): {tool_names}
6. Pass tool parameters as keyword arguments matching the tool's documented parameter names
7. Wrap the entire body in try/except — catch Exception as e and return {{"error": str(e), "status": "failed"}}
8. Add a descriptive comment above every step
9. RETURN VALUE MUST COMBINE EVERY STEP'S RESULT, NOT JUST THE LAST ONE: the final `return` inside `try` must be a dict with one key per step whose output is a named field the SOP's Output/results section asks for — not the bare return value of only the last tool call. Every intermediate variable you computed (including ones only used to feed a later step's parameters) still needs to appear in this final dict if the SOP lists it as an output field. Before writing the return statement, list every field the SOP's Output section names and map each one to the step/variable that produced it — a return statement with fewer keys than the SOP's Output section lists is almost always a bug.
10. Return ONLY raw Python code — no markdown fences, no explanation
11. Do not import anything other than get_manager_instance from global_tool_functions — no other modules, no direct tools.py imports
12. CROSS-STEP PARAMETERS: any tool parameter name that does NOT appear in the input_data keys above MUST be extracted from an earlier step's return value — never invent it, never leave it out. Find which earlier step's tool documents that exact field under "Returns:" in Available Tools, extract it from that step's result dict by that exact field name, then pass it to the next tool under whatever name THAT tool's "Parameters:" section calls it — the producer's field name and the consumer's parameter name are not guaranteed to match, so map them explicitly (e.g. `registration_number=business_profile["registration_number"]`, not an assumption that the field just carries over under the same name).
13. TYPE SAFETY ON CHAINED VALUES: never call `.get(`, attribute access, or dict-style indexing on a previous step's return value or on an input_data field without knowing its actual type. Do NOT default to assuming a manager method returns a dict — only treat it as a dict if its "Returns:" section explicitly documents named fields. If "Returns:" says "(not documented in toolspec...)" or looks like a single value, treat the return as a plain scalar (string/number/bool) and use it directly — do not index into it or call `.get()` on it. An input_data field described as an array may arrive as a literal dict/list already (do not call `.get()` on it as if it were the tool's response, and do not assume a string field is a parsed list — pass it straight through if the SOP doesn't require inspecting its contents).
14. DECISION/STATUS LOGIC MUST FOLLOW NAMED CONDITIONS, NOT A SHORTCUT: when the SOP describes how to determine a final decision/status field (e.g. "trigger X if <specific condition>, else Y"), implement each named condition as an explicit check against the specific field(s) the SOP names for it — do not collapse multiple named conditions into a single numeric threshold or a default value unless the SOP itself says to use one. If the SOP explicitly says a computed score is unreliable/noisy/not authoritative, do not use that score as the primary or sole basis for the decision — the named checks it says to weigh instead are the real logic. Re-read the SOP's decision section once you know which tools/fields are involved, and enumerate every condition it lists before writing the branching code.
    A SOP's individual trigger conditions are frequently NOT all restated in
    whichever section makes the final decision — that section often just
    says something like "triggering X if your review triggers any of the
    above checks", referring back to conditions stated earlier, inline,
    inside unrelated-looking procedural steps (e.g. a data-validation
    section saying "if the ID format is invalid, escalate immediately", or
    a documentation-check section saying "if fields look inconsistent, mark
    awaiting information"). Read the ENTIRE SOP for every sentence phrased
    as "if <condition>, <status>" before writing the decision logic, not
    just the section literally titled as the decision/escalation section —
    a condition stated once, anywhere in the document, still has to be
    checked.
15. OUTPUT VALUE FORMAT — USE THE SOP'S OWN TERMINOLOGY, NOT JUST THE PART THAT VARIES: when the SOP names a set of output values as a compound phrase (e.g. "apply the Hazard Class A, B, C and D" — meaning the category names ARE "Hazard Class A", "Hazard Class C", etc., not bare "A"/"C"), output the value exactly as the SOP phrases each member, not merely the substring that changes between them. A later section giving a short parenthetical like "(A, B, C, or D)" is naming which variant applies, not redefining the output format — prefer the fuller phrasing used where the value is first introduced unless the SOP's own output/example section explicitly shows the shorter form.
16. OUTPUT DICT KEYS MUST BE FLAT, SHORT, CANONICAL FIELD NAMES — NOT PROSE LIFTED FROM THE OUTPUT SECTION: a SOP's Output section often describes deliverables in prose ("Final hazard class designation", "Digital record in Hazard Classification Registry") rather than handing you a field name. Do not turn that prose into a dict key (e.g. `final_hazard_class_designation`) and do not nest the actual computed value inside a larger record/registry structure. Use the short snake_case name that same field is called elsewhere — in the SOP's own body, in a tool's documented Parameters/Returns, or as the variable you already computed it into (e.g. `hazard_class`, `hazard_score`) — and place it directly at the top level of the returned dict, never nested inside another dict.
17. NEVER CHECK A KEY THAT ISN'T IN THE TOOL'S DOCUMENTED "Returns:" FIELDS: when branching on a previous step's result (e.g. deciding whether to escalate based on a verification step's outcome), only read keys that tool's "Returns:" section actually lists — never invent a plausible-sounding generic key like `.get("status")` that isn't one of them. If the meaningful signal is nested (e.g. "Returns:" says a field is a list of {{name, status}} objects, not a top-level status), read it from where it actually lives, not from a shortcut field you assumed would exist. A branch condition that references a key absent from every tool's documented Returns will silently never fire — that's not a warning the code will raise, it just quietly does nothing, so get the key names right by checking Returns before writing the check, not after.
18. DO NOT REUSE ONE FIELD'S COMPARISON LOGIC FOR A DIFFERENT FIELD, EVEN IF THEY LOOK STRUCTURALLY IDENTICAL: two fields can share the same shape (e.g. both are lists of {{name, status}} objects) while using completely different value vocabularies for status (e.g. one uses 'Clear'/'Pending'/'Matched', another uses 'Yes'/'No'). Check each field's "Returns:" description for its OWN specific possible values before writing a comparison against it — do not copy a condition you just wrote for one field onto a sibling field a few lines later without re-reading what values that specific field actually takes. A copied comparison against the wrong vocabulary won't error, it will just silently evaluate to the same result for every input.

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
                # to MAX_CODE_LINES=500 in validation_agent.py, and observed
                # runs so far (60-75 lines) don't reflect that ceiling.
                response = ClientSingleton.execute(messages, max_tokens=3000)
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
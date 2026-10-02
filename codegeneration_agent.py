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

        # ── 3-5. LLM CALL, EXTRACTION, OUTPUT GUARDRAILS — RETRIED TOGETHER ─────
        # A rejection at step 5 (e.g. a dangerous-pattern guardrail, a missing
        # required element) used to propagate straight out of __call__ and
        # end the ENTIRE pipeline run on the very first attempt — before the
        # orchestrator's own retry loop ever got a turn, since _call_with_retry
        # only retries the raw LLM call, not what happens to its output.
        # Regenerating (a fresh LLM call, not just re-validating the same
        # rejected code) is the only way a guardrail rejection can resolve, so
        # retry the whole (call, extract, validate) sequence here instead.
        last_exc: Optional[Exception] = None
        code = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._call_with_retry(messages)
                candidate = self._extract_code(response)
                code = self._validate_output(candidate, state)
                break
            except CodeGeneratorAgentError as exc:
                last_exc = exc
                logger.warning(
                    f"CodeGeneratorAgent output guardrail rejected attempt "
                    f"{attempt}/{MAX_RETRIES}: {exc}. Regenerating..."
                )
        else:
            raise CodeGeneratorAgentError(
                f"Generated code failed output guardrails after {MAX_RETRIES} "
                f"attempts. Last error: {last_exc}"
            )

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
22. NEVER PASS A HARDCODED LITERAL FOR A TOOL PARAMETER THAT HAS A REAL SOURCE: if a parameter's value is available from `input_data` (rule 4's key list) or an earlier step's return (rule 12), it must come from there — never a made-up placeholder string/number that merely looks plausible (e.g. `service_type="internet"`, `region="UNKNOWN"`), even as a "default" for a branch you think is unreachable. A hardcoded guess only coincidentally matches real data and silently breaks every input where it doesn't — this fails louder than most bugs here (the tool's own lookup rejects it) but only on whichever inputs happen to differ from the guess, so it can still pass a small sample of test rows undetected.
23. EARLY-TERMINATION CHECKLIST — BUILD IT BEFORE WRITING ANY CODE: scan the entire SOP text for every sentence that stops the process early — phrases like "conclude the case", "terminate the process", "close the case", "ineligible for support", "immediately terminate", "log the issue and stop". For EACH one found, write down: (a) which step's result the triggering condition depends on, and (b) what the function must return at that point. Then, when writing the code, insert that check as an explicit `if <condition>: return {{...}}` placed IMMEDIATELY after the step that produces the condition's value — never deferred to a later "determine final status" section, and never implemented merely by skipping ONE subsequent optional step while still letting every step after that run unconditionally. A termination condition almost always means "stop calling tools entirely from here on", not "skip the next tool but keep going" — if a later step's tool call assumes a state that an earlier termination condition rules out (e.g. calling a diagnostics tool for an account already established as ineligible), the fixture data for that later tool won't exist for that case, and the call raises a lookup error instead of the SOP's intended clean early return. Before finalizing the code, re-read your own checklist from this rule and verify each entry has a matching `return` placed at the right step — a rule you "know about" but positioned incorrectly (e.g. only gating the very next line instead of everything downstream) is the same bug as not having it.
24. NEVER SUBSTITUTE A "SIMPLIFYING ASSUMPTION" — OR A SILENT COPY OF AN UNRELATED VARIABLE — FOR A CHECK THE SOP DEFINES WITH REAL CONDITIONS: if the SOP states a specific rule for deriving a decision/status variable, and a tool's documented "Returns:" shape gives you the actual named field(s) that rule needs, you MUST implement that exact check by reading those exact field names — not approximate it. This bug shows up in disguises that each look different but are the SAME violation: (a) hardcoding the value with a rationalizing comment ("assume", "simplify", "for now", "not explicitly detailed") instead of deriving it from the tool's response; (b) silently reusing a DIFFERENT variable left over from an earlier, unrelated step instead of the field this tool's own response actually documents; (c) checking the response object's truthiness instead of a named field inside it (rule 25). All three compile, run without error, and look plausible on a quick read — that's exactly why they survive review. Before writing ANY decision/status variable, name out loud which exact key, inside which tool's documented Returns, supplies it, using that key's real spelling from that tool's "Returns:" section — if you can't name the specific key, you haven't implemented the SOP's check, you've guessed at it. If a "Returns:" field's shape is genuinely undocumented (rule 13), that's the one case where a coarser heuristic is defensible — but once the shape IS documented (has a "properties"/named-fields breakdown, not just "shape not further specified"), you have no basis to call it undocumented and skip the real check.
25. A NON-EMPTY OBJECT IS ALWAYS TRUTHY, REGARDLESS OF WHAT'S INSIDE IT (the third disguise from rule 24): `bool(some_dict)` / `if some_dict:` tests only whether the dict has any keys at all — a dict representing a FAILURE/negative outcome is just as truthy as one representing a SUCCESS/positive outcome, because both are non-empty dicts with the same keys present, just different values. If a tool's documented "Returns:" gives you a status/outcome FIELD inside an object, checking the object's own truthiness is never a substitute for checking that field's actual value — it will silently evaluate to "success"/"present" on every row where the object exists at all, which for most fixture data is every row, defeating the check entirely while looking like it does something.
26. EVERY `input_data[...]` VALUE IS A RAW STRING, EVEN WHEN ITS NAME OR SOP DESCRIPTION SOUNDS NUMERIC OR BOOLEAN: `input_data` always arrives as text (from a CSV cell or a real caller), never a real `int`/`float`/`bool`, regardless of what the SOP or a parameter's own description implies about its type. Comparing a raw `input_data` value directly with `<`/`>`/`<=`/`>=` against a numeric literal (e.g. `input_data["confidence_score"] < 0.85`) raises `TypeError: '<' not supported between instances of 'str' and 'float'` — a hard crash on every single row, not just wrong output. Before any numeric or boolean comparison, arithmetic, or threshold check involving an `input_data` field, cast it explicitly: `float(input_data["confidence_score"])`, `int(input_data["retry_count"])`, or for booleans `str(input_data["flag"]).strip().lower() == "true"` (Python's own `bool("False")` is `True` — never use bare `bool(...)` on a string). This applies even to a value you're about to pass straight into a tool call that itself expects that type.

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
                # 4000 was a Groq-TPM-era compromise (8000 TPM ceiling made
                # anything higher unreliable for customer_service_sop's
                # 10-tool prompt). On OpenRouter that ceiling doesn't apply,
                # and OpenRouter's reasoning models (e.g. openai/gpt-oss-120b)
                # spend part of max_tokens on a hidden `reasoning` field
                # before emitting visible content — for a complex generation
                # prompt that can consume most of a 4000 budget by itself,
                # leaving `content` blank. 8000 matches validation_agent.py's
                # already-proven budget for the same model/provider.
                response = ClientSingleton.execute(messages, max_tokens=8000)
                if not response or not hasattr(response, "content"):
                    raise RuntimeError(
                        "LLM returned empty or malformed response."
                    )
                if not isinstance(response.content, str) or not response.content.strip():
                    # Transient, not a hard failure: a reasoning model can
                    # burn the whole max_tokens budget on hidden reasoning
                    # tokens before emitting content, non-deterministically.
                    # Retrying (like any other Exception below) usually
                    # succeeds; treating it as an unretryable
                    # CodeGeneratorAgentError (as before) wasted the entire
                    # node on one unlucky sample.
                    raise RuntimeError("LLM response content is blank.")
                return response

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
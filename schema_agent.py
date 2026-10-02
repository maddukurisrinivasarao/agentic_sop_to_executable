import re
import json
import time
import logging
from typing import Optional
from client import ClientSingleton
from sop_state import SOPConverterState

logger = logging.getLogger(__name__)

VALID_PARAM_TYPES = {"string", "integer", "number", "boolean", "array", "object"}


class SchemaAgentError(Exception):
    """Custom exception for SchemaAgent failures."""
    pass


class SchemaAgent:
    """
    Agent responsible for identifying base-level input parameters.
    Includes input validation, output validation, retry logic, and safe parsing.
    """

    MAX_RETRIES = 3
    MAX_PARAMS = 50
    MIN_PARAM_NAME_LENGTH = 1
    MAX_PARAM_NAME_LENGTH = 100

    def __call__(self, state: SOPConverterState) -> SOPConverterState:
        print("\n" + "=" * 80)
        print("🤖 SCHEMA AGENT: Identifying input parameters...")
        print("=" * 80)

        # ── 1. INPUT GUARDRAILS ───────────────────────────────────────────────
        self._validate_input(state)

        # ── 2. BUILD PROMPT ───────────────────────────────────────────────────
        prompt = self._build_prompt(state)
        messages = [
            {"role": "system", "content": "You are an expert data schema analyst."},
            {"role": "user",   "content": prompt},
        ]

        # ── 3-5. LLM CALL, PARSING, OUTPUT GUARDRAILS — RETRIED TOGETHER ────────
        # A parse/guardrail rejection at step 4/5 used to propagate straight
        # out of __call__ and end the entire pipeline run on the first
        # attempt, since _call_with_retry only retries the raw LLM call, not
        # what happens to its output (same architectural gap already fixed
        # in codegeneration_agent.py). Regenerating is the only way a parse
        # failure can resolve, so retry the whole sequence here too.
        last_exc: Optional[Exception] = None
        input_schema = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self._call_with_retry(messages)
                parsed = self._parse_response(response)
                input_schema = self._validate_output(parsed, state)
                break
            except SchemaAgentError as exc:
                last_exc = exc
                logger.warning(
                    f"SchemaAgent output guardrail rejected attempt "
                    f"{attempt}/{self.MAX_RETRIES}: {exc}. Regenerating..."
                )
        else:
            raise SchemaAgentError(
                f"Input schema failed output guardrails after "
                f"{self.MAX_RETRIES} attempts. Last error: {last_exc}"
            )

        # ── 6. COMMIT TO STATE ────────────────────────────────────────────────
        print(f"✓ Identified {len(input_schema)} input parameters")
        for param in input_schema:
            req = "required" if param.get("required") else "optional"
            print(f"  • {param['name']} ({param['type']}, {req})")

        state["input_schema"] = input_schema
        return state

    # =========================================================================
    # INPUT GUARDRAILS
    # =========================================================================

    def _validate_input(self, state: SOPConverterState) -> None:
        """Validate all required state fields before touching the LLM."""

        # --- SOP ---
        sop = state.get("sop")
        if not sop or not isinstance(sop, str) or not sop.strip():
            raise SchemaAgentError("Input guardrail: 'sop' must be a non-empty string.")

        # --- api_plan: must exist and be a non-empty list produced by PlannerAgent ---
        api_plan = state.get("api_plan")
        if not api_plan or not isinstance(api_plan, list):
            raise SchemaAgentError(
                "Input guardrail: 'api_plan' must be a non-empty list. "
                "Ensure PlannerAgent ran successfully before SchemaAgent."
            )

        required_plan_keys = {"step", "task", "tool", "description"}
        for i, step in enumerate(api_plan):
            if not isinstance(step, dict):
                raise SchemaAgentError(
                    f"Input guardrail: api_plan[{i}] is not a dict."
                )
            missing = required_plan_keys - step.keys()
            if missing:
                raise SchemaAgentError(
                    f"Input guardrail: api_plan[{i}] is missing keys: {missing}"
                )

        # --- tools_formatted ---
        tools_formatted = state.get("tools_formatted")
        if not tools_formatted or not isinstance(tools_formatted, str):
            raise SchemaAgentError(
                "Input guardrail: 'tools_formatted' must be a non-empty string."
            )

        # --- Prompt-injection check on SOP ---
        injection_markers = [
            "ignore previous instructions",
            "ignore all instructions",
            "disregard the above",
            "forget everything",
            "you are now",
        ]
        sop_lower = sop.lower()
        for marker in injection_markers:
            if marker in sop_lower:
                raise SchemaAgentError(
                    f"Input guardrail: Potential prompt injection in SOP: '{marker}'."
                )

        logger.info("SchemaAgent input validation passed.")

    # =========================================================================
    # PROMPT BUILDER
    # =========================================================================

    def _compute_parameter_checklist(self, state: SOPConverterState) -> str:
        """
        Deterministically enumerate every distinct parameter name required by
        at least one tool in the plan, and every distinct field name returned
        by at least one of those tools. Asking the LLM to recall this list
        from tools_formatted prose is exactly where it starts missing or
        inventing names once a domain has enough tools (observed directly:
        a 26-tool domain got a schema with invented parameter names that
        don't exist in the toolspec at all, and separately missed several
        real ones). Handing it a precomputed, guaranteed-complete checklist
        turns "recall N names from a wall of text" into "classify each name
        in this list" — the second task degrades far less with scale.
        """
        tools_by_name = {t["name"]: t for t in state.get("tools", []) if isinstance(t, dict)}
        plan_tool_names = {step["tool"] for step in state["api_plan"] if step.get("tool")}

        required_param_names = set()
        optional_param_notes = {}
        return_names = set()
        for name in plan_tool_names:
            tool = tools_by_name.get(name)
            if not tool:
                continue
            for pname, pspec in tool.get("parameters", {}).items():
                if isinstance(pspec, dict) and pspec.get("required") is False:
                    # Optional with its own default — NOT automatically a
                    # base-level input. A tool parameter being optional and
                    # pre-defaulted means codegen can omit it or pass its
                    # documented default; forcing every parameter (required
                    # or not) into "base-level input vs. covered by an
                    # earlier return" previously had no third option, so an
                    # optional flag like a tool's own `include_history=False`
                    # default got wrongly promoted to a required input_data
                    # field that doesn't exist in the real data, crashing
                    # every row with a KeyError.
                    optional_param_notes[pname] = pspec.get("default", "no stated default")
                else:
                    required_param_names.add(pname)
            returns = tool.get("returns")
            if isinstance(returns, dict):
                return_names.update(returns.keys())

        if not required_param_names and not optional_param_notes:
            return ""

        optional_section = ""
        if optional_param_notes:
            optional_lines = "\n".join(
                f"  - {pname} (default: {default!r}) — do NOT add this as a "
                f"base-level input unless the SOP explicitly describes the "
                f"user/caller supplying it; otherwise the generated code "
                f"should omit it or pass its documented default literally."
                for pname, default in sorted(optional_param_notes.items())
            )
            optional_section = f"""

These parameters are OPTIONAL on their tool and already have a documented
default — they are a separate case from the required list below, not part
of it:
{optional_lines}"""

        return f"""
Precomputed checklist (do not recompute this by re-reading the tools' prose —
use it directly): every distinct REQUIRED parameter name needed by at least
one tool your plan actually calls is:
{sorted(required_param_names)}

Every distinct field name returned by at least one of those same tools is:
{sorted(return_names)}

Classify EVERY name in the required-parameter list above: either it matches
(by meaning) one of the names in the returns list, or it belongs in your
input_schema output. Do not output a required parameter name that isn't in
this checklist, and do not omit one that is — this list is complete and
authoritative for the tools your plan uses; if a name looks unfamiliar or
you don't remember seeing it, it's still real if it's in this list.{optional_section}"""

    def _build_prompt(self, state: SOPConverterState) -> str:
        checklist = self._compute_parameter_checklist(state)

        # OrchestratorAgent sets retry_feedback (and escalates the graph back
        # to this agent specifically) only when a validation issue survived a
        # generator-only retry unchanged AND looks schema-shaped (a missing,
        # misnamed, or wrongly-required/optional parameter) — i.e. evidence
        # the SCHEMA itself is the problem, not how codegen used it.
        feedback_section = ""
        retry_feedback = state.get("retry_feedback")
        if retry_feedback:
            previous_schema = state.get("input_schema") or []
            feedback_section = f"""

RETRY — A VALIDATION ISSUE PERSISTED THROUGH A CODE-GENERATION RETRY,
SUGGESTING THE SCHEMA ITSELF (not the generated code) IS MISSING OR
MISNAMING A FIELD:
{retry_feedback}

Your previous input parameter list (don't just resubmit this unchanged —
reconsider whether a required tool parameter is missing, misspelled, or
incorrectly marked optional/required, based on the issue above):
{json.dumps(previous_schema, indent=2)}
"""

        return f"""Identify all BASE-LEVEL input parameters for this workflow.

SOP:
{state['sop']}

API Plan:
{json.dumps(state['api_plan'], indent=2)}

Available Tools:
{state['tools_formatted']}
{checklist}
{feedback_section}

Base-level inputs are parameters that:
- Are NOT outputs from other tools in the plan
- Must be provided by the user at workflow start
- Cannot be derived or computed from earlier steps

Find them two ways, and take the union — neither alone is complete:

FIRST, mechanically, not by reading the SOP's own narrative for what it
calls an "input": for EVERY tool in the API Plan (every occurrence, not just
the first time a tool name appears — later steps can reuse a tool with
different call-site parameters), list every parameter in that tool's
"Parameters:" section under Available Tools. For each one, check whether any
EARLIER step's tool "Returns:" a field that supplies it — MATCH BY MEANING,
NOT EXACT STRING: a "Returns:" field and a "Parameters:" field naming the
same concept are very often spelled differently in this data (the same
boolean can appear as `is account id valid` in one tool's Returns and
`is_account_id_valid` in another tool's Parameters — spaced vs. snake_case,
and occasionally a genuine synonym). Read what each field actually holds,
not just its literal spelling, before concluding nothing upstream supplies
it. If, after that meaning-level check, no earlier step's output covers it,
it is a base-level input — regardless of whether the SOP's prose ever calls
it out as something "the user provides" or "the customer submits". A
parameter can be required by a tool the SOP describes as an internal lookup
(e.g. "check the service area for outages") without the SOP ever mentioning
that lookup needs a caller-supplied code — the tool's own "Parameters:" list
is still authoritative and still makes it a base-level input if nothing
upstream produces it, under the meaning-matching rule above. Missing one of
these silently breaks every later step that calls that tool, however the
generated code chooses to compensate (a placeholder, a guess derived from
some other field, etc.) — the fix belongs here, not in a workaround
downstream.

SECOND, separately, read the SOP's own "Input"/"Definitions" section (the
part that names things like an identifier, a free-text body, a timestamp)
and include every field it names there too — even ones NO tool ever takes
as a parameter. Not every base-level input feeds a tool call: some are only
used by the generated code's own inline logic (extracting a value from a
free-text field, echoing an identifier straight into the output, branching
on a flag) and never appear in any "Parameters:" list at all. The first,
mechanical pass will never find these on its own, because by definition
they're absent from every tool's parameters — skipping this second pass
because "the mechanical check already covered inputs" is exactly the gap
that produces a workflow silently missing its own primary key or main
content field (e.g. an email-processing workflow that fetches every
product's price/description/status but never once reads the email's
own id or body, because neither is ever passed to a tool).

Before adding a field found this second way, check it's not just a prose
RESTATEMENT of a field the mechanical pass already covered under a
different spelling — an SOP can describe the same real-world field with
one name in its "Input" section and a shorter/different name in its
procedure steps or a tool's actual "Parameters:" list (e.g. an Input
section listing "operating_system" and "browser_specification" as prose
labels, while the procedure text and every tool actually use `os` and
`browser`). When that happens, the tool's real parameter spelling is
authoritative — it's what `input_data` will actually be keyed by at
runtime — so use that spelling and do NOT also add the Input section's
prose version as a second, separate field; that produces two entries for
one real value, and the one you invented from prose has no real column to
read from.

Two things are NEVER base-level inputs, even if the mechanical check above
seems to suggest one: (1) anything the SOP's own Output/Deliverables section
lists as something this workflow produces — a field the workflow computes
and returns is not also something it must receive as an input; (2) any
intermediate decision/flag your own reasoning about the SOP concludes is
*derived* from tool results (a boolean like "is authenticated" or "is
eligible" that a later step's logic decides, rather than a value a tool
literally returns unchanged) — if you can't point to one specific tool's
"Returns:" field (by meaning) that IS this value, it isn't a base-level
input just because no tool's Returns matches it exactly; it's something the
generated code must compute, and belongs nowhere in this list.

Rule (2) still applies even when the derivation takes real logic to write —
a boolean check, a comparison against a threshold, string matching, picking
one of several tool results — not just a rename. "No tool returns this
value under any name" does NOT default to "therefore it's a base-level
input": it defaults to "the generated code must compute it from what tools
DO return", which is a normal, expected part of turning an SOP into code,
not a gap to plug with an extra input. `is_authenticated` in a workflow
where authentication is decided by whether `getAuthenticationDetails`
returned any records — computed with one `bool(...)` check, still NOT a
base-level input, even though no tool's "Returns:" is spelled anything like
"authenticated". Ask yourself, for every candidate: "if I removed this from
the input list, could the workflow still produce it purely from tool calls
plus ordinary Python logic (if/comparison/boolean)?" — if yes, it does NOT
belong in your output, no matter how naturally it reads as an "input" to
the decision it feeds.

Return a JSON array using this exact schema:
[
  {{
    "name": "patient_id",
    "type": "string",
    "required": true,
    "description": "Unique identifier for the patient"
  }},
  ...
]

Rules:
- "type" must be one of: string, integer, number, boolean, array, object
- "required" must be a boolean (true or false), never a string
- "name" must be copied EXACTLY as it's spelled in the tool's "Parameters:"
  list under Available Tools — do not normalize casing, add/remove
  underscores, or otherwise "clean up" the spelling, even if it looks
  inconsistent (a real parameter can be `Captcha_tries` with a capital C).
  The generated workflow reads this value out of `input_data` using this
  exact string as the dict key, and `input_data`'s keys are the raw column
  headers from the source data — a normalized name that no longer matches
  the real header causes a `KeyError` at runtime that a spec/schema review
  won't catch, since everything still *looks* correct. The one time to
  choose the name yourself (snake_case is a reasonable default here) is for
  a field found only in the SOP's own Input/Definitions section that no
  tool ever takes as a parameter — there, no external spelling constrains
  you.
- Return ONLY the JSON array — no markdown fences, no explanation
- Maximum {self.MAX_PARAMS} parameters"""

    # =========================================================================
    # LLM CALL WITH RETRY
    # =========================================================================

    def _call_with_retry(self, messages: list) -> object:
        """Call LLM with exponential back-off retry on transient failures."""
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info(f"SchemaAgent LLM call attempt {attempt}/{self.MAX_RETRIES}")
                # Same reasoning as planner_agent.py's bump: a domain with
                # many input parameters (each with name/type/required/
                # description) can run past the client default of 2000.
                # Bumped again for video_annotation_sop (26 tools, ~23
                # distinct parameters plus the deterministic checklist in
                # the prompt): 3000 produced "No JSON array found" — the
                # array likely ran past the cap before closing.
                response = ClientSingleton.execute(messages, max_tokens=6000)

                if not response or not hasattr(response, "content"):
                    raise RuntimeError("LLM returned empty or malformed response.")
                if not isinstance(response.content, str) or not response.content.strip():
                    # Transient: a reasoning model (e.g. OpenRouter's
                    # openai/gpt-oss-120b) can non-deterministically spend
                    # the whole max_tokens budget on hidden reasoning before
                    # emitting content, leaving it blank. Retry like any
                    # other Exception below instead of failing the node
                    # outright on one unlucky sample.
                    raise RuntimeError("LLM response content is blank.")

                return response

            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    f"SchemaAgent LLM call failed (attempt {attempt}): {exc}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)

        raise SchemaAgentError(
            f"LLM call failed after {self.MAX_RETRIES} attempts. Last error: {last_exc}"
        )

    # =========================================================================
    # SAFE PARSING
    # =========================================================================

    def _parse_response(self, response) -> list:
        """Robustly extract a JSON array from the LLM response."""
        raw = response.content.strip()

        # Strip accidental markdown fences
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"```$", "", raw).strip()

        # strict=False: same fix as planner_agent.py/validation_agent.py —
        # a field value with an unescaped raw newline is otherwise a hard
        # parse error in strict JSON even though the content is fine.

        # Try direct parse first
        try:
            parsed = json.loads(raw, strict=False)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fallback: extract the first [...] block
        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0), strict=False)
            except json.JSONDecodeError as exc:
                raise SchemaAgentError(
                    f"Parse guardrail: Found JSON array but could not decode it: {exc}\n"
                    f"Raw snippet: {json_match.group(0)[:300]}"
                )

        raise SchemaAgentError(
            f"Parse guardrail: No JSON array found in LLM response.\n"
            f"Response (first 500 chars): {raw[:500]}"
        )

    # =========================================================================
    # OUTPUT GUARDRAILS
    # =========================================================================

    def _validate_output(
        self, input_schema: list, state: SOPConverterState
    ) -> list:
        """Validate and sanitize the parsed schema before writing to state."""

        if not input_schema:
            raise SchemaAgentError(
                "Output guardrail: LLM returned an empty schema. "
                "Every workflow needs at least one input parameter."
            )

        if len(input_schema) > self.MAX_PARAMS:
            raise SchemaAgentError(
                f"Output guardrail: Schema has {len(input_schema)} params, "
                f"exceeding the maximum of {self.MAX_PARAMS}."
            )

        # Collect tool output names to cross-check (outputs should NOT appear as inputs)
        tool_outputs = self._extract_tool_output_names(state)
        seen_names = set()

        for i, param in enumerate(input_schema):

            # --- Must be a dict ---
            if not isinstance(param, dict):
                raise SchemaAgentError(
                    f"Output guardrail: param[{i}] is not a dict: {param}"
                )

            # --- Required keys ---
            required_keys = {"name", "type", "required", "description"}
            missing = required_keys - param.keys()
            if missing:
                raise SchemaAgentError(
                    f"Output guardrail: param[{i}] is missing keys: {missing}"
                )

            # --- name: non-empty string, snake_case, no spaces ---
            name = param["name"]
            if not isinstance(name, str) or not name.strip():
                raise SchemaAgentError(
                    f"Output guardrail: param[{i}] 'name' must be a non-empty string."
                )
            name = name.strip()
            if len(name) > self.MAX_PARAM_NAME_LENGTH:
                raise SchemaAgentError(
                    f"Output guardrail: param '{name}' name exceeds "
                    f"{self.MAX_PARAM_NAME_LENGTH} characters."
                )
            # A valid Python identifier shape (letters/digits/underscores,
            # not starting with a digit) — NOT forced to lowercase, since a
            # real tool parameter can use mixed case (e.g. `Captcha_tries`)
            # and the prompt now explicitly asks for exact spelling, not
            # normalized snake_case, to keep this name usable as a literal
            # `input_data[...]` dict key against the real column header.
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
                raise SchemaAgentError(
                    f"Output guardrail: param name '{name}' must look like a "
                    f"valid identifier (letters, digits, underscores; not "
                    f"starting with a digit) — no spaces or punctuation."
                )

            # --- Duplicate names ---
            if name in seen_names:
                raise SchemaAgentError(
                    f"Output guardrail: Duplicate parameter name '{name}'."
                )
            seen_names.add(name)

            # --- type: must be in whitelist ---
            param_type = param["type"]
            if not isinstance(param_type, str) or param_type not in VALID_PARAM_TYPES:
                raise SchemaAgentError(
                    f"Output guardrail: param '{name}' has invalid type '{param_type}'. "
                    f"Must be one of: {sorted(VALID_PARAM_TYPES)}"
                )

            # --- required: must be a boolean ---
            if not isinstance(param["required"], bool):
                # Attempt a lenient fix: "true"/"false" strings → bool
                if isinstance(param["required"], str):
                    coerced = param["required"].strip().lower()
                    if coerced == "true":
                        param["required"] = True
                        logger.warning(
                            f"Output guardrail: coerced 'required' string→bool for '{name}'."
                        )
                    elif coerced == "false":
                        param["required"] = False
                        logger.warning(
                            f"Output guardrail: coerced 'required' string→bool for '{name}'."
                        )
                    else:
                        raise SchemaAgentError(
                            f"Output guardrail: param '{name}' 'required' must be a boolean."
                        )
                else:
                    raise SchemaAgentError(
                        f"Output guardrail: param '{name}' 'required' must be a boolean."
                    )

            # --- description: non-empty string ---
            desc = param["description"]
            if not isinstance(desc, str) or not desc.strip():
                raise SchemaAgentError(
                    f"Output guardrail: param '{name}' 'description' must be a non-empty string."
                )

            # --- Cross-check: input should not be a known tool output ---
            if tool_outputs and name in tool_outputs:
                logger.warning(
                    f"Output guardrail: param '{name}' looks like a tool output, "
                    f"not a base-level input. Flagging for review."
                )

            # --- Sanitize strings ---
            param["name"] = name
            param["type"] = param_type.strip()
            param["description"] = desc.strip()

        logger.info(f"SchemaAgent output validation passed: {len(input_schema)} params.")
        return input_schema

    def _extract_tool_output_names(self, state: SOPConverterState) -> set:
        """
        Best-effort: extract return-value field names from tools_formatted
        to flag params that are tool outputs being misclassified as inputs.
        Looks for lines under 'Returns:' in format_tools_for_llm output.
        """
        tools_formatted = state.get("tools_formatted", "")
        if not tools_formatted:
            return set()
        # Capture words after "Returns:" lines
        matches = re.findall(r'Returns:.*?([a-z][a-z0-9_]+)', tools_formatted, re.IGNORECASE)
        return {m.lower() for m in matches} if matches else set()
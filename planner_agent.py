import re
import json
from client import ClientSingleton
from sop_state import SOPConverterState
import logging
logger = logging.getLogger(__name__)

# ============================================================================
# AGENT 1: PLANNER AGENT
# ============================================================================
class PlannerAgentError(Exception):
    """Custom exception for PlannerAgent failures."""
    pass

class PlannerAgent:
    """
    Agent responsible for analyzing SOP and creating API execution plan
    Includes input validation, output validation, retry logic, and safe parsing.
    """
    MAX_SOP_LENGTH = 50_000        # characters
    MIN_SOP_LENGTH = 10
    MAX_PLAN_STEPS = 50
    MAX_RETRIES = 3
    def __call__(self, state: SOPConverterState) -> SOPConverterState:
        """
        Analyze SOP and create API plan
        """
        print("\n" + "=" * 80)
        print("🤖 PLANNER AGENT: Analyzing SOP...")
        print("=" * 80)
        
        # 1. INPUT VALIDATION GUARDRAILS
        self._validate_input(state)
        
        # 2. BUILD PROMPT
        prompt = self._build_prompt(state)
        messages = [
            {"role": "system", "content": "You are an expert workflow planner."},
            {"role": "user",   "content": prompt},
        ]

        # 3. LLM CALL
        response = self._call_with_retry(messages)        
        print('PLANNER AGENT LLM RESPONE= {response}')
        
        # 4. SAFE PARSING LLM RESPONSE
        api_plan = self._parse_response(response)
        
        
        # 5. OUTPUT GUARDRAILS
        api_plan = self._validate_output(api_plan, state)

        # 6. COMMIT TO 
        print(f"✓ Created plan with {len(api_plan)} steps")
        for step in api_plan:
            print(f"  Step {step['step']}: {step['tool']}")
        
        state['api_plan'] = api_plan
        state['status'] = "planning"
        return state

    # =========================================================================
    # INPUT GUARDRAILS
    # =========================================================================
    def _validate_input(self, state: SOPConverterState) -> None:
       """Validate state fields before sending to the LLM."""

       # --- SOP presence & type ---
       sop = state.get("sop")
       if not sop or not isinstance(sop, str):
           raise PlannerAgentError("Input guardrail: 'sop' must be a non-empty string.")

       sop = sop.strip()
       if len(sop) < self.MIN_SOP_LENGTH:
           raise PlannerAgentError(
               f"Input guardrail: SOP is too short ({len(sop)} chars). "
               f"Minimum is {self.MIN_SOP_LENGTH}."
           )
       if len(sop) > self.MAX_SOP_LENGTH:
           raise PlannerAgentError(
               f"Input guardrail: SOP exceeds maximum length "
               f"({len(sop)} > {self.MAX_SOP_LENGTH} chars). Truncate before sending."
           )

       # --- Tools presence ---
       tools_formatted = state.get("tools_formatted")
       if not tools_formatted or not isinstance(tools_formatted, str):
           raise PlannerAgentError(
               "Input guardrail: 'tools_formatted' must be a non-empty string."
           )

       # --- Prompt-injection heuristic ---
       injection_markers = [
           "ignore previous instructions",
           "ignore all instructions",
           "disregard the above",
           "forget everything",
       ]
       sop_lower = sop.lower()
       for marker in injection_markers:
           if marker in sop_lower:
               raise PlannerAgentError(
                   f"Input guardrail: Potential prompt-injection detected in SOP: '{marker}'."
               )

       logger.info("Input validation passed.")

    # =========================================================================
    # PROMPT BUILDER
    # =========================================================================

    def _build_prompt(self, state: SOPConverterState) -> str:
        # OrchestratorAgent sets retry_feedback (and escalates the graph back
        # to this agent specifically) only when a validation issue survived a
        # generator-only retry unchanged AND looks plan-shaped (wrong tool,
        # missing/extra step, wrong order) — i.e. evidence the PLAN itself is
        # the problem, not how codegen implemented it.
        feedback_section = ""
        retry_feedback = state.get("retry_feedback")
        if retry_feedback:
            previous_plan = state.get("api_plan") or []
            feedback_section = f"""

RETRY — A VALIDATION ISSUE PERSISTED THROUGH A CODE-GENERATION RETRY,
SUGGESTING THE PLAN ITSELF (not the generated code) IS THE PROBLEM:
{retry_feedback}

Your previous plan (don't just resubmit this unchanged — reconsider the
tool choice, step order, or whether a step is missing or shouldn't be
there, based on the issue above):
{json.dumps(previous_plan, indent=2)}
"""

        return f"""You are a workflow planning expert. Analyze this SOP and create an execution plan.

SOP:
{state['sop']}

Available Tools:
{state['tools_formatted']}
{feedback_section}
Create a step-by-step API execution plan — a plan of TOOL CALLS, not a
transcription of every sentence in the SOP. For each step:
1. Identify a task that requires calling one of the Available Tools
2. Match it to the exact tool name
3. Determine the logical sequence

Return a JSON array with this exact schema:
[
  {{
    "step": 1,
    "task": "Validate patient insurance",
    "tool": "validateInsurance",
    "description": "Verify insurance coverage details"
  }},
  ...
]

Rules:
- Return ONLY the JSON array — no markdown fences, no explanation.
- Every tool name must be taken verbatim from the Available Tools list.
- Steps must be sequentially numbered starting from 1.
- Maximum {self.MAX_PLAN_STEPS} steps.
- Not every sentence in the SOP needs a step here. Many SOPs describe data
  extraction, formatting, or classification logic (e.g. "extract the ID from
  the text using pattern matching", "validate the ID format") that has no
  corresponding tool in Available Tools — that logic gets implemented
  directly in code later from the SOP text, which the code generator also
  receives in full. Leave those out of this plan entirely rather than
  inventing a tool name for them or leaving "tool" empty — every entry you
  return must name one real, callable tool."""

    # =========================================================================
    # LLM CALL WITH RETRY
    # =========================================================================

    def _call_with_retry(self, messages: list) -> object:
        """Call the LLM with exponential back-off retry on failure."""
        import time

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info(f"LLM call attempt {attempt}/{self.MAX_RETRIES}")
                # Higher than the client default (2000): a multi-step plan
                # with a task/tool/description per step can run past 2000
                # tokens for domains with several branches, truncating the
                # response before the closing ] — "No JSON array found"
                # even though the array just never got to close.
                response = ClientSingleton.execute(messages, max_tokens=3000)

                # Basic response sanity check
                if not response or not hasattr(response, "content"):
                    raise RuntimeError("LLM returned an empty or malformed response.")
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
                logger.warning(f"LLM call failed (attempt {attempt}): {exc}. Retrying in {wait}s…")
                time.sleep(wait)

        raise PlannerAgentError(
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

        # strict=False: field values (e.g. a "description") can legitimately
        # contain raw newlines the model forgot to escape as \n — strict
        # JSON treats that as a hard parse error ("Unterminated string...")
        # even though the content is otherwise fine. Same fix already
        # applied to validation_agent.py for the identical failure mode.

        # Try direct parse first
        try:
            parsed = json.loads(raw, strict=False)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fall back: extract the first [...] block
        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0), strict=False)
            except json.JSONDecodeError as exc:
                raise PlannerAgentError(
                    f"Parse guardrail: Found a JSON array but could not decode it: {exc}\n"
                    f"Raw snippet: {json_match.group(0)[:300]}"
                )

        raise PlannerAgentError(
            f"Parse guardrail: No JSON array found in LLM response.\n"
            f"Response (first 500 chars): {raw[:500]}"
        )

    # =========================================================================
    # OUTPUT GUARDRAILS
    # =========================================================================

    def _validate_output(self, api_plan: list, state: SOPConverterState) -> list:
        """Validate and sanitize the parsed plan before writing to state."""

        if not api_plan:
            raise PlannerAgentError("Output guardrail: LLM returned an empty plan.")

        if len(api_plan) > self.MAX_PLAN_STEPS:
            raise PlannerAgentError(
                f"Output guardrail: Plan has {len(api_plan)} steps, "
                f"exceeding the maximum of {self.MAX_PLAN_STEPS}."
            )

        required_keys = {"step", "task", "tool", "description"}
        # Build tool whitelist from the available tools (best-effort)
        available_tools = self._extract_tool_names(state.get("tools", ""))

        seen_steps = set()
        for i, entry in enumerate(api_plan):
            # --- Schema check ---
            if not isinstance(entry, dict):
                raise PlannerAgentError(
                    f"Output guardrail: Step {i} is not a dict: {entry}"
                )
            missing = required_keys - entry.keys()
            if missing:
                raise PlannerAgentError(
                    f"Output guardrail: Step {i} is missing keys: {missing}"
                )

            # --- Type checks ---
            if not isinstance(entry["step"], int):
                raise PlannerAgentError(
                    f"Output guardrail: 'step' at index {i} must be an integer."
                )
            for key in ("task", "tool", "description"):
                if not isinstance(entry[key], str) or not entry[key].strip():
                    raise PlannerAgentError(
                        f"Output guardrail: '{key}' at step {entry['step']} must be a non-empty string."
                    )

            # --- Duplicate step numbers ---
            if entry["step"] in seen_steps:
                raise PlannerAgentError(
                    f"Output guardrail: Duplicate step number {entry['step']}."
                )
            seen_steps.add(entry["step"])

            # --- Sequential numbering ---
            if entry["step"] != i + 1:
                raise PlannerAgentError(
                    f"Output guardrail: Steps are not sequentially numbered. "
                    f"Expected {i + 1}, got {entry['step']}."
                )

            # --- Tool whitelist (only if we could extract tool names) ---
            if available_tools and entry["tool"] not in available_tools:
                raise PlannerAgentError(
                    f"Output guardrail: Step {entry['step']} references unknown tool "
                    f"'{entry['tool']}'. Known tools: {sorted(available_tools)}"
                )

            # --- Sanitize strings (strip leading/trailing whitespace) ---
            for key in ("task", "tool", "description"):
                entry[key] = entry[key].strip()

        logger.info(f"Output validation passed: {len(api_plan)} steps.")
        return api_plan

    def _extract_tool_names(self, tools: list = None) -> set:
     """
     Extract tool names directly from the tools list (preferred),
     or fall back to parsing tools_formatted string.
     """
     # ── Preferred: parse directly from the structured list ───────────────
     if tools:
        names = {t["name"] for t in tools if isinstance(t, dict) and t.get("name")}
        logger.info(f"_extract_tool_names: Found {len(names)} tools from list: {names}")
        return names

     return set()
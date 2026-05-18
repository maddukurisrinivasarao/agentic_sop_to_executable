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
        return f"""You are a workflow planning expert. Analyze this SOP and create an execution plan.

SOP:
{state['sop']}

Available Tools:
{state['tools_formatted']}

Create a step-by-step API execution plan. For each step:
1. Identify the task description
2. Match it to the appropriate tool
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
- Maximum {self.MAX_PLAN_STEPS} steps."""       

    # =========================================================================
    # LLM CALL WITH RETRY
    # =========================================================================

    def _call_with_retry(self, messages: list) -> object:
        """Call the LLM with exponential back-off retry on failure."""
        import time

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info(f"LLM call attempt {attempt}/{self.MAX_RETRIES}")
                response = ClientSingleton.execute(messages)

                # Basic response sanity check
                if not response or not hasattr(response, "content"):
                    raise PlannerAgentError("LLM returned an empty or malformed response.")
                if not isinstance(response.content, str) or not response.content.strip():
                    raise PlannerAgentError("LLM response content is blank.")

                return response

            except PlannerAgentError:
                raise  # Don't retry on our own validation errors
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

        # Try direct parse first
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fall back: extract the first [...] block
        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
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
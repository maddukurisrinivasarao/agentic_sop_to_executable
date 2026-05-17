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

        # ── 3. LLM CALL WITH RETRY ────────────────────────────────────────────
        response = self._call_with_retry(messages)

        # ── 4. SAFE PARSING ───────────────────────────────────────────────────
        input_schema = self._parse_response(response)

        # ── 5. OUTPUT GUARDRAILS ──────────────────────────────────────────────
        input_schema = self._validate_output(input_schema, state)

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

    def _build_prompt(self, state: SOPConverterState) -> str:
        return f"""Identify all BASE-LEVEL input parameters for this workflow.

SOP:
{state['sop']}

API Plan:
{json.dumps(state['api_plan'], indent=2)}

Available Tools:
{state['tools_formatted']}

Base-level inputs are parameters that:
- Are NOT outputs from other tools in the plan
- Must be provided by the user at workflow start
- Cannot be derived or computed from earlier steps

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
- "name" must be snake_case, no spaces
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
                response = ClientSingleton.execute(messages)

                if not response or not hasattr(response, "content"):
                    raise SchemaAgentError("LLM returned empty or malformed response.")
                if not isinstance(response.content, str) or not response.content.strip():
                    raise SchemaAgentError("LLM response content is blank.")

                return response

            except SchemaAgentError:
                raise  # Never retry our own validation errors
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

        # Try direct parse first
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fallback: extract the first [...] block
        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
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
            if not re.match(r"^[a-z][a-z0-9_]*$", name):
                raise SchemaAgentError(
                    f"Output guardrail: param name '{name}' must be snake_case "
                    f"(lowercase letters, digits, underscores; start with a letter)."
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
import json
import textwrap
from typing import Dict, Any, List, Tuple, Optional

# -----------------------------
# 1) Tool registry (YOUR tools)
# -----------------------------
# Reuse your existing tools, but DO NOT use AgentExecutor or create_tool_calling_agent.
# Each tool exposes a .run(input_str) method we can call directly.

TOOLS = {
    "wikipedia": {
        "call": lambda s: tool_wiki.run(s),
        "description": "Use to look up concise factual info from Wikipedia. Input: a short search query string."
    },
    "youtube_search": {
        "call": lambda s: tool_youtube.run(s),
        "description": "Use to find a YouTube video URL. Input: a short, specific search query. (Policy: call at most once.)"
    },
    "python_repl": {
        "call": lambda s: python_repl.run(s),
        "description": "Execute Python code. Input must be valid Python. Print outputs with print(...)."
    }
}

ALLOWED_TOOL_NAMES = list(TOOLS.keys())


# ------------------------------------------------
# 2) Helper: render tool docs for the model prompt
# ------------------------------------------------
def render_tools_doc() -> str:
    lines = []
    for name, meta in TOOLS.items():
        lines.append(f"- {name}: {meta['description']}")
    return "\n".join(lines)


# -----------------------------------------------------
# 3) Helper: format scratchpad as Thought/Action blocks
# -----------------------------------------------------
def format_scratchpad(steps: List[Tuple[str, str, str]]) -> str:
    """
    steps = list of (action_name, action_input, observation)
    """
    buf = []
    for idx, (act, inp, obs) in enumerate(steps, start=1):
        buf.append(f"Step {idx}")
        buf.append(f"Thought: I decided to use the '{act}' tool.")
        buf.append(f"Action: {act}")
        buf.append(f"Action Input: {inp}")
        buf.append(f"Observation: {obs}")
        buf.append("")  # newline between steps
    return "\n".join(buf)


# ------------------------------------------------------
# 4) Prompt builder: instruct model to emit strict JSON
# ------------------------------------------------------
def build_prompt(user_query: str, scratchpad_text: str) -> str:
    tools_doc = render_tools_doc()
    system_instructions = f"""
You are an assistant that solves tasks by deciding actions step by step.
You have access to these tools:

{tools_doc}

Rules:
- ALWAYS respond with a SINGLE JSON object and NOTHING ELSE.
- If you want to use a tool, return:
  {{
    "type": "action",
    "tool": "<one of: {', '.join(ALLOWED_TOOL_NAMES)}>",
    "input": "<string input for the tool>"
  }}
- If you are done and want to answer, return:
  {{
    "type": "final",
    "answer": "<your final answer for the user>"
  }}
- Do not include markdown, code fences, or extra text—just pure JSON.
- Be concise and accurate. Use the tools only when helpful.

Scratchpad so far (past steps):
{scratchpad_text if scratchpad_text.strip() else "(empty)"}

User question:
{user_query}
    """.strip()

    # Keep it compact to save tokens
    return textwrap.dedent(system_instructions)


# -----------------------------------------------
# 5) Safe JSON parser with a small repair attempt
# -----------------------------------------------
def parse_action_json(s: str) -> Dict[str, Any]:
    s = s.strip()
    # Try direct parse first
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Small repair: try to extract a JSON object substring
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = s[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        raise


# -----------------------------------------
# 6) Fully Custom Agent (planner + executor)
# -----------------------------------------
class FullyCustomAgent:
    def __init__(
        self,
        llm,                      # your LLM object (must support .invoke(prompt) -> str or dict)
        max_steps: int = 8,
        youtube_once: bool = True,
        truncate_obs: int = 1500,
        verbose: bool = True,
    ):
        self.llm = llm
        self.max_steps = max_steps
        self.youtube_once = youtube_once
        self.truncate_obs = truncate_obs
        self.verbose = verbose

    def _call_llm(self, prompt: str) -> str:
        """
        Calls your LLM and returns a string response.
        Supports llm.invoke(...) returning str or dict.
        """
        out = self.llm.invoke(prompt)
        if isinstance(out, dict) and "content" in out:
            return out["content"]
        if isinstance(out, (dict, list)):
            return json.dumps(out)
        return str(out)

    def run(self, user_query: str) -> Dict[str, Any]:
        steps: List[Tuple[str, str, str]] = []  # (action, input, observation)
        youtube_calls = 0

        for step_idx in range(1, self.max_steps + 1):
            scratchpad_text = format_scratchpad(steps)
            prompt = build_prompt(user_query, scratchpad_text)

            if self.verbose:
                print("\n=== LLM PROMPT =====================================")
                print(prompt)
                print("====================================================\n")

            raw = self._call_llm(prompt)

            if self.verbose:
                print("=== RAW LLM OUTPUT (should be JSON) ================")
                print(raw)
                print("====================================================\n")

            # Parse the JSON decision
            try:
                obj = parse_action_json(raw)
            except Exception as e:
                # If parsing fails, ask for final answer as fallback
                if self.verbose:
                    print(f"[Parser] JSON parse error: {e}. Asking for final answer.\n")
                final_prompt = (
                    "Return a SINGLE JSON object with your final answer only, like "
                    '{"type":"final","answer":"..."}'
                )
                raw = self._call_llm(final_prompt)
                obj = parse_action_json(raw)

            # Decision handling
            typ = obj.get("type")

            if typ == "final":
                final_answer = obj.get("answer", "").strip()
                return {
                    "final_answer": final_answer,
                    "steps": steps,
                    "terminated": "final_answer",
                }

            if typ == "action":
                tool = obj.get("tool", "")
                tool_input = str(obj.get("input", ""))

                # Validate tool name
                if tool not in TOOLS:
                    # Ask the model to correct tool name
                    correction_prompt = (
                        f"Tool '{tool}' is invalid. Only these tools are allowed: "
                        f"{', '.join(ALLOWED_TOOL_NAMES)}. "
                        "Return a SINGLE JSON object correcting your action."
                    )
                    raw = self._call_llm(correction_prompt)
                    obj = parse_action_json(raw)
                    tool = obj.get("tool", "")
                    tool_input = str(obj.get("input", ""))

                    if tool not in TOOLS:
                        # Give up and ask for final
                        if self.verbose:
                            print("[Policy] Invalid tool after correction. Forcing final answer.\n")
                        force_final = (
                            "Return a SINGLE JSON with your final answer only: "
                            '{"type":"final","answer":"..."}'
                        )
                        raw = self._call_llm(force_final)
                        obj = parse_action_json(raw)
                        return {
                            "final_answer": obj.get("answer", ""),
                            "steps": steps,
                            "terminated": "invalid_tool",
                        }

                # Enforce YouTube-only-once policy
                if self.youtube_once and tool == "youtube_search":
                    if youtube_calls >= 1:
                        observation = (
                            "Policy: YouTube search has already been called once this conversation."
                        )
                        steps.append((tool, tool_input, observation))
                        # Give the model a chance to proceed with other steps
                        continue
                    youtube_calls += 1

                # Execute tool
                try:
                    observation_full = TOOLS[tool]["call"](tool_input)
                    observation_str = str(observation_full)
                except Exception as e:
                    observation_str = f"[ToolError] {type(e).__name__}: {e}"

                # Truncate very long observations to control token usage
                if len(observation_str) > self.truncate_obs:
                    observation_str = observation_str[: self.truncate_obs] + " ... [truncated]"

                steps.append((tool, tool_input, observation_str))
                continue

            # Unknown type → request final answer
            if self.verbose:
                print("[Policy] Unknown decision type. Forcing final answer.\n")
            raw = self._call_llm('{"type":"final","answer":"Please provide the final answer."}')
            try:
                obj = parse_action_json(raw)
            except Exception:
                obj = {"type": "final", "answer": "Unable to parse model output. Ending."}
            return {
                "final_answer": obj.get("answer", ""),
                "steps": steps,
                "terminated": "unknown_type",
            }

        # Exceeded max steps → ask for final answer based on scratchpad
        scratchpad_text = format_scratchpad(steps)
        final_prompt = f"""
You have reached the maximum steps. Using the scratchpad below, return a SINGLE JSON object:
{{"type":"final","answer":"..."}}

Scratchpad:
{scratchpad_text}
        """.strip()
        raw = self._call_llm(final_prompt)
        try:
            obj = parse_action_json(raw)
            ans = obj.get("answer", "")
        except Exception:
            ans = "Max steps reached. Ending with best effort."
        return {
            "final_answer": ans,
            "steps": steps,
            "terminated": "max_steps",
        }




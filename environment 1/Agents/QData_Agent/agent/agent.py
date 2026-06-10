import json
import uuid
import logging
import json_repair
from typing import Dict, Any, List, Tuple
from mcp import ClientSession
from agent.audit import LangSmithAudit

logger = logging.getLogger(__name__)

# ── System Prompt ─────────────────────────────────────────────────────────────
def build_system_prompt(tools: list) -> str:
    tool_docs = "\n".join(
        f"- {t['name']}: {t['description']}"
        for t in tools
    )
    return f"""You are a data analyst assistant that solves tasks step by step.

Available tools:
{tool_docs}

Rules:
- ALWAYS respond with a SINGLE JSON object and NOTHING ELSE.
- To use a tool:
  {{"type": "action", "tool": "<tool_name>", "input": {{<input dict>}}}}
- To give final answer:
  {{"type": "final", "answer": "<your answer>"}}
- No markdown, no code fences — pure JSON only.
- For CSV tasks: always call tool_inspect_source_schema first, then
  tool_query_source for simple reads, or tool_load_source_into_temp
  + tool_query_temp for multi-step work or joins."""

# ── JSON Parser ───────────────────────────────────────────────────────────────
def parse_json(raw: str) -> Dict[str, Any]:
    result = json_repair.repair_json(raw, return_objects=True)
    if isinstance(result, dict):
        return result
    raise ValueError(f"Could not parse: {raw[:200]}")

# ── Scratchpad Formatter ──────────────────────────────────────────────────────
def format_scratchpad(steps: List[Tuple[str, str, str]]) -> str:
    buf = []
    for idx, (act, inp, obs) in enumerate(steps, start=1):
        buf.append(f"Step {idx}")
        buf.append(f"Thought: I decided to use the '{act}' tool.")
        buf.append(f"Action: {act}")
        buf.append(f"Action Input: {inp}")
        buf.append(f"Observation: {obs}")
        buf.append("")
    return "\n".join(buf)

# ── Fully Custom Agent ────────────────────────────────────────────────────────
class FullyCustomAgent:
    def __init__(
        self,
        llm,
        session_id:   str,
        max_steps:    int = 8,
        truncate_obs: int = 1500,
    ):
        self.llm          = llm
        self.session_id   = session_id
        self.max_steps    = max_steps
        self.truncate_obs = truncate_obs
        self.audit        = LangSmithAudit(session_id)

    def _call_llm(self, messages: list) -> str:
        out = self.llm.invoke(messages)
        if hasattr(out, "content"):
            return out.content
        return str(out)

    def _build_messages(
        self,
        user_query:    str,
        history:       list,
        steps:         List[Tuple[str, str, str]],
        system_prompt: str,
    ) -> list:
        # Build scratchpad from all steps so far
        scratchpad_text = format_scratchpad(steps)

        messages = [{"role": "system", "content": system_prompt}]

        # Inject full conversation history
        for h in history:
            messages.append(h)

        messages.append({"role": "user", "content": user_query})

        # Scratchpad injected as assistant turn so LLM knows what it already did
        if scratchpad_text.strip():
            messages.append({
                "role":    "assistant",
                "content": f"Scratchpad so far:\n{scratchpad_text}"
            })

        return messages

    async def run(
        self,
        user_query:      str,
        history:         List[Dict],
        mcp_session:     ClientSession,   # ← MCP session passed in from client
        available_tools: list,
    ) -> Dict[str, Any]:

        steps      = []
        run_id     = str(uuid.uuid4())
        tool_names = [t["name"] for t in available_tools]
        system_prompt = build_system_prompt(available_tools)

        for step_idx in range(1, self.max_steps + 1):

            # ── Build messages with full scratchpad ───────────────────────────
            messages = self._build_messages(user_query, history, steps, system_prompt)
            raw      = self._call_llm(messages)
            logger.debug("Step %d raw output: %s", step_idx, raw)

            # ── Parse JSON decision ───────────────────────────────────────────
            try:
                obj = parse_json(raw)
            except Exception as e:
                logger.warning("JSON parse failed at step %d: %s", step_idx, e)
                steps.append(("parse_error", raw[:100], f"JSON parse error: {e}"))
                continue

            typ = obj.get("type")

            # ── Final answer ──────────────────────────────────────────────────
            if typ == "final":
                answer = obj.get("answer", "").strip()
                self.audit.log_run(user_query, answer, steps, "final_answer", run_id)
                return {
                    "final_answer": answer,
                    "steps":        steps,
                    "terminated":   "final_answer",
                    "run_id":       run_id,
                }

            # ── Tool action ───────────────────────────────────────────────────
            if typ == "action":
                tool_name  = obj.get("tool", "")
                tool_input = obj.get("input", {})

                # Ensure input is always a dict
                if isinstance(tool_input, str):
                    try:
                        tool_input = json.loads(tool_input)
                    except Exception:
                        tool_input = {"input": tool_input}

                # Invalid tool → inject as observation, LLM self-corrects naturally
                if tool_name not in tool_names:
                    steps.append((
                        tool_name, str(tool_input),
                        f"Invalid tool '{tool_name}'. Available: {tool_names}"
                    ))
                    continue

                # Auto-inject session_id for tools that need it
                tool_schema = next(
                    (t["input_schema"] for t in available_tools if t["name"] == tool_name), {}
                )
                if "session_id" in tool_schema.get("properties", {}):
                    tool_input["session_id"] = self.session_id

                # ── Call tool via MCP server (only this line touches MCP) ─────
                try:
                    result      = await mcp_session.call_tool(tool_name, tool_input)
                    observation = str(result.content[0].text if result.content else "No result")
                except Exception as e:
                    observation = f"ToolError: {type(e).__name__}: {e}"

                if len(observation) > self.truncate_obs:
                    observation = observation[:self.truncate_obs] + " ... [truncated]"

                # Append to scratchpad — next iteration LLM sees this
                steps.append((tool_name, str(tool_input), observation))
                continue

            # ── Unknown type → inject as observation, keep loop alive ─────────
            steps.append((
                "unknown_type", str(obj),
                "Unknown response type. Respond with 'action' or 'final' only."
            ))
            continue

        # ── Max steps reached — ask LLM for best effort final answer ──────────
        logger.warning("Max steps (%d) reached for query: %s", self.max_steps, user_query)
        messages = self._build_messages(user_query, history, steps, system_prompt)
        messages.append({
            "role":    "user",
            "content": "Max steps reached. Give your best final answer now as JSON: {\"type\":\"final\",\"answer\":\"...\"}"
        })
        raw = self._call_llm(messages)
        try:
            ans = parse_json(raw).get("answer", "Max steps reached.")
        except Exception:
            ans = "Max steps reached. Could not produce final answer."

        self.audit.log_run(user_query, ans, steps, "max_steps", run_id)
        return {
            "final_answer": ans,
            "steps":        steps,
            "terminated":   "max_steps",
            "run_id":       run_id,
        }

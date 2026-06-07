import asyncio
import uuid
import json
import os
import json_repair
import logging
from typing import Dict, Any, List, Tuple
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
from langchain_openai import ChatOpenAI
from langsmith import Client
from agent.audit import LangSmithAudit
from agent.classifier import classify_intent
from core.duckdb_runner import cleanup_session
from config import SOURCE_FOLDER

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
smith  = Client()

# ── MCP Server connection config ──────────────────────────────────────────────
MCP_SERVER_URL   = os.environ.get("MCP_SERVER_URL",   "http://localhost:8000/mcp")
MCP_AUTH_TOKEN   = os.environ.get("MCP_AUTH_TOKEN",   "your-secret-token")

# Auth headers passed on every request to MCP server
MCP_AUTH_HEADERS = {
    "Authorization": f"Bearer {MCP_AUTH_TOKEN}"
}

# ── JSON Parser ───────────────────────────────────────────────────────────────
def parse_json(raw: str) -> Dict[str, Any]:
    result = json_repair.repair_json(raw, return_objects=True)
    if isinstance(result, dict):
        return result
    raise ValueError(f"Could not parse: {raw[:200]}")

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

# ── DataForge Agent ───────────────────────────────────────────────────────────
class DataForgeAgent:
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
        steps:         List,
        system_prompt: str,
    ) -> list:
        scratchpad = ""
        for i, (act, inp, obs) in enumerate(steps, 1):
            scratchpad += (
                f"\nStep {i}\n"
                f"Action: {act}\n"
                f"Input: {inp}\n"
                f"Observation: {obs}\n"
            )
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append(h)
        messages.append({"role": "user", "content": user_query})
        if scratchpad:
            messages.append({"role": "assistant", "content": f"Scratchpad:{scratchpad}"})
        return messages

    async def run(
        self,
        user_query:      str,
        history:         List[Dict],
        mcp_session:     ClientSession,
        available_tools: list,
    ) -> Dict[str, Any]:

        steps         = []
        run_id        = str(uuid.uuid4())
        tool_names    = [t["name"] for t in available_tools]
        system_prompt = build_system_prompt(available_tools)

        for step_idx in range(1, self.max_steps + 1):
            messages = self._build_messages(user_query, history, steps, system_prompt)
            raw      = self._call_llm(messages)
            logger.debug("Step %d: %s", step_idx, raw)

            # ── Parse JSON ────────────────────────────────────────────────────
            try:
                obj = parse_json(raw)
            except Exception as e:
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

                # Invalid tool → inject as observation, LLM self-corrects
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

                # ── Call tool via MCP server (streamable HTTP) ────────────────
                try:
                    result      = await mcp_session.call_tool(tool_name, tool_input)
                    observation = str(result.content[0].text if result.content else "No result")
                except Exception as e:
                    observation = f"ToolError: {type(e).__name__}: {e}"

                if len(observation) > self.truncate_obs:
                    observation = observation[:self.truncate_obs] + " ... [truncated]"

                steps.append((tool_name, str(tool_input), observation))
                continue

            # ── Unknown type → inject as observation, keep loop alive ─────────
            steps.append((
                "unknown_type", str(obj),
                "Unknown response type. Use 'action' or 'final' only."
            ))
            continue

        # ── Max steps reached ─────────────────────────────────────────────────
        logger.warning("Max steps reached for query: %s", user_query)
        messages = self._build_messages(user_query, history, steps, system_prompt)
        messages.append({
            "role":    "user",
            "content": "Max steps reached. Give your best final answer as JSON: {\"type\":\"final\",\"answer\":\"...\"}"
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


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    session_id     = str(uuid.uuid4())
    history        = []
    last_run_id    = None

    llm            = ChatOpenAI(model="gpt-4o",      temperature=0, max_tokens=2000)
    classifier_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=20)
    agent          = DataForgeAgent(llm=llm, session_id=session_id)
    audit          = LangSmithAudit(session_id=session_id)

    print(f"Session    : {session_id}")
    print(f"Source     : {SOURCE_FOLDER.resolve()}")
    print(f"MCP Server : {MCP_SERVER_URL}")
    print("Connecting to MCP server...\n")

    # ── Connect to MCP server via Streamable HTTP with auth headers ───────────
    async with streamablehttp_client(
        url     = MCP_SERVER_URL,
        headers = MCP_AUTH_HEADERS,      # Bearer token sent on every request
    ) as (read, write, _):
        async with ClientSession(read, write) as mcp_session:

            # ── Initialize and discover tools from server ─────────────────────
            await mcp_session.initialize()
            tools_response  = await mcp_session.list_tools()
            available_tools = [
                {
                    "name":         t.name,
                    "description":  t.description,
                    "input_schema": t.inputSchema,
                }
                for t in tools_response.tools
            ]

            print(f"Tools available from server ({len(available_tools)}):")
            for t in available_tools:
                print(f"  - {t['name']}")
            print()

            try:
                while True:
                    user_input = input("You: ").strip()
                    if not user_input:
                        continue
                    if user_input.lower() == "exit":
                        break

                    intent = classify_intent(user_input, classifier_llm)

                    if intent == "POSITIVE_FEEDBACK" and last_run_id:
                        audit.log_feedback(last_run_id, score=1.0, comment=user_input)
                        print("Bot: Glad that helped!\n")
                        continue

                    if intent == "NEGATIVE_FEEDBACK" and last_run_id:
                        audit.log_feedback(last_run_id, score=0.0, comment=user_input)
                        print("Bot: Sorry! What were you looking for exactly?\n")
                        continue

                    result      = await agent.run(
                        user_input, history, mcp_session, available_tools
                    )
                    last_run_id = result["run_id"]

                    history.append({"role": "user",      "content": user_input})
                    history.append({"role": "assistant",  "content": result["final_answer"]})

                    print(f"Bot: {result['final_answer']}\n")

            finally:
                cleanup_session(session_id)
                print("Session cleaned up.")


if __name__ == "__main__":
    asyncio.run(main())

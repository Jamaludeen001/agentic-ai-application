import asyncio
import uuid
import os
import logging
from typing import Dict, List
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
from langchain_openai import ChatOpenAI
from langsmith import Client
from agent.agent import FullyCustomAgent
from agent.audit import LangSmithAudit
from agent.classifier import classify_intent
from core.duckdb_runner import cleanup_session
from config import SOURCE_FOLDER

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
smith  = Client()

# ── MCP Server connection config ──────────────────────────────────────────────
MCP_SERVER_URL   = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/mcp")
MCP_AUTH_TOKEN   = os.environ.get("MCP_AUTH_TOKEN", "your-secret-token")
MCP_AUTH_HEADERS = {"Authorization": f"Bearer {MCP_AUTH_TOKEN}"}

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    session_id     = str(uuid.uuid4())
    history        = []
    last_run_id    = None

    llm            = ChatOpenAI(model="gpt-4o",      temperature=0, max_tokens=2000)
    classifier_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=20)
    agent          = FullyCustomAgent(llm=llm, session_id=session_id)
    audit          = LangSmithAudit(session_id=session_id)

    print(f"Session    : {session_id}")
    print(f"Source     : {SOURCE_FOLDER.resolve()}")
    print(f"MCP Server : {MCP_SERVER_URL}")
    print("Connecting to MCP server...\n")

    async with streamablehttp_client(
        url     = MCP_SERVER_URL,
        headers = MCP_AUTH_HEADERS,
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

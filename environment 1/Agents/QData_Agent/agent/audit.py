import logging
from typing import List, Tuple
from langsmith import Client

logger = logging.getLogger(__name__)
smith  = Client()

class LangSmithAudit:
    def __init__(self, session_id: str, project: str = "dataforge"):
        self.session_id = session_id
        self.project    = project

    def log_run(self, user_query: str, final_answer: str, steps: List[Tuple], terminated: str, run_id: str):
        try:
            smith.create_run(
                id           = run_id,
                name         = "dataforge-turn",
                run_type     = "chain",
                project_name = self.project,
                inputs       = {"user_query": user_query, "session_id": self.session_id},
                outputs      = {"final_answer": final_answer, "terminated": terminated},
                extra        = {"metadata": {"session_id": self.session_id, "tools_used": [s[0] for s in steps], "steps_count": len(steps)}},
            )
            for i, (tool_name, tool_input, observation) in enumerate(steps):
                smith.create_run(
                    name          = f"tool-{tool_name}",
                    run_type      = "tool",
                    project_name  = self.project,
                    parent_run_id = run_id,
                    inputs        = {"tool": tool_name, "input": tool_input},
                    outputs       = {"observation": observation[:500]},
                    extra         = {"metadata": {"step": i + 1}},
                )
        except Exception as e:
            logger.warning("LangSmith log failed: %s", e)

    def log_feedback(self, run_id: str, score: float, comment: str = ""):
        try:
            smith.create_feedback(run_id=run_id, key="user-feedback", score=score, comment=comment)
        except Exception as e:
            logger.warning("LangSmith feedback failed: %s", e)

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.workflows.adk_workflow import _triage_agent as root_agent

__all__ = ["root_agent"]

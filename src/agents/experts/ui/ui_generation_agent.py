from google.adk.agents import BaseAgent, LlmAgent, ParallelAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.tools import ToolContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.sessions import InMemorySessionService
from google.adk.models import LlmRequest
from src.llm.model_factory import build_model_and_config
from google.genai.types import Part
from google.genai.types import Content

from conf.system import SYS_CONFIG
from src.logger import logger
from src.agents.experts.ui.ui_keyword_extractor import UIKeywordsExtractorAgent
from src.agents.experts.ui.ui_code_generation import UICodeGenerationAgent

ui_generation_agent = SequentialAgent(
    name="UIGenerationAgent",
    sub_agents=[UIKeywordsExtractorAgent(name="UIKeywordsExtractorAgent"),
                UICodeGenerationAgent(name="UICodeGenerationAgent"),
                ]
)

# import asyncio
# import uuid
# from typing_extensions import override
from typing import AsyncGenerator, List

# from google.adk.agents import LlmAgent
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
from src.agents.experts.article_v2.article_draft_agent import ArticleDraftAgent
from src.agents.experts.article_v2.article_image_generation_agent import ArticleImageGenerationAgent
from src.agents.experts.article_v2.article_finalize_agent import ArticleFinalizeAgent

article_generation_agent_v2 = SequentialAgent(
    name="ArticleGenerationAgentv2",
    sub_agents=[ArticleDraftAgent(name="ArticleDraftAgent"),
                ArticleImageGenerationAgent(name="ArticleImageGenerationAgent"),
                ArticleFinalizeAgent(name="ArticleFinalizeAgent")
                ]
)
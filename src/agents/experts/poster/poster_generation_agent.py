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
from src.agents.experts.poster.poster_draft_agent import PosterDraftAgent
from src.agents.experts.poster.poster_image_generation_agent import PosterImageGenerationAgent
from src.agents.experts.poster.poster_finalize_agent import PosterFinalizeAgent
from src.agents.experts.poster.poster_image_combine_agent import PosterImageCombineAgent


poster_generation_agent = SequentialAgent(
    name="PosterGenerationAgent",
    sub_agents=[PosterDraftAgent(name="PosterDraftAgent"),
                PosterImageCombineAgent(name="PosterImageCombineAgent"),
                PosterImageGenerationAgent(name="PosterImageGenerationAgent"),
                PosterFinalizeAgent(name="PosterFinalizeAgent")
                ]
)
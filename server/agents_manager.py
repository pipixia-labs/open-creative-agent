import os

from conf.system import SYS_CONFIG
from conf.agent import expert_name_2_desc
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from src.custom_session_service import build_session_service
from src.logger import logger

from src.agents.experts import (
    ImageGenerationAndEditingAgent,
    ImageProcessingAgent,
    ImageGenerationAgent,
    ReasoningImageGenerationAgent,
    VideoGenerationAgent,
    SearchAgent,
    ReadArtifactAgent,
    ImageUnderstandingAgent,
    ImageToPromptAgent,
    ArtKnowledgeAgent,
    ExtractorAgent,
    SearchQueryAgent,
    HTMLGenerationAgent,
    HTMLToImageAgent,
    ScienceAgent,
    AdTextElementGenerationAgent,
    page_generation_by_reference_agent,
    article_generation_agent_v2,
    poster_generation_agent,
    ui_generation_agent
)


db_path = os.path.join(SYS_CONFIG.session_database_dir, "session_database.db")
db_url = f"sqlite+aiosqlite:///{db_path}?timeout=30"

session_service = build_session_service(db_url, logger=logger)
artifact_service = InMemoryArtifactService()


def _description(agent_name: str) -> str:
    """Return the configured description for an expert agent."""
    return expert_name_2_desc[agent_name]


image_generation_agent = ImageGenerationAgent(
    name="ImageGenerationAgent",
    description=_description("ImageGenerationAgent"),
)
reasoning_image_generation_agent = ReasoningImageGenerationAgent(
    name="ReasoningImageGenerationAgent",
    description=_description("ReasoningImageGenerationAgent"),
)
video_generation_agent = VideoGenerationAgent(
    name="VideoGenerationAgent",
    description=_description("VideoGenerationAgent"),
)
image_generation_and_editing_agent = ImageGenerationAndEditingAgent(
    name="ImageGenerationAndEditingAgent",
    description=_description("ImageGenerationAndEditingAgent"),
)
image_processing_agent = ImageProcessingAgent(
    name="ImageProcessingAgent",
    description=_description("ImageProcessingAgent"),
)
image_understanding_agent = ImageUnderstandingAgent(
    name="ImageUnderstandingAgent",
    description=_description("ImageUnderstandingAgent"),
)
search_agent = SearchAgent(
    name="SearchAgent",
    max_search_count=SYS_CONFIG.max_search_count,
    description=_description("SearchAgent"),
)
art_knowledge_agent = ArtKnowledgeAgent(
    name="ArtKnowledgeAgent",
    description=_description("ArtKnowledgeAgent"),
    llm_model=SYS_CONFIG.art_knowledge_llm_model,
)
extractor_agent = ExtractorAgent(
    name="ExtractorAgent",
    description=_description("ExtractorAgent"),
    llm_model=SYS_CONFIG.llm_model,
)
read_artifact_agent = ReadArtifactAgent(
    name="ReadArtifactAgent",
    description=_description("ReadArtifactAgent"),
    llm_model=SYS_CONFIG.llm_model,
)
search_query_agent = SearchQueryAgent(
    name="SearchQueryAgent",
    description=_description("SearchQueryAgent"),
    llm_model=SYS_CONFIG.llm_model,
)
html_generation_agent = HTMLGenerationAgent(
    name="HTMLGenerationAgent",
    description=_description("HTMLGenerationAgent"),
    llm_model=SYS_CONFIG.html_gen_llm_model,
)
html_to_image = HTMLToImageAgent(
    name="HTMLToImageAgent",
    description=_description("HTMLToImageAgent"),
)
science_agent = ScienceAgent(
    name="ScienceAgent",
    description=_description("ScienceAgent"),
    llm_model=SYS_CONFIG.science_llm_model,
)
ad_element_generation_agent = AdTextElementGenerationAgent(
    name="AdTextElementGenerationAgent",
    description=_description("AdTextElementGenerationAgent"),
    llm_model=SYS_CONFIG.llm_model,
)
image_to_prompt_agent = ImageToPromptAgent(
    name="ImageToPromptAgent",
    description=_description("ImageToPromptAgent"),
)


# Keys must match the names in conf/jsons/agent.json.
expert_agents = {
    "ImageGenerationAgent": image_generation_agent,
    "ReasoningImageGenerationAgent": reasoning_image_generation_agent,
    "VideoGenerationAgent": video_generation_agent,
    "ImageGenerationAndEditingAgent": image_generation_and_editing_agent,
    "ImageProcessingAgent": image_processing_agent,
    "ImageUnderstandingAgent": image_understanding_agent,
    "ImageToPromptAgent": image_to_prompt_agent,
    "ArtKnowledgeAgent": art_knowledge_agent,
    "SearchAgent": search_agent,
    "ExtractorAgent": extractor_agent,
    "ReadArtifactAgent": read_artifact_agent,
    "SearchQueryAgent": search_query_agent,
    "HTMLGenerationAgent": html_generation_agent,
    "HTMLToImageAgent": html_to_image,
    "ScienceAgent": science_agent,
    "AdTextElementGenerationAgent": ad_element_generation_agent,
    "ArticleGenerationAgentv2": article_generation_agent_v2,
    "PosterGenerationAgent": poster_generation_agent,
    "PageGenerationByReferenceAgent": page_generation_by_reference_agent,
    "UIGenerationAgent": ui_generation_agent,
}


expert_runners = {
    name: Runner(
        agent=agent,
        app_name=SYS_CONFIG.app_name,
        session_service=session_service,
        artifact_service=artifact_service,
    )
    for name, agent in expert_agents.items()
}

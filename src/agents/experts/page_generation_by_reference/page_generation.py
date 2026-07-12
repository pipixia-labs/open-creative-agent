from google.adk.agents import SequentialAgent

from src.agents.experts.page_generation_by_reference.pgbr_draft_agent import PGBRDraftAgent
from src.agents.experts.page_generation_by_reference.pgbr_image_generation_agent import (
    PGBRImageGenerationAgent,
)
from src.agents.experts.page_generation_by_reference.pgbr_finalize_agent import PGBRFinalizeAgent
from src.agents.experts.page_generation_by_reference.pgbr_html_to_image_agent import (
    PGBRHTMLToImageAgent,
)
from src.agents.experts.page_generation_by_reference.pgbr_design_element_analysis_agent import (
    PGBRDesignElementAnalysisAgent,
)
from src.agents.experts.page_generation_by_reference.page_quality_analysis_agent import (
    PGBRQualityAnalysisAgent,
)


page_generation_by_reference_agent = SequentialAgent(
    name="PageGenerationByReferenceAgent",
    sub_agents=[
        PGBRDesignElementAnalysisAgent(name="PGBRDesignElementAnalysisAgent"),
        PGBRDraftAgent(name="PGBRDraftAgent"),
        PGBRImageGenerationAgent(name="PGBRImageGenerationAgent"),
        PGBRFinalizeAgent(name="PGBRFinalizeAgent"),
        PGBRHTMLToImageAgent(name="PGBRHTMLToImageAgent"),
        PGBRQualityAnalysisAgent(name="PGBRQualityAnalysisAgent"),
        PGBRFinalizeAgent(name="PGBRFinalizeAgentRevision"),
        PGBRHTMLToImageAgent(name="PGBRHTMLToImageAgentRevision"),
    ],
)

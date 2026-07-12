import os
import json5

from pydantic import BaseModel
from conf.path import CONF_ROOT


class RootAgentConfig(BaseModel):
    """
    Root agent configuration model.
    """

    name: str
    model: str
    description: str  # Description of the root agent's purpose
    instruction: str  # Teach the LLM how & when to delegate tasks to sub-agents
    sub_agents: list[str]  # List of sub-agent names
    tools: list[str]  # List of tool names available to the root agent

    def __str__(self) -> str:
        return (
            f"**{self.name}**\n"
            f"**Description:** {self.description}\n"
            f"**Instruction:** {self.instruction}\n"
            f"**Sub-agents:** {', '.join(self.sub_agents)}\n"
            f"**Tools:** {', '.join(self.tools)}"
        )


class ExpertAgentConfig(BaseModel):
    """
    Agent configuration model.
    """

    name: str  # Name of the expert agent
    enable: bool  # Whether the agent is enabled or not
    description: str
    parameters: str

    def __str__(self) -> str:
        return (
            (f"- **{self.name}**：\n"
            f"- 功能描述：{self.description}\n"
            f"- `parameters`: {self.parameters}\n" 
            )
            if self.enable
            else f"**{self.name}** (Disabled)"
        )


def load_agent_configs(
    config_file_path: str,
) -> tuple[list[RootAgentConfig], list[ExpertAgentConfig]]:
    """
    Load agent configurations from a JSON file.
    Args:
        config_file_path (str): Path to the JSON configuration file.
    Returns:
        tuple: A tuple containing two lists:
            - List of RootAgentConfig objects.
            - List of ExpertAgentConfig objects.
    Raises:
        FileNotFoundError: If the configuration file does not exist.
        json.JSONDecodeError: If the configuration file is not a valid JSON.
    """
    if not os.path.exists(config_file_path):
        raise FileNotFoundError(f"Configuration file not found: {config_file_path}")

    with open(config_file_path, "r", encoding="utf-8") as file:
        data = json5.load(file)

    # print(data)
    root_agents = [RootAgentConfig(**agent) for agent in data.get("root_agent", [])]
    expert_agents = [
        ExpertAgentConfig(**agent) for agent in data.get("expert_agents", [])
    ]

    return root_agents, expert_agents


experts_list: list[ExpertAgentConfig] = load_agent_configs(
    os.path.join(CONF_ROOT, "jsons/agent.json")
)[1]

expert_name_2_desc = {}
for e in experts_list:
    expert_name_2_desc[e.name] = e.description + '\n input parameters:' + e.parameters + '\n'
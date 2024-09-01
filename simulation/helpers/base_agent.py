from typing import Any, Optional, Union, Sequence
from loguru import logger
import requests

from agentscope.agents import AgentBase
from agentscope.message import Msg
from agentscope.manager import ModelManager
from agentscope.rpc import async_func

from simulation.helpers.constants import *
from simulation.helpers.utils import get_memory_until_limit, get_assistant_msg, setup_memory


class BaseAgent(AgentBase):
    """Base agent."""

    def __init__(self, 
                name: str, 
                model_config_name: str=None, 
                **kwargs) -> None:
        super().__init__(
            name=name,
            model_config_name=model_config_name,
        )
        self._profile = ""
        self.backend_server_url = "http://localhost:9000"

    def _send_message(self, prompt, response):
        if hasattr(self, "backend_server_url"):
            url = f"{self.backend_server_url}/api/message"
            resp = requests.post(
                url,
                json={
                    "name": self.name,
                    "prompt": "\n".join([p["content"] for p in prompt]),
                    "completion": response.text,
                    "agent_type": type(self).__name__,
                    "agent_id": self.agent_id,
                },
            )
            if resp.status_code != 200:
                logger.error(f"Failed to send message: {self.agent_id}")

    @property
    def profile(self):
        return self._profile

    def __getstate__(self) -> object:
        state = self.__dict__.copy()
        state.pop("model", None)
        if hasattr(self, "memory"):
            memory_state = self.memory.__dict__.copy()
            memory_state["model"] = None
            state["memory"] = memory_state
        return state

    def __setstate__(self, state: object) -> None:
        self.__dict__.update(state)
        if hasattr(self, "memory_config"):
            self.memory = setup_memory(self.memory_config)
            self.memory.__dict__.update(state["memory"])
        if hasattr(self, "model_config_name"):
            self.model = ModelManager.get_instance().get_model_by_config_name(
                self.model_config_name
            )
            self.memory.model = self.model

    @async_func
    def set_attr(self, attr: str, value: Any, **kwargs):
        attrs = attr.split(".")
        obj = self
        for attr in attrs[:-1]:
            obj = getattr(obj, attr)
        setattr(obj, attrs[-1], value)
        return "success"

    def get_attr(self, attr: str):
        return getattr(self, attr)

    def external_interview(self, observation, **kwargs):
        instruction = "You are participating in a simple interview where you need to answer some questions."
        observation = "Question:" + observation + "Answer:"
        msg = get_assistant_msg()
        msg.instruction = instruction
        msg.observation = observation
        msg.no_memory = True
        response = self(msg).content
        return response

    def session_chat(self, announcement, participants, **kwargs):
        MAX_CONVERSATION_NUM = 2
        msg = get_assistant_msg()
        msg.instruction = announcement
        msg.observation = "\nThe dialogue proceeds as follows:\n"
        msg.no_memory = True
        for _ in range(MAX_CONVERSATION_NUM):
            for p in participants:
                msg.observation += f"{p.name}:"
                response = self(msg).content
                msg.observation += response + "\n"
        return msg.observation

    def script_chat(self, announcement, participants, **kwargs):
        format_instruction = INSTRUCTION_BEGIN + announcement + INSTRUCTION_END
        profile = ""
        for p in participants:
            profile += "\n" + p.name + ": " + p.profile
        format_profile = PROFILE_BEGIN + profile + PROFILE_END
        memory = ""
        for p in participants:
            memory_msgs = get_memory_until_limit(memory, format_instruction + format_profile + memory)
            memory_content = "-\n".join([m.content for m in memory_msgs])
            memory += "\n" + p.name + ": " + memory_content
        format_memory = MEMORY_BEGIN + memory + MEMORY_END
        observation = "The dialogue proceeds as follows:\n"
        response = self.model(self.model.format(get_assistant_msg(
            format_instruction + format_profile + format_memory + observation)))
        return response.text
    
    def chat(self, announcement, participants, mode="session", **kwargs):
        if mode == "session":
            return self.session_chat(announcement, participants, **kwargs)
        elif mode == "script":
            return self.script_chat(announcement, participants, **kwargs)
        
    def post(self, content, participants, **kwargs):
        for p in participants:
            p.observe(get_assistant_msg(f"{self.name} posted: {content}"))
        return content
    
    def reply(self, x: Optional[Union[Msg, Sequence[Msg]]] = None) -> Msg:
        instruction = ""
        format_instruction = ""
        format_profile = PROFILE_BEGIN + self._profile + PROFILE_END
        observation = ""
        prompt_content = []
        memory_query = ""
        if x and hasattr(x, "instruction"):
            instruction = x.instruction
            memory_query += instruction
            format_instruction = INSTRUCTION_BEGIN + instruction + INSTRUCTION_END
            prompt_content.append(format_instruction)

        prompt_content.append(format_profile)

        if x and hasattr(x, "observation"):
            observation = x.observation
            memory_query += observation
            prompt_content.append(observation)

        if x and x.content:
            memory_query += x.content
            prompt_content.append(x.content)

        memory = self.memory.get_memory(get_assistant_msg(memory_query))
        if len(memory) > 0:
            insert_index = -2 if len(prompt_content) > 1 else -1
            memory_msgs = get_memory_until_limit(memory, "\n".join(prompt_content))
            memory_content = "-\n".join([m.content for m in memory_msgs])
            prompt_content.insert(insert_index, MEMORY_BEGIN + memory_content + MEMORY_END)

        prompt_content = "\n".join(prompt_content)

        prompt_msg = self.model.format(Msg(
            "user", 
            prompt_content, 
            role="user"
        ))
        response = self.model(prompt_msg)

        self._send_message(prompt_msg, response)
        add_memory_msg = Msg("user", instruction + observation + response.text, role="user")
        if not hasattr(x, "no_memory"):
            self.observe(add_memory_msg)
        return get_assistant_msg(response.text)
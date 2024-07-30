from typing import List, Optional
from pydantic import BaseModel, Field
import queue


class MessageUnit(BaseModel):
    msg_id: Optional[int] = None
    agent_id: int
    name: str
    agent_type: str
    query: str = Field(..., serialization_alias="prompt")
    response: str = Field(..., serialization_alias="completion")
    rewritten_response: Optional[str] = Field(None, serialization_alias="completion")
    rating: Optional[int] = Field(None, serialization_alias="reward")


class StateUnit(BaseModel):
    agent_id: int
    state: str


class MessageManager:
    def __init__(self):
        self.messages: List[MessageUnit] = []
        self.message_queue = queue.Queue()
        self.state_queue = queue.Queue()

    def add_message(self, message: MessageUnit):
        from backend.app import lock
        from simulation.helpers.events import check_pause

        check_pause()
        with lock:
            self.messages.append(message)
        self.message_queue.put(message)

    def add_state(self, state: StateUnit):
        self.state_queue.put(state)

    def clear(self):
        from backend.app import lock

        with lock:
            self.messages.clear()
        self.message_queue = queue.Queue()
        self.state_queue = queue.Queue()


message_manager = MessageManager()

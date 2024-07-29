from pydantic import BaseModel
import queue


class MessageUnit(BaseModel):
    agent_id: int
    name: str
    agent_type: str
    prompt: str
    completion: str


class StateUnit(BaseModel):
    agent_id: int
    state: str


class MessageManager:
    def __init__(self):
        self.messages = []
        self.message_queue = queue.Queue()
        self.state_queue = queue.Queue()

    def add_message(self, message: MessageUnit):
        self.messages.append(message)
        self.message_queue.put(message)
    
    def add_state(self, state: StateUnit):
        self.state_queue.put(state)

    async def clear(self):
        from backend.app import lock

        async with lock:
            self.messages.clear()
        self.message_queue = queue.Queue()
        self.state_queue = queue.Queue()


message_manager = MessageManager()

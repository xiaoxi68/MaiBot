import enum


class ChatState(enum.Enum):
    ABSENT = "没在看群"
    NORMAL = "随便水群"
    FOCUSED = "认真水群"


class ChatStateInfo:
    def __init__(self):
        self.chat_status: ChatState = ChatState.NORMAL
        self.current_state_time = 120

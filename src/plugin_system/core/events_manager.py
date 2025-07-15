from typing import List, Dict, Type

from src.plugin_system.base.component_types import EventType


class EventsManager:
    def __init__(self):
        # 有权重的 events 订阅者注册表
        self.events_subscribers: Dict[EventType, List[Dict[int, Type]]] = {event: [] for event in EventType}

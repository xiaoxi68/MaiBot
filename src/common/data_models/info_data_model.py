from dataclasses import dataclass, field
from typing import Optional

@dataclass
class TargetPersonInfo:
    platform: str = field(default_factory=str)
    user_id: str = field(default_factory=str)
    user_nickname: str = field(default_factory=str)
    person_id: Optional[str] = None
    person_name: Optional[str] = None
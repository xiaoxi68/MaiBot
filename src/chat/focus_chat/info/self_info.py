from dataclasses import dataclass
from .info_base import InfoBase


@dataclass
class SelfInfo(InfoBase):
    """思维信息类

    用于存储和管理当前思维状态的信息。

    Attributes:
        type (str): 信息类型标识符，默认为 "mind"
        data (Dict[str, Any]): 包含 current_mind 的数据字典
    """

    type: str = "self"

    def get_self_info(self) -> str:
        """获取当前思维状态

        Returns:
            str: 当前思维状态
        """
        return self.get_info("self_info") or ""

    def set_self_info(self, self_info: str) -> None:
        """设置当前思维状态

        Args:
            self_info: 要设置的思维状态
        """
        self.data["self_info"] = self_info

    def get_processed_info(self) -> str:
        """获取处理后的信息

        Returns:
            str: 处理后的信息
        """
        return self.get_self_info() or ""

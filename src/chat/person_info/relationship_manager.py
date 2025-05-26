from model_manager.person_info import PersonInfoDTO, PersonInfoManager
from src.common.logger_manager import get_logger
import math
import random

from ...manager.mood_manager import mood_manager

# import re
# import traceback


logger = get_logger("relation")

STANCE_MAP = {
    "支持": 0,
    "中立": 1,
    "反对": 2,
}
"""立场映射"""

ATTITUDE_MAP = {
    "喜爱": 2.0,
    "高兴": 1.5,
    "惊讶": 0.8,
    "中性": 0.0,
    "悲伤": -0.5,
    "恐惧": -1.0,
    "愤怒": -2.5,
    "厌恶": -3.5,
}
"""情绪映射

“毁掉一段关系比建立一段关系要容易得多”——OctAutumn
"""

RELATIONSHIP_LEVEL = [
    (-1000, -227, "厌恶", "厌恶", "忽视的回应"),
    (-227, -73, "冷漠", "冷漠以对", "冷淡回复"),
    (-73, 227, "一般", "认识", "保持理性"),
    (227, 587, "友好", "友好对待", "愿意回复"),
    (587, 900, "喜欢", "喜欢", "积极回复"),
    (900, 1001, "暧昧", "暧昧", "友善和包容的回复"),
]


class RelationshipManager:
    def __init__(self):
        self.feedback_level = 0  # 正反馈水平

    def calculate_update_relationship_value(
        self,
        person_id: int,
        stance_tag: str,
        attitude_tag: str,
    ):
        """计算并变更关系值

        关系模型基本原理：
            1. 关系值是一个浮点数，范围从-1000到1000
            2. 关系值的变化取决于立场和情绪
            3. 关系越差，改善越难，关系越好，恶化越容易
            4. 人维护关系的精力往往有限，所以当高关系值用户越多，对于中高关系值用户增长越慢
            5. 连续正面或负面情感会正反馈，放大关系变化量

        :param person_id: 目标个体ID
        :param stance_tag: 立场标签：支持、中立、反对
        :param attitude_tag: 情绪标签：喜爱、高兴、惊讶、中性、悲伤、恐惧、愤怒、厌恶
        """

        person_info_dto = PersonInfoManager.get_person_info(PersonInfoDTO(id=person_id))

        if not person_info_dto:
            logger.error(f"PersonInfo with id {person_id} not found.")
            return

        old_value = person_info_dto.relationship_value or 0.0

        delta = ATTITUDE_MAP[attitude_tag]
        delta = _calculate_delta_adjustment(stance_tag, old_value, delta)

        # 考虑心情反馈系数
        delta *= _mood_feedback_factor()

        new_value = max(-1000, min(old_value + delta, 1000))

        # 更新关系值
        person_info_dto.relationship_value = new_value

        relation_level = _calc_relation_level(new_value)
        if relation_level < 0:
            logger.error(
                f"关系值更新失败: {person_info_dto.nickname}(PersonID: {person_info_dto.id}) 新关系值: {new_value:.2f}"
            )
            return

        PersonInfoManager.update_person_info(person_info_dto)

        logger.info(
            f"关系值更新: {person_info_dto.nickname}(PersonID: {person_info_dto.id}) "
            f"{{{old_value:.2f} -> {new_value:.2f}}} (Delta: {delta:.2f}) "
            f"当前关系等级: {RELATIONSHIP_LEVEL[relation_level][2]} "
        )

    def build_relationship_info(
        self,
        person_id: int,
    ) -> str:
        """构建关系信息字符串"""
        person_info_dto = PersonInfoManager.get_person_info(PersonInfoDTO(id=person_id))

        relation_level = _calc_relation_level(person_info_dto.relationship_value)

        if relation_level == -1:
            logger.error(
                f"关系值应用失败: {person_info_dto.nickname}(PersonID: {person_info_dto.id}) 关系值: {person_info_dto.relationship_value:.2f}"
            )
            return ""
        elif relation_level in [0, 5] or (relation_level in [1, 3, 4] and random.random() < 0.6):
            # 关系等级为0或5时，或者1、3、4等级时有60%的概率
            return f"你{RELATIONSHIP_LEVEL[relation_level][3]}{person_info_dto.nickname}，打算{RELATIONSHIP_LEVEL[relation_level][4]}。\n"
        else:
            return ""


def _calculate_delta_adjustment(self, stance_tag: str, old_value: str, delta: float) -> float:
    if old_value >= 0:
        # 正向关系值
        if delta >= 0 and STANCE_MAP[stance_tag] != 2:
            # 正向变化
            delta = delta * math.cos(math.pi * old_value / 2000)
            if old_value > 500:
                # 高关系值时，考虑其它高关系值对象
                # 当有较多高关系值时，增幅会减小
                high_relation_count = PersonInfoManager.count_by_relationship_value(700)
                if old_value > 700:
                    # 排除自己
                    delta *= 3 / (high_relation_count + 2)
                else:
                    delta *= 3 / (high_relation_count + 3)
        elif delta < 0 and STANCE_MAP[stance_tag] != 0:
            # 负向变化
            delta = delta * math.exp(old_value / 2000)
        else:
            # 其他情况下delta值归零
            delta = 0
    else:
        # 负向关系值
        if delta >= 0 and STANCE_MAP[stance_tag] != 2:
            # 正向变化
            delta = delta * math.exp(-old_value / 2000)
        elif delta < 0 and STANCE_MAP[stance_tag] != 0:
            # 负向变化
            delta = delta * math.cos(math.pi * old_value / 2000)
        else:
            # 其他情况下delta值归零
            delta = 0

    return delta


def _mood_feedback_factor():
    """根据当前心情状态计算反馈系数"""
    return math.copysign(mood_manager.current_mood.valence**2, mood_manager.current_mood.valence) + 1


def _calc_relation_level(relationship_value: float) -> int:
    """根据关系值计算关系等级"""
    return next(
        (idx for idx, level in enumerate(RELATIONSHIP_LEVEL) if level[0] <= relationship_value < level[1]),
        -1,
    )


relationship_manager = RelationshipManager()

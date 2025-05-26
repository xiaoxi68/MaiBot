from model_manager.person_info import PersonInfoDTO, PersonInfoManager
from src.common.logger_manager import get_logger
from typing import Optional
from src.chat.models.utils_model import LLMRequest
from src.config.config import global_config
from src.individuality.individuality import individuality

import json  # 新增导入

# TODO: 实现个体数据合并


logger = get_logger("person_identity")


class PersonIdentityManager:
    """个体身份管理器，负责处理个体信息的创建、更新和查询等操作。"""

    def __init__(self):
        # TODO: API-Adapter修改标记
        self._gen_name_llm = LLMRequest(
            model=global_config.model.normal,
            max_tokens=256,
            request_type="qv_name",
        )

    async def _generate_nickname(
        self,
        user_nickname: str,
        user_cardname: Optional[str] = None,
        user_avatar: Optional[str] = None,
        old_name: Optional[str] = None,
        old_name_reason: Optional[str] = None,
        extra_request: Optional[str] = None,
        avoid_names: Optional[list[str]] = None,
    ) -> Optional[tuple[str, str]]:
        """生成昵称"""
        prompt_personality = individuality.get_prompt(x_person=2, level=1)
        bot_name = individuality.personality.bot_nickname

        prompt = f"你是{bot_name}，{prompt_personality}，现在你想给一个用户取一个方便称呼的昵称"
        prompt += f"用户的昵称是'{user_nickname}'，"
        if user_cardname:  # 群昵称
            prompt += f"，ta目前在群里的ID是'{user_cardname}'"
        prompt += "。\n"

        if user_avatar:  # 用户头像
            prompt += f"ta的头像是这样的：{user_avatar}\n"

        if old_name and old_name_reason:  # 旧名称
            prompt += f"你之前叫他{old_name}，是因为{old_name_reason}。\n"

        if extra_request:  # 额外要求
            prompt += f"其他取名的要求是：{extra_request}\n"

        prompt += "请根据以上信息，想想叫ta什么比较好，不要太浮夸，最好使用ta当前的ID，可以稍作修改。\n"

        if avoid_names:
            prompt += f"请注意，以下昵称已被你尝试过或已知存在，请避免：{', '.join(avoid_names)}\n"

        prompt += "请用json给出你的想法，并给出理由，示例如下："
        prompt += """{"nickname": "昵称", "reason": "理由"}"""

        response = await self._gen_name_llm.generate_response(prompt)

        logger.trace(f"生成昵称提示词：{prompt}\n生成昵称回复：{response}")

        try:
            result = json.loads(response[0])
            if not result or not isinstance(result, dict):
                logger.error("生成的昵称结果格式不正确")
                return None
            if "nickname" not in result or "reason" not in result:
                logger.error("生成的昵称结果缺少 'nickname' 或 'reason' 字段")
                return None
            return result["nickname"], result["reason"]
        except json.JSONDecodeError:
            logger.error(f"生成昵称时解析JSON失败: {response[0]}")
            return None

    async def create_person_info(
        self,
        user_nickname: str,
        user_cardname: Optional[str] = None,
        user_avatar: Optional[str] = None,
        extra_request: Optional[str] = None,
    ) -> PersonInfoDTO:
        """创建一个新的个体信息

        :param person_id: 个体ID
        :param user_nickname: 用户ID
        :param user_cardname: 用户在群组内的ID
        :param user_avatar: 用户头像的描述
        :param extra_request: 额外的取名要求
        """

        try_count = 0
        avoid_names = set()

        nickname = None
        reason = None

        while try_count < 5:
            result = await self._generate_nickname(
                user_nickname,
                user_cardname,
                user_avatar,
                extra_request=extra_request,
                avoid_names=list(avoid_names) if avoid_names else None,
            )
            if result is None:
                logger.error("生成昵称失败，重试中...")
                try_count += 1
                continue

            nickname_, reason_ = result

            if not nickname_ or not reason_:
                logger.error("生成的昵称或理由为空，重试中...")
                try_count += 1
                continue

            if PersonInfoManager.get_person_info(PersonInfoDTO(nickname=nickname_)):
                logger.debug(f"生成的昵称 '{nickname_}' 已被占用，重试中...")
                avoid_names.add(nickname_)
                try_count += 1
                continue

            nickname = nickname_
            reason = reason_

            break

        return PersonInfoManager.create_person_info(
            PersonInfoDTO(
                nickname=nickname,
                nickname_reason=reason,
            )
        )

    async def rename_person(
        self, person_id: int, user_nickname: str, user_cardname: str, user_avatar: str, extra_request: str = ""
    ) -> Optional[PersonInfoDTO]:
        """重命名一个个体

        :param person_id: 个体ID
        :param user_nickname: 用户昵称
        :param user_cardname: 用户群昵称
        :param user_avatar: 用户头像
        :param extra_request: 额外的取名要求
        """

        person_info_dto = PersonInfoManager.get_person_info(PersonInfoDTO(person_id=person_id))

        if not person_info_dto:
            logger.debug(f"重命名失败：未找到ID为 {person_id} 的个体信息")
            return None

        old_name = person_info_dto.nickname
        old_reason = person_info_dto.nickname_reason

        result = await self._generate_nickname(
            user_nickname,
            user_cardname,
            user_avatar,
            old_name,
            old_reason,
            extra_request=extra_request,
            avoid_names=list(self.person_name_list.values()),
        )

        if result is None:
            logger.error("重命名失败，生成昵称时出错")
            return

        new_nickname, new_nickname_reason = result

        if not new_nickname or not new_nickname_reason:
            logger.error("生成的昵称或理由为空，重命名失败")
            return

        person_info_dto.nickname = new_nickname
        person_info_dto.nickname_reason = new_nickname_reason

        person_info_dto = PersonInfoManager.update_person_info(person_info_dto)

        return person_info_dto

    def get_person_nickname(self, person_id: str) -> Optional[str]:
        """获取个体昵称"""
        if not person_id:
            return None
        person_info = PersonInfoManager.get_person_info(PersonInfoDTO(person_id=person_id))
        nickname = person_info.nickname if person_info else None
        return nickname or None


person_identity_manager = PersonIdentityManager()
"""全局个人信息管理器"""

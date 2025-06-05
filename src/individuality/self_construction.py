from model_manager.chat_user import ChatUserDTO, ChatUserManager
from model_manager.person_info import PersonInfoDTO, PersonInfoManager
from config import global_config

"""
自我建构

用于在数据库中创建与自己相关的身份记录
"""

# TODO: 将individuality重命名为self_construction


class SelfRecord:
    def __init__(self):
        self.person_id: int | None = None
        """个体ID"""

        self.platform_user_id: dict[str, int] = {}
        """平台用户信息
        
        {
            "platform_name": chat_user_id(int),
        }
        """

        self._load_self_record()

    def _load_self_record(self):
        """初始化个体记录"""
        self._load_or_update_person_info()
        self._load_or_update_platform_users()

    def _load_or_update_person_info(self):
        """加载或更新个体信息"""
        person_info_dto = PersonInfoManager.get_person_info(PersonInfoDTO(nickname=global_config.character.name))
        if not person_info_dto:
            person_info_dto = PersonInfoManager.create_person_info(
                real_name=global_config.character.name,
                nickname=global_config.character.name,
                nickname_reason="方便称呼",
                relationship_value=0.0,
            )
        elif (
            person_info_dto.real_name != global_config.character.name
            or person_info_dto.nickname != global_config.character.name
        ):
            person_info_dto.real_name = global_config.character.name
            person_info_dto.nickname = global_config.character.name
            PersonInfoManager.update_person_info(person_info_dto)
        self.person_id = person_info_dto.id

    def _load_or_update_platform_users(self):
        """加载或更新平台用户信息"""
        platforms = global_config.platforms
        for platform_name, platform_config in platforms.items():
            chat_user_dto = ChatUserManager.get_chat_user(
                ChatUserDTO(platform=platform_name, platform_user_id=platform_config.platform_user_id)
            )
            if not chat_user_dto:
                chat_user_dto = ChatUserManager.create_user(
                    ChatUserDTO(
                        platform=platform_name,
                        platform_user_id=platform_config.account,
                        user_name=platform_config.nickname,
                        person_id=self.person_id,
                    )
                )
            elif chat_user_dto.person_id != self.person_id:
                chat_user_dto.person_id = self.person_id
                ChatUserManager.update_chat_user(chat_user_dto)
            elif chat_user_dto.user_name != platform_config.nickname:
                chat_user_dto.user_name = platform_config.nickname
                ChatUserManager.update_chat_user(chat_user_dto)
            self.platform_user_id[platform_name] = chat_user_dto.id


self_record = SelfRecord()

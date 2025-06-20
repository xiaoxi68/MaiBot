from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.heart_flow.observation.observation import Observation
from src.llm_models.utils_model import LLMRequest
from src.config.config import global_config
import time
import traceback
import json
import os
import hashlib
from src.common.logger import get_logger
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.chat.message_receive.chat_stream import get_chat_manager
from .base_processor import BaseProcessor
from typing import List, Dict
from src.chat.heart_flow.observation.hfcloop_observation import HFCloopObservation
from src.chat.focus_chat.info.info_base import InfoBase
from src.chat.focus_chat.info.self_info import SelfInfo

logger = get_logger("processor")


def init_prompt():
    
    indentify_prompt = """
{time_now}，以下是正在进行的聊天内容：
<聊天记录>
{chat_observe_info}
</聊天记录>

{name_block}
请你根据以上聊天记录，思考聊天记录中是否有人提到你自己相关的信息，或者有人询问你的相关信息，例如你的性格，身高，喜好，外貌，身份，兴趣，爱好，习惯，等等。
然后请你根据你的聊天需要，输出关键词属性在数据库中进行查询，数据库包含了关于你的所有信息，你需要直接输出你要查询的关键词，如果要输出多个，请用逗号隔开
如果没有需要查询的内容，请输出none
现在请输出关键词，注意只输出关键词就好，不要输出其他内容：
"""
    Prompt(indentify_prompt, "indentify_prompt")
    
    
    fetch_info_prompt = """
    
{name_block}，你的性格是：
{prompt_personality}
{indentify_block}

请从中提取有关你的有关"{keyword}"信息，请输出原始内容，如果{bot_name}没有涉及"{keyword}"相关信息，请输出none：
"""
    Prompt(fetch_info_prompt, "fetch_info_prompt")


class SelfProcessor(BaseProcessor):
    log_prefix = "自我认同"

    def __init__(self, subheartflow_id: str):
        super().__init__()

        self.subheartflow_id = subheartflow_id
        
        self.info_fetched_cache: Dict[str, Dict[str, any]] = {}
        
        self.fetch_info_file_path = "data/personality/fetch_info.json"
        self.meta_info_file_path = "data/personality/meta_info.json"

        self.llm_model = LLMRequest(
            model=global_config.model.utils_small,
            request_type="focus.processor.self_identify",
        )


        name = get_chat_manager().get_stream_name(self.subheartflow_id)
        self.log_prefix = f"[{name}] "
        
        # 在初始化时检查配置是否发生变化
        self._check_config_change_and_clear()

    def _get_config_hash(self) -> str:
        """获取当前personality和identity配置的哈希值"""
        personality_sides = list(global_config.personality.personality_sides)
        identity_detail = list(global_config.identity.identity_detail)
        
        # 将配置转换为字符串并排序，确保一致性
        config_str = json.dumps({
            "personality_sides": sorted(personality_sides),
            "identity_detail": sorted(identity_detail)
        }, sort_keys=True)
        
        return hashlib.md5(config_str.encode('utf-8')).hexdigest()

    def _load_meta_info(self) -> Dict[str, str]:
        """从JSON文件中加载元信息"""
        if os.path.exists(self.meta_info_file_path):
            try:
                with open(self.meta_info_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"{self.log_prefix} 读取meta_info文件失败: {e}")
                return {}
        return {}

    def _save_meta_info(self, meta_info: Dict[str, str]):
        """将元信息保存到JSON文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.meta_info_file_path), exist_ok=True)
            with open(self.meta_info_file_path, 'w', encoding='utf-8') as f:
                json.dump(meta_info, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"{self.log_prefix} 保存meta_info文件失败: {e}")

    def _check_config_change_and_clear(self):
        """检查配置是否发生变化，如果变化则清空fetch_info.json"""
        current_config_hash = self._get_config_hash()
        meta_info = self._load_meta_info()
        
        stored_config_hash = meta_info.get("config_hash", "")
        
        if current_config_hash != stored_config_hash:
            logger.info(f"{self.log_prefix} 检测到personality或identity配置发生变化，清空fetch_info数据")
            
            # 清空fetch_info文件
            if os.path.exists(self.fetch_info_file_path):
                try:
                    os.remove(self.fetch_info_file_path)
                    logger.info(f"{self.log_prefix} 已清空fetch_info文件")
                except Exception as e:
                    logger.error(f"{self.log_prefix} 清空fetch_info文件失败: {e}")
            
            # 更新元信息
            meta_info["config_hash"] = current_config_hash
            self._save_meta_info(meta_info)
            logger.info(f"{self.log_prefix} 已更新配置哈希值")

    def _load_fetch_info_from_file(self) -> Dict[str, str]:
        """从JSON文件中加载已保存的fetch_info数据"""
        if os.path.exists(self.fetch_info_file_path):
            try:
                with open(self.fetch_info_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"{self.log_prefix} 读取fetch_info文件失败: {e}")
                return {}
        return {}

    def _save_fetch_info_to_file(self, fetch_info_data: Dict[str, str]):
        """将fetch_info数据保存到JSON文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.fetch_info_file_path), exist_ok=True)
            with open(self.fetch_info_file_path, 'w', encoding='utf-8') as f:
                json.dump(fetch_info_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"{self.log_prefix} 保存fetch_info文件失败: {e}")

    async def process_info(self, observations: List[Observation] = None, *infos) -> List[InfoBase]:
        """处理信息对象

        Args:
            *infos: 可变数量的InfoBase类型的信息对象

        Returns:
            List[InfoBase]: 处理后的结构化信息列表
        """
        self_info_str = await self.self_indentify(observations)

        if self_info_str:
            self_info = SelfInfo()
            self_info.set_self_info(self_info_str)
        else:
            self_info = None
            return None

        return [self_info]

    async def self_indentify(
        self,
        observations: List[Observation] = None,
    ):
        """
        在回复前进行思考，生成内心想法并收集工具调用结果

        参数:
            observations: 观察信息

        返回:
            如果return_prompt为False:
                tuple: (current_mind, past_mind) 当前想法和过去的想法列表
            如果return_prompt为True:
                tuple: (current_mind, past_mind, prompt) 当前想法、过去的想法列表和使用的prompt
        """

        if observations is None:
            observations = []
        for observation in observations:
            if isinstance(observation, ChattingObservation):
                # 获取聊天元信息
                is_group_chat = observation.is_group_chat
                chat_target_info = observation.chat_target_info
                chat_target_name = "对方"  # 私聊默认名称
                if not is_group_chat and chat_target_info:
                    # 优先使用person_name，其次user_nickname，最后回退到默认值
                    chat_target_name = (
                        chat_target_info.get("person_name") or chat_target_info.get("user_nickname") or chat_target_name
                    )
                # 获取聊天内容
                chat_observe_info = observation.get_observe_info()
            if isinstance(observation, HFCloopObservation):
                pass

        nickname_str = ""
        for nicknames in global_config.bot.alias_names:
            nickname_str += f"{nicknames},"
        name_block = f"你的名字是{global_config.bot.nickname},你的昵称有{nickname_str}，有人也会用这些昵称称呼你。"

        personality_sides_str = "你"
        identity_detail_str = "你"
        for personality_side in global_config.personality.personality_sides:
            personality_sides_str += f"{personality_side},"
            
        for identity_detail in global_config.identity.identity_detail:
            identity_detail_str += f"{identity_detail},"

        
        prompt = (await global_prompt_manager.get_prompt_async("indentify_prompt")).format(
            name_block=name_block,
            time_now=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            chat_observe_info=chat_observe_info[-200:],
            bot_name = global_config.bot.nickname
        )

        keyword = ""
        
        try:
            keyword, _ = await self.llm_model.generate_response_async(prompt=prompt)
            
            print(f"prompt: {prompt}\nkeyword: {keyword}")
            
            if not keyword:
                logger.warning(f"{self.log_prefix} LLM返回空结果，自我识别失败。")
        except Exception as e:
            # 处理总体异常
            logger.error(f"{self.log_prefix} 执行LLM请求或处理响应时出错: {e}")
            logger.error(traceback.format_exc())
            keyword = "我是谁，我从哪来，要到哪去"
        

        # keyword_json = json.loads(repair_json(keyword))
        # 根据逗号分割为list
        keyword = keyword.strip()
        if not keyword or keyword == "none":
            keyword_set = []
        else:
            # 只保留非空关键词，去除多余空格
            keyword_set = [k.strip() for k in keyword.split(",") if k.strip()]
        
            for keyword in keyword_set:
                if keyword not in self.info_fetched_cache:
                # 首先尝试从文件中读取
                    fetch_info_data = self._load_fetch_info_from_file()
                    
                    if keyword in fetch_info_data:
                        # 从文件中获取已保存的信息
                        fetched_info = fetch_info_data[keyword]
                        logger.info(f"{self.log_prefix} 从文件中读取到关键词 '{keyword}' 的信息")
                    else:
                        # 文件中没有，使用LLM生成
                        prompt = (await global_prompt_manager.get_prompt_async("fetch_info_prompt")).format(
                            name_block=name_block,
                            prompt_personality=personality_sides_str,
                            indentify_block=identity_detail_str,
                            keyword=keyword,
                            bot_name = global_config.bot.nickname
                        )
                        
                        print(prompt)
                        
                        fetched_info, _ = await self.llm_model.generate_response_async(prompt=prompt)
                        if not fetched_info:
                            logger.warning(f"{self.log_prefix} LLM返回空结果，自我识别失败。")
                            fetched_info = ""
                        elif fetched_info == "none":
                            fetched_info = ""
                        else:
                            # 保存新生成的信息到文件
                            fetch_info_data[keyword] = fetched_info
                            self._save_fetch_info_to_file(fetch_info_data)
                            logger.info(f"{self.log_prefix} 新生成的关键词 '{keyword}' 信息已保存到文件")
                    
                    if fetched_info:
                        self.info_fetched_cache[keyword] = {
                            "info": fetched_info,
                            "ttl": 5,
                        }
        
        for fetched_keyword, info in self.info_fetched_cache.items():
            if info["ttl"] > 0:
                info["ttl"] -= 1
            else:
                del self.info_fetched_cache[fetched_keyword]
        
        
        fetched_info_str = ""
        for keyword, info in self.info_fetched_cache.items():
            fetched_info_str += f"你的：{keyword}信息是: {info['info']}\n"
        
        return fetched_info_str



init_prompt()

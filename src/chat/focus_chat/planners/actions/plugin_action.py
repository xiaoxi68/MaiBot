import traceback
from typing import Tuple, Dict, List, Any, Optional, Union, Type
from src.chat.focus_chat.planners.actions.base_action import BaseAction, register_action, ActionActivationType  # noqa F401
from src.chat.heart_flow.observation.chatting_observation import ChattingObservation
from src.chat.focus_chat.hfc_utils import create_empty_anchor_message
from src.common.logger_manager import get_logger
from src.llm_models.utils_model import LLMRequest
from src.person_info.person_info import person_info_manager
from abc import abstractmethod
from src.config.config import global_config
import os
import inspect
import toml  # 导入 toml 库
from src.common.database.database_model import ActionRecords
from src.common.database.database import db
from peewee import Model, DoesNotExist
import json
import time

# 以下为类型注解需要
from src.chat.message_receive.chat_stream import ChatStream
from src.chat.focus_chat.expressors.default_expressor import DefaultExpressor
from src.chat.focus_chat.replyer.default_replyer import DefaultReplyer
from src.chat.focus_chat.info.obs_info import ObsInfo

logger = get_logger("plugin_action")


class PluginAction(BaseAction):
    """插件动作基类

    封装了主程序内部依赖，提供简化的API接口给插件开发者
    """

    action_config_file_name: Optional[str] = None  # 插件可以覆盖此属性来指定配置文件名
    
    # 默认激活类型设置，插件可以覆盖
    action_activation_type = ActionActivationType.ALWAYS
    random_activation_probability: float = 0.3
    llm_judge_prompt: str = ""
    activation_keywords: list[str] = []
    keyword_case_sensitive: bool = False

    def __init__(
        self,
        action_data: dict,
        reasoning: str,
        cycle_timers: dict,
        thinking_id: str,
        global_config: Optional[dict] = None,
        **kwargs,
    ):
        """初始化插件动作基类"""
        super().__init__(action_data, reasoning, cycle_timers, thinking_id)

        # 存储内部服务和对象引用
        self._services = {}
        self.config: Dict[str, Any] = {}  # 用于存储插件自身的配置

        # 从kwargs提取必要的内部服务
        if "observations" in kwargs:
            self._services["observations"] = kwargs["observations"]
        if "expressor" in kwargs:
            self._services["expressor"] = kwargs["expressor"]
        if "chat_stream" in kwargs:
            self._services["chat_stream"] = kwargs["chat_stream"]
        if "replyer" in kwargs:
            self._services["replyer"] = kwargs["replyer"]

        self.log_prefix = kwargs.get("log_prefix", "")
        self._load_plugin_config()  # 初始化时加载插件配置

    def _load_plugin_config(self):
        """
        加载插件自身的配置文件。
        配置文件应与插件模块在同一目录下。
        插件可以通过覆盖 `action_config_file_name` 类属性来指定文件名。
        如果 `action_config_file_name` 未指定，则不加载配置。
        仅支持 TOML (.toml) 格式。
        """
        if not self.action_config_file_name:
            logger.debug(
                f"{self.log_prefix} 插件 {self.__class__.__name__} 未指定 action_config_file_name，不加载插件配置。"
            )
            return

        try:
            plugin_module_path = inspect.getfile(self.__class__)
            plugin_dir = os.path.dirname(plugin_module_path)
            config_file_path = os.path.join(plugin_dir, self.action_config_file_name)

            if not os.path.exists(config_file_path):
                logger.warning(
                    f"{self.log_prefix} 插件 {self.__class__.__name__} 的配置文件 {config_file_path} 不存在。"
                )
                return

            file_ext = os.path.splitext(self.action_config_file_name)[1].lower()

            if file_ext == ".toml":
                with open(config_file_path, "r", encoding="utf-8") as f:
                    self.config = toml.load(f) or {}
                logger.info(f"{self.log_prefix} 插件 {self.__class__.__name__} 的配置已从 {config_file_path} 加载。")
            else:
                logger.warning(
                    f"{self.log_prefix} 不支持的插件配置文件格式: {file_ext}。仅支持 .toml。插件配置未加载。"
                )
                self.config = {}  # 确保未加载时为空字典
                return

        except Exception as e:
            logger.error(
                f"{self.log_prefix} 加载插件 {self.__class__.__name__} 的配置文件 {self.action_config_file_name} 时出错: {e}"
            )
            self.config = {}  # 出错时确保 config 是一个空字典

    def get_global_config(self, key: str, default: Any = None) -> Any:
        """
        安全地从全局配置中获取一个值。
        插件应使用此方法读取全局配置，以保证只读和隔离性。
        """

        return global_config.get(key, default)

    async def get_user_id_by_person_name(self, person_name: str) -> Tuple[str, str]:
        """根据用户名获取用户ID"""
        person_id = person_info_manager.get_person_id_by_person_name(person_name)
        user_id = await person_info_manager.get_value(person_id, "user_id")
        platform = await person_info_manager.get_value(person_id, "platform")
        return platform, user_id

    # 提供简化的API方法
    async def send_message(self, type: str, data: str, target: Optional[str] = "", display_message: str = "") -> bool:
        """发送消息的简化方法

        Args:
            text: 要发送的消息文本
            target: 目标消息（可选）

        Returns:
            bool: 是否发送成功
        """
        try:
            expressor: DefaultExpressor = self._services.get("expressor")
            chat_stream: ChatStream = self._services.get("chat_stream")

            if not expressor or not chat_stream:
                logger.error(f"{self.log_prefix} 无法发送消息：缺少必要的内部服务")
                return False

            # 构造简化的动作数据
            # reply_data = {"text": text, "target": target or "", "emojis": []}

            # 获取锚定消息（如果有）
            observations = self._services.get("observations", [])

            if len(observations) > 0:
                chatting_observation: ChattingObservation = next(
                    obs for obs in observations if isinstance(obs, ChattingObservation)
                )

                anchor_message = chatting_observation.search_message_by_text(target)
            else:
                anchor_message = None

            # 如果没有找到锚点消息，创建一个占位符
            if not anchor_message:
                logger.info(f"{self.log_prefix} 未找到锚点消息，创建占位符")
                anchor_message = await create_empty_anchor_message(
                    chat_stream.platform, chat_stream.group_info, chat_stream
                )
            else:
                anchor_message.update_chat_stream(chat_stream)

            response_set = [
                (type, data),
            ]

            # 调用内部方法发送消息
            success = await expressor.send_response_messages(
                anchor_message=anchor_message,
                response_set=response_set,
                display_message=display_message,
            )

            return success
        except Exception as e:
            logger.error(f"{self.log_prefix} 发送消息时出错: {e}")
            traceback.print_exc()
            return False

    async def send_message_by_expressor(self, text: str, target: Optional[str] = None) -> bool:
        """发送消息的简化方法

        Args:
            text: 要发送的消息文本
            target: 目标消息（可选）

        Returns:
            bool: 是否发送成功
        """
        expressor: DefaultExpressor = self._services.get("expressor")
        chat_stream: ChatStream = self._services.get("chat_stream")

        if not expressor or not chat_stream:
            logger.error(f"{self.log_prefix} 无法发送消息：缺少必要的内部服务")
            return False

        # 构造简化的动作数据
        reply_data = {"text": text, "target": target or "", "emojis": []}

        # 获取锚定消息（如果有）
        observations = self._services.get("observations", [])

        # 查找 ChattingObservation 实例
        chatting_observation = None
        for obs in observations:
            if isinstance(obs, ChattingObservation):
                chatting_observation = obs
                break

        if not chatting_observation:
            logger.warning(f"{self.log_prefix} 未找到 ChattingObservation 实例，创建占位符")
            anchor_message = await create_empty_anchor_message(
                chat_stream.platform, chat_stream.group_info, chat_stream
            )
        else:
            anchor_message = chatting_observation.search_message_by_text(reply_data["target"])
            if not anchor_message:
                logger.info(f"{self.log_prefix} 未找到锚点消息，创建占位符")
                anchor_message = await create_empty_anchor_message(
                    chat_stream.platform, chat_stream.group_info, chat_stream
                )
            else:
                anchor_message.update_chat_stream(chat_stream)

        # 调用内部方法发送消息
        success, _ = await expressor.deal_reply(
            cycle_timers=self.cycle_timers,
            action_data=reply_data,
            anchor_message=anchor_message,
            reasoning=self.reasoning,
            thinking_id=self.thinking_id,
        )

        return success

    async def send_message_by_replyer(self, target: Optional[str] = None, extra_info_block: Optional[str] = None) -> bool:
        """通过 replyer 发送消息的简化方法

        Args:
            text: 要发送的消息文本
            target: 目标消息（可选）

        Returns:
            bool: 是否发送成功
        """
        replyer: DefaultReplyer = self._services.get("replyer")
        chat_stream: ChatStream = self._services.get("chat_stream")

        if not replyer or not chat_stream:
            logger.error(f"{self.log_prefix} 无法发送消息：缺少必要的内部服务")
            return False

        # 构造简化的动作数据
        reply_data = {"target": target or "", "extra_info_block": extra_info_block}

        # 获取锚定消息（如果有）
        observations = self._services.get("observations", [])

        # 查找 ChattingObservation 实例
        chatting_observation = None
        for obs in observations:
            if isinstance(obs, ChattingObservation):
                chatting_observation = obs
                break

        if not chatting_observation:
            logger.warning(f"{self.log_prefix} 未找到 ChattingObservation 实例，创建占位符")
            anchor_message = await create_empty_anchor_message(
                chat_stream.platform, chat_stream.group_info, chat_stream
            )
        else:
            anchor_message = chatting_observation.search_message_by_text(reply_data["target"])
            if not anchor_message:
                logger.info(f"{self.log_prefix} 未找到锚点消息，创建占位符")
                anchor_message = await create_empty_anchor_message(
                    chat_stream.platform, chat_stream.group_info, chat_stream
                )
            else:
                anchor_message.update_chat_stream(chat_stream)

        # 调用内部方法发送消息
        success, _ = await replyer.deal_reply(
            cycle_timers=self.cycle_timers,
            action_data=reply_data,
            anchor_message=anchor_message,
            reasoning=self.reasoning,
            thinking_id=self.thinking_id,
        )

        return success

    def get_chat_type(self) -> str:
        """获取当前聊天类型

        Returns:
            str: 聊天类型 ("group" 或 "private")
        """
        chat_stream: ChatStream = self._services.get("chat_stream")
        if chat_stream and hasattr(chat_stream, "group_info"):
            return "group" if chat_stream.group_info else "private"
        return "unknown"

    def get_recent_messages(self, count: int = 5) -> List[Dict[str, Any]]:
        """获取最近的消息

        Args:
            count: 要获取的消息数量

        Returns:
            List[Dict]: 消息列表，每个消息包含发送者、内容等信息
        """
        messages = []
        observations = self._services.get("observations", [])

        if observations and len(observations) > 0:
            obs = observations[0]
            if hasattr(obs, "get_talking_message"):
                obs: ObsInfo
                raw_messages = obs.get_talking_message()
                # 转换为简化格式
                for msg in raw_messages[-count:]:
                    simple_msg = {
                        "sender": msg.get("sender", "未知"),
                        "content": msg.get("content", ""),
                        "timestamp": msg.get("timestamp", 0),
                    }
                    messages.append(simple_msg)

        return messages

    def get_available_models(self) -> Dict[str, Any]:
        """获取所有可用的模型配置

        Returns:
            Dict[str, Any]: 模型配置字典，key为模型名称，value为模型配置
        """
        if not hasattr(global_config, "model"):
            logger.error(f"{self.log_prefix} 无法获取模型列表：全局配置中未找到 model 配置")
            return {}
        
        models = global_config.model
            
        return models

    async def generate_with_model(
        self,
        prompt: str,
        model_config: Dict[str, Any],
        request_type: str = "plugin.generate",
        **kwargs
    ) -> Tuple[bool, str]:
        """使用指定模型生成内容

        Args:
            prompt: 提示词
            model_config: 模型配置（从 get_available_models 获取的模型配置）
            temperature: 温度参数，控制随机性 (0-1)
            max_tokens: 最大生成token数
            request_type: 请求类型标识
            **kwargs: 其他模型特定参数

        Returns:
            Tuple[bool, str]: (是否成功, 生成的内容或错误信息)
        """
        try:
            
            
            logger.info(f"prompt: {prompt}")
            
            llm_request = LLMRequest(
                model=model_config,
                request_type=request_type,
                **kwargs
            )
            
            response,(resoning , model_name) = await llm_request.generate_response_async(prompt)
            return True, response, resoning, model_name
        except Exception as e:
            error_msg = f"生成内容时出错: {str(e)}"
            logger.error(f"{self.log_prefix} {error_msg}")
            return False, error_msg

    @abstractmethod
    async def process(self) -> Tuple[bool, str]:
        """插件处理逻辑，子类必须实现此方法

        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        pass

    async def handle_action(self) -> Tuple[bool, str]:
        """实现BaseAction的抽象方法，调用子类的process方法

        Returns:
            Tuple[bool, str]: (是否执行成功, 回复文本)
        """
        return await self.process()

    async def store_action_info(self, action_build_into_prompt: bool = False, action_prompt_display: str = "", action_done: bool = True) -> None:
        """存储action执行信息到数据库

        Args:
            action_build_into_prompt: 是否构建到提示中
            action_prompt_display: 动作显示内容
        """
        try:
            chat_stream: ChatStream = self._services.get("chat_stream")
            if not chat_stream:
                logger.error(f"{self.log_prefix} 无法存储action信息：缺少chat_stream服务")
                return

            action_time = time.time()
            action_id = f"{action_time}_{self.thinking_id}"

            ActionRecords.create(
                action_id=action_id,
                time=action_time,
                action_name=self.__class__.__name__,
                action_data=str(self.action_data),
                action_done=action_done,
                action_build_into_prompt=action_build_into_prompt,
                action_prompt_display=action_prompt_display,
                chat_id=chat_stream.stream_id,
                chat_info_stream_id=chat_stream.stream_id,
                chat_info_platform=chat_stream.platform,
                user_id=chat_stream.user_info.user_id if chat_stream.user_info else "",
                user_nickname=chat_stream.user_info.user_nickname if chat_stream.user_info else "",
                user_cardname=chat_stream.user_info.user_cardname if chat_stream.user_info else ""
            )
            logger.debug(f"{self.log_prefix} 已存储action信息: {action_prompt_display}")
        except Exception as e:
            logger.error(f"{self.log_prefix} 存储action信息时出错: {e}")
            traceback.print_exc()
            
    async def db_query(
        self,
        model_class: Type[Model],
        query_type: str = "get",
        filters: Dict[str, Any] = None,
        data: Dict[str, Any] = None,
        limit: int = None,
        order_by: List[str] = None,
        single_result: bool = False
    ) -> Union[List[Dict[str, Any]], Dict[str, Any], None]:
        """执行数据库查询操作
        
        这个方法提供了一个通用接口来执行数据库操作，包括查询、创建、更新和删除记录。
        
        Args:
            model_class: Peewee 模型类，例如 ActionRecords, Messages 等
            query_type: 查询类型，可选值: "get", "create", "update", "delete", "count"
            filters: 过滤条件字典，键为字段名，值为要匹配的值
            data: 用于创建或更新的数据字典
            limit: 限制结果数量
            order_by: 排序字段列表，使用字段名，前缀'-'表示降序
            single_result: 是否只返回单个结果
            
        Returns:
            根据查询类型返回不同的结果:
            - "get": 返回查询结果列表或单个结果（如果 single_result=True）
            - "create": 返回创建的记录
            - "update": 返回受影响的行数
            - "delete": 返回受影响的行数
            - "count": 返回记录数量
            
        示例:
            # 查询最近10条消息
            messages = await self.db_query(
                Messages, 
                query_type="get",
                filters={"chat_id": chat_stream.stream_id},
                limit=10,
                order_by=["-time"]
            )
            
            # 创建一条记录
            new_record = await self.db_query(
                ActionRecords,
                query_type="create",
                data={"action_id": "123", "time": time.time(), "action_name": "TestAction"}
            )
            
            # 更新记录
            updated_count = await self.db_query(
                ActionRecords,
                query_type="update",
                filters={"action_id": "123"},
                data={"action_done": True}
            )
            
            # 删除记录
            deleted_count = await self.db_query(
                ActionRecords,
                query_type="delete",
                filters={"action_id": "123"}
            )
            
            # 计数
            count = await self.db_query(
                Messages,
                query_type="count",
                filters={"chat_id": chat_stream.stream_id}
            )
        """
        try:
            # 构建基本查询
            if query_type in ["get", "update", "delete", "count"]:
                query = model_class.select()
                
                # 应用过滤条件
                if filters:
                    for field, value in filters.items():
                        query = query.where(getattr(model_class, field) == value)
            
            # 执行查询
            if query_type == "get":
                # 应用排序
                if order_by:
                    for field in order_by:
                        if field.startswith("-"):
                            query = query.order_by(getattr(model_class, field[1:]).desc())
                        else:
                            query = query.order_by(getattr(model_class, field))
                
                # 应用限制
                if limit:
                    query = query.limit(limit)
                
                # 执行查询
                results = list(query.dicts())
                
                # 返回结果
                if single_result:
                    return results[0] if results else None
                return results
                
            elif query_type == "create":
                if not data:
                    raise ValueError("创建记录需要提供data参数")
                
                # 创建记录
                record = model_class.create(**data)
                # 返回创建的记录
                return model_class.select().where(model_class.id == record.id).dicts().get()
                
            elif query_type == "update":
                if not data:
                    raise ValueError("更新记录需要提供data参数")
                
                # 更新记录
                return query.update(**data).execute()
                
            elif query_type == "delete":
                # 删除记录
                return query.delete().execute()
                
            elif query_type == "count":
                # 计数
                return query.count()
                
            else:
                raise ValueError(f"不支持的查询类型: {query_type}")
                
        except DoesNotExist:
            # 记录不存在
            if query_type == "get" and single_result:
                return None
            return []
            
        except Exception as e:
            logger.error(f"{self.log_prefix} 数据库操作出错: {e}")
            traceback.print_exc()
            
            # 根据查询类型返回合适的默认值
            if query_type == "get":
                return None if single_result else []
            elif query_type in ["create", "update", "delete", "count"]:
                return None
                
    async def db_raw_query(
        self, 
        sql: str, 
        params: List[Any] = None,
        fetch_results: bool = True
    ) -> Union[List[Dict[str, Any]], int, None]:
        """执行原始SQL查询
        
        警告: 使用此方法需要小心，确保SQL语句已正确构造以避免SQL注入风险。
        
        Args:
            sql: 原始SQL查询字符串
            params: 查询参数列表，用于替换SQL中的占位符
            fetch_results: 是否获取查询结果，对于SELECT查询设为True，对于
                          UPDATE/INSERT/DELETE等操作设为False
                          
        Returns:
            如果fetch_results为True，返回查询结果列表；
            如果fetch_results为False，返回受影响的行数；
            如果出错，返回None
        """
        try:
            cursor = db.execute_sql(sql, params or [])
            
            if fetch_results:
                # 获取列名
                columns = [col[0] for col in cursor.description]
                
                # 构建结果字典列表
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                
                return results
            else:
                # 返回受影响的行数
                return cursor.rowcount
                
        except Exception as e:
            logger.error(f"{self.log_prefix} 执行原始SQL查询出错: {e}")
            traceback.print_exc()
            return None
            
    async def db_save(
        self, 
        model_class: Type[Model], 
        data: Dict[str, Any], 
        key_field: str = None, 
        key_value: Any = None
    ) -> Union[Dict[str, Any], None]:
        """保存数据到数据库（创建或更新）
        
        如果提供了key_field和key_value，会先尝试查找匹配的记录进行更新；
        如果没有找到匹配记录，或未提供key_field和key_value，则创建新记录。
        
        Args:
            model_class: Peewee模型类，如ActionRecords, Messages等
            data: 要保存的数据字典
            key_field: 用于查找现有记录的字段名，例如"action_id"
            key_value: 用于查找现有记录的字段值
            
        Returns:
            Dict[str, Any]: 保存后的记录数据
            None: 如果操作失败
            
        示例:
            # 创建或更新一条记录
            record = await self.db_save(
                ActionRecords,
                {
                    "action_id": "123", 
                    "time": time.time(), 
                    "action_name": "TestAction",
                    "action_done": True
                },
                key_field="action_id",
                key_value="123"
            )
        """
        try:
            # 如果提供了key_field和key_value，尝试更新现有记录
            if key_field and key_value is not None:
                # 查找现有记录
                existing_records = list(model_class.select().where(
                    getattr(model_class, key_field) == key_value
                ).limit(1))
                
                if existing_records:
                    # 更新现有记录
                    existing_record = existing_records[0]
                    for field, value in data.items():
                        setattr(existing_record, field, value)
                    existing_record.save()
                    
                    # 返回更新后的记录
                    updated_record = model_class.select().where(
                        model_class.id == existing_record.id
                    ).dicts().get()
                    return updated_record
            
            # 如果没有找到现有记录或未提供key_field和key_value，创建新记录
            new_record = model_class.create(**data)
            
            # 返回创建的记录
            created_record = model_class.select().where(
                model_class.id == new_record.id
            ).dicts().get()
            return created_record
            
        except Exception as e:
            logger.error(f"{self.log_prefix} 保存数据库记录出错: {e}")
            traceback.print_exc()
            return None
            
    async def db_get(
        self,
        model_class: Type[Model],
        filters: Dict[str, Any] = None,
        order_by: str = None,
        limit: int = None
    ) -> Union[List[Dict[str, Any]], Dict[str, Any], None]:
        """从数据库获取记录
        
        这是db_query方法的简化版本，专注于数据检索操作。
        
        Args:
            model_class: Peewee模型类
            filters: 过滤条件，字段名和值的字典
            order_by: 排序字段，前缀'-'表示降序，例如'-time'表示按时间降序
            limit: 结果数量限制，如果为1则返回单个记录而不是列表
            
        Returns:
            如果limit=1，返回单个记录字典或None；
            否则返回记录字典列表或空列表。
            
        示例:
            # 获取单个记录
            record = await self.db_get(
                ActionRecords,
                filters={"action_id": "123"},
                limit=1
            )
            
            # 获取最近10条记录
            records = await self.db_get(
                Messages,
                filters={"chat_id": chat_stream.stream_id},
                order_by="-time",
                limit=10
            )
        """
        try:
            # 构建查询
            query = model_class.select()
            
            # 应用过滤条件
            if filters:
                for field, value in filters.items():
                    query = query.where(getattr(model_class, field) == value)
            
            # 应用排序
            if order_by:
                if order_by.startswith("-"):
                    query = query.order_by(getattr(model_class, order_by[1:]).desc())
                else:
                    query = query.order_by(getattr(model_class, order_by))
            
            # 应用限制
            if limit:
                query = query.limit(limit)
            
            # 执行查询
            results = list(query.dicts())
            
            # 返回结果
            if limit == 1:
                return results[0] if results else None
            return results
            
        except Exception as e:
            logger.error(f"{self.log_prefix} 获取数据库记录出错: {e}")
            traceback.print_exc()
            return None if limit == 1 else []

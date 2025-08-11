import copy
import hashlib
import datetime
import asyncio
import json

from typing import Dict, Union, Optional, List

from src.common.logger import get_logger
from src.common.database.database import db
from src.common.database.database_model import GroupInfo


"""
GroupInfoManager 类方法功能摘要：
1. get_group_id - 根据平台和群号生成MD5哈希的唯一group_id
2. create_group_info - 创建新群组信息文档（自动合并默认值）
3. update_one_field - 更新单个字段值（若文档不存在则创建）
4. del_one_document - 删除指定group_id的文档
5. get_value - 获取单个字段值（返回实际值或默认值）
6. get_values - 批量获取字段值（任一字段无效则返回空字典）
7. add_member - 添加群成员
8. remove_member - 移除群成员
9. get_member_list - 获取群成员列表
"""


logger = get_logger("group_info")

JSON_SERIALIZED_FIELDS = ["member_list", "group_info"]

group_info_default = {
    "group_id": None,
    "group_name": None,
    "platform": "unknown",
    "group_number": "unknown",
    "group_impression": None,
    "short_impression": None,
    "member_list": [],
    "group_info": {},
    "create_time": None,
    "last_active": None,
    "member_count": 0,
}


class GroupInfoManager:
    def __init__(self):
        self.group_name_list = {}
        try:
            db.connect(reuse_if_open=True)
            # 设置连接池参数
            if hasattr(db, "execute_sql"):
                # 设置SQLite优化参数
                db.execute_sql("PRAGMA cache_size = -64000")  # 64MB缓存
                db.execute_sql("PRAGMA temp_store = memory")  # 临时存储在内存中
                db.execute_sql("PRAGMA mmap_size = 268435456")  # 256MB内存映射
            db.create_tables([GroupInfo], safe=True)
        except Exception as e:
            logger.error(f"数据库连接或 GroupInfo 表创建失败: {e}")

        # 初始化时读取所有group_name
        try:
            for record in GroupInfo.select(GroupInfo.group_id, GroupInfo.group_name).where(
                GroupInfo.group_name.is_null(False)
            ):
                if record.group_name:
                    self.group_name_list[record.group_id] = record.group_name
            logger.debug(f"已加载 {len(self.group_name_list)} 个群组名称 (Peewee)")
        except Exception as e:
            logger.error(f"从 Peewee 加载 group_name_list 失败: {e}")

    @staticmethod
    def get_group_id(platform: str, group_number: Union[int, str]) -> str:
        """获取群组唯一id"""
        # 添加空值检查，防止 platform 为 None 时出错
        if platform is None:
            platform = "unknown"
        elif "-" in platform:
            platform = platform.split("-")[1]

        components = [platform, str(group_number)]
        key = "_".join(components)
        return hashlib.md5(key.encode()).hexdigest()

    async def is_group_known(self, platform: str, group_number: int):
        """判断是否知道某个群组"""
        group_id = self.get_group_id(platform, group_number)

        def _db_check_known_sync(g_id: str):
            return GroupInfo.get_or_none(GroupInfo.group_id == g_id) is not None

        try:
            return await asyncio.to_thread(_db_check_known_sync, group_id)
        except Exception as e:
            logger.error(f"检查群组 {group_id} 是否已知时出错 (Peewee): {e}")
            return False

    @staticmethod
    async def create_group_info(group_id: str, data: Optional[dict] = None):
        """创建一个群组信息项"""
        if not group_id:
            logger.debug("创建失败，group_id不存在")
            return

        _group_info_default = copy.deepcopy(group_info_default)
        model_fields = GroupInfo._meta.fields.keys()  # type: ignore

        final_data = {"group_id": group_id}

        # Start with defaults for all model fields
        for key, default_value in _group_info_default.items():
            if key in model_fields:
                final_data[key] = default_value

        # Override with provided data
        if data:
            for key, value in data.items():
                if key in model_fields:
                    final_data[key] = value

        # Ensure group_id is correctly set from the argument
        final_data["group_id"] = group_id

        # Serialize JSON fields
        for key in JSON_SERIALIZED_FIELDS:
            if key in final_data:
                if isinstance(final_data[key], (list, dict)):
                    final_data[key] = json.dumps(final_data[key], ensure_ascii=False)
                elif final_data[key] is None:  # Default for lists is [], store as "[]"
                    final_data[key] = json.dumps([], ensure_ascii=False)

        def _db_create_sync(g_data: dict):
            try:
                GroupInfo.create(**g_data)
                return True
            except Exception as e:
                logger.error(f"创建 GroupInfo 记录 {g_data.get('group_id')} 失败 (Peewee): {e}")
                return False

        await asyncio.to_thread(_db_create_sync, final_data)

    async def _safe_create_group_info(self, group_id: str, data: Optional[dict] = None):
        """安全地创建群组信息，处理竞态条件"""
        if not group_id:
            logger.debug("创建失败，group_id不存在")
            return

        _group_info_default = copy.deepcopy(group_info_default)
        model_fields = GroupInfo._meta.fields.keys()  # type: ignore

        final_data = {"group_id": group_id}

        # Start with defaults for all model fields
        for key, default_value in _group_info_default.items():
            if key in model_fields:
                final_data[key] = default_value

        # Override with provided data
        if data:
            for key, value in data.items():
                if key in model_fields:
                    final_data[key] = value

        # Ensure group_id is correctly set from the argument
        final_data["group_id"] = group_id

        # Serialize JSON fields
        for key in JSON_SERIALIZED_FIELDS:
            if key in final_data:
                if isinstance(final_data[key], (list, dict)):
                    final_data[key] = json.dumps(final_data[key], ensure_ascii=False)
                elif final_data[key] is None:  # Default for lists is [], store as "[]"
                    final_data[key] = json.dumps([], ensure_ascii=False)

        def _db_safe_create_sync(g_data: dict):
            try:
                # 首先检查是否已存在
                existing = GroupInfo.get_or_none(GroupInfo.group_id == g_data["group_id"])
                if existing:
                    logger.debug(f"群组 {g_data['group_id']} 已存在，跳过创建")
                    return True

                # 尝试创建
                GroupInfo.create(**g_data)
                return True
            except Exception as e:
                if "UNIQUE constraint failed" in str(e):
                    logger.debug(f"检测到并发创建群组 {g_data.get('group_id')}，跳过错误")
                    return True  # 其他协程已创建，视为成功
                else:
                    logger.error(f"创建 GroupInfo 记录 {g_data.get('group_id')} 失败 (Peewee): {e}")
                    return False

        await asyncio.to_thread(_db_safe_create_sync, final_data)

    async def update_one_field(self, group_id: str, field_name: str, value, data: Optional[Dict] = None):
        """更新某一个字段，会补全"""
        if field_name not in GroupInfo._meta.fields:  # type: ignore
            logger.debug(f"更新'{field_name}'失败，未在 GroupInfo Peewee 模型中定义的字段。")
            return

        processed_value = value
        if field_name in JSON_SERIALIZED_FIELDS:
            if isinstance(value, (list, dict)):
                processed_value = json.dumps(value, ensure_ascii=False, indent=None)
            elif value is None:  # Store None as "[]" for JSON list fields
                processed_value = json.dumps([], ensure_ascii=False, indent=None)

        def _db_update_sync(g_id: str, f_name: str, val_to_set):
            import time

            start_time = time.time()
            try:
                record = GroupInfo.get_or_none(GroupInfo.group_id == g_id)
                query_time = time.time()

                if record:
                    setattr(record, f_name, val_to_set)
                    record.save()
                    save_time = time.time()

                    total_time = save_time - start_time
                    if total_time > 0.5:  # 如果超过500ms就记录日志
                        logger.warning(
                            f"数据库更新操作耗时 {total_time:.3f}秒 (查询: {query_time - start_time:.3f}s, 保存: {save_time - query_time:.3f}s) group_id={g_id}, field={f_name}"
                        )

                    return True, False  # Found and updated, no creation needed
                else:
                    total_time = time.time() - start_time
                    if total_time > 0.5:
                        logger.warning(f"数据库查询操作耗时 {total_time:.3f}秒 group_id={g_id}, field={f_name}")
                    return False, True  # Not found, needs creation
            except Exception as e:
                total_time = time.time() - start_time
                logger.error(f"数据库操作异常，耗时 {total_time:.3f}秒: {e}")
                raise

        found, needs_creation = await asyncio.to_thread(_db_update_sync, group_id, field_name, processed_value)

        if needs_creation:
            logger.info(f"{group_id} 不存在，将新建。")
            creation_data = data if data is not None else {}
            # Ensure platform and group_number are present for context if available from 'data'
            # but primarily, set the field that triggered the update.
            # The create_group_info will handle defaults and serialization.
            creation_data[field_name] = value  # Pass original value to create_group_info

            # Ensure platform and group_number are in creation_data if available,
            # otherwise create_group_info will use defaults.
            if data and "platform" in data:
                creation_data["platform"] = data["platform"]
            if data and "group_number" in data:
                creation_data["group_number"] = data["group_number"]

            # 使用安全的创建方法，处理竞态条件
            await self._safe_create_group_info(group_id, creation_data)

    @staticmethod
    async def del_one_document(group_id: str):
        """删除指定 group_id 的文档"""
        if not group_id:
            logger.debug("删除失败：group_id 不能为空")
            return

        def _db_delete_sync(g_id: str):
            try:
                query = GroupInfo.delete().where(GroupInfo.group_id == g_id)
                deleted_count = query.execute()
                return deleted_count
            except Exception as e:
                logger.error(f"删除 GroupInfo {g_id} 失败 (Peewee): {e}")
                return 0

        deleted_count = await asyncio.to_thread(_db_delete_sync, group_id)

        if deleted_count > 0:
            logger.debug(f"删除成功：group_id={group_id} (Peewee)")
        else:
            logger.debug(f"删除失败：未找到 group_id={group_id} 或删除未影响行 (Peewee)")

    @staticmethod
    async def get_value(group_id: str, field_name: str):
        """获取指定群组指定字段的值"""
        default_value_for_field = group_info_default.get(field_name)
        if field_name in JSON_SERIALIZED_FIELDS and default_value_for_field is None:
            default_value_for_field = []  # Ensure JSON fields default to [] if not in DB

        def _db_get_value_sync(g_id: str, f_name: str):
            record = GroupInfo.get_or_none(GroupInfo.group_id == g_id)
            if record:
                val = getattr(record, f_name, None)
                if f_name in JSON_SERIALIZED_FIELDS:
                    if isinstance(val, str):
                        try:
                            return json.loads(val)
                        except json.JSONDecodeError:
                            logger.warning(f"字段 {f_name} for {g_id} 包含无效JSON: {val}. 返回默认值.")
                            return []  # Default for JSON fields on error
                    elif val is None:  # Field exists in DB but is None
                        return []  # Default for JSON fields
                    # If val is already a list/dict (e.g. if somehow set without serialization)
                    return val  # Should ideally not happen if update_one_field is always used
                return val
            return None  # Record not found

        try:
            value_from_db = await asyncio.to_thread(_db_get_value_sync, group_id, field_name)
            if value_from_db is not None:
                return value_from_db
            if field_name in group_info_default:
                return default_value_for_field
            logger.warning(f"字段 {field_name} 在 group_info_default 中未定义，且在数据库中未找到。")
            return None  # Ultimate fallback
        except Exception as e:
            logger.error(f"获取字段 {field_name} for {group_id} 时出错 (Peewee): {e}")
            # Fallback to default in case of any error during DB access
            return default_value_for_field if field_name in group_info_default else None

    @staticmethod
    async def get_values(group_id: str, field_names: list) -> dict:
        """获取指定group_id文档的多个字段值，若不存在该字段，则返回该字段的全局默认值"""
        if not group_id:
            logger.debug("get_values获取失败：group_id不能为空")
            return {}

        result = {}

        def _db_get_record_sync(g_id: str):
            return GroupInfo.get_or_none(GroupInfo.group_id == g_id)

        record = await asyncio.to_thread(_db_get_record_sync, group_id)

        for field_name in field_names:
            if field_name not in GroupInfo._meta.fields:  # type: ignore
                if field_name in group_info_default:
                    result[field_name] = copy.deepcopy(group_info_default[field_name])
                    logger.debug(f"字段'{field_name}'不在Peewee模型中，使用默认配置值。")
                else:
                    logger.debug(f"get_values查询失败：字段'{field_name}'未在Peewee模型和默认配置中定义。")
                    result[field_name] = None
                continue

            if record:
                value = getattr(record, field_name)
                if value is not None:
                    result[field_name] = value
                else:
                    result[field_name] = copy.deepcopy(group_info_default.get(field_name))
            else:
                result[field_name] = copy.deepcopy(group_info_default.get(field_name))

        return result

    async def add_member(self, group_id: str, member_info: dict):
        """添加群成员（使用 last_active_time，不使用 join_time）"""
        if not group_id or not member_info:
            logger.debug("添加成员失败：group_id或member_info不能为空")
            return

        # 规范化成员字段
        normalized_member = dict(member_info)
        normalized_member.pop("join_time", None)
        if "last_active_time" not in normalized_member:
            normalized_member["last_active_time"] = datetime.datetime.now().timestamp()

        member_id = normalized_member.get("user_id")
        if not member_id:
            logger.debug("添加成员失败：缺少 user_id")
            return

        # 获取当前成员列表
        current_members = await self.get_value(group_id, "member_list")
        if not isinstance(current_members, list):
            current_members = []

        # 移除已存在的同 user_id 成员
        current_members = [m for m in current_members if m.get("user_id") != member_id]

        # 添加新成员
        current_members.append(normalized_member)

        # 更新成员列表和成员数量
        await self.update_one_field(group_id, "member_list", current_members)
        await self.update_one_field(group_id, "member_count", len(current_members))
        await self.update_one_field(group_id, "last_active", datetime.datetime.now().timestamp())

        logger.info(f"群组 {group_id} 添加/更新成员 {normalized_member.get('nickname', member_id)} 成功")

    async def remove_member(self, group_id: str, user_id: str):
        """移除群成员"""
        if not group_id or not user_id:
            logger.debug("移除成员失败：group_id或user_id不能为空")
            return

        # 获取当前成员列表
        current_members = await self.get_value(group_id, "member_list")
        if not isinstance(current_members, list):
            logger.debug(f"群组 {group_id} 成员列表为空或格式错误")
            return

        # 移除指定成员
        original_count = len(current_members)
        current_members = [m for m in current_members if m.get("user_id") != user_id]
        new_count = len(current_members)

        if new_count < original_count:
            # 更新成员列表和成员数量
            await self.update_one_field(group_id, "member_list", current_members)
            await self.update_one_field(group_id, "member_count", new_count)
            await self.update_one_field(group_id, "last_active", datetime.datetime.now().timestamp())
            logger.info(f"群组 {group_id} 移除成员 {user_id} 成功")
        else:
            logger.debug(f"群组 {group_id} 中未找到成员 {user_id}")

    async def get_member_list(self, group_id: str) -> List[dict]:
        """获取群成员列表"""
        if not group_id:
            logger.debug("获取成员列表失败：group_id不能为空")
            return []

        members = await self.get_value(group_id, "member_list")
        if isinstance(members, list):
            return members
        return []

    async def get_or_create_group(
        self, platform: str, group_number: int, group_name: str = None
    ) -> str:
        """
        根据 platform 和 group_number 获取 group_id。
        如果对应的群组不存在，则使用提供的信息创建新群组。
        使用try-except处理竞态条件，避免重复创建错误。
        """
        group_id = self.get_group_id(platform, group_number)

        def _db_get_or_create_sync(g_id: str, init_data: dict):
            """原子性的获取或创建操作"""
            # 首先尝试获取现有记录
            record = GroupInfo.get_or_none(GroupInfo.group_id == g_id)
            if record:
                return record, False  # 记录存在，未创建

            # 记录不存在，尝试创建
            try:
                GroupInfo.create(**init_data)
                return GroupInfo.get(GroupInfo.group_id == g_id), True  # 创建成功
            except Exception as e:
                # 如果创建失败（可能是因为竞态条件），再次尝试获取
                if "UNIQUE constraint failed" in str(e):
                    logger.debug(f"检测到并发创建群组 {g_id}，获取现有记录")
                    record = GroupInfo.get_or_none(GroupInfo.group_id == g_id)
                    if record:
                        return record, False  # 其他协程已创建，返回现有记录
                # 如果仍然失败，重新抛出异常
                raise e

        initial_data = {
            "group_id": group_id,
            "platform": platform,
            "group_number": str(group_number),
            "group_name": group_name,
            "create_time": datetime.datetime.now().timestamp(),
            "last_active": datetime.datetime.now().timestamp(),
            "member_count": 0,
            "member_list": [],
            "group_info": {},
        }

        # 序列化JSON字段
        for key in JSON_SERIALIZED_FIELDS:
            if key in initial_data:
                if isinstance(initial_data[key], (list, dict)):
                    initial_data[key] = json.dumps(initial_data[key], ensure_ascii=False)
                elif initial_data[key] is None:
                    initial_data[key] = json.dumps([], ensure_ascii=False)

        model_fields = GroupInfo._meta.fields.keys()  # type: ignore
        filtered_initial_data = {k: v for k, v in initial_data.items() if v is not None and k in model_fields}

        record, was_created = await asyncio.to_thread(_db_get_or_create_sync, group_id, filtered_initial_data)

        if was_created:
            logger.info(f"群组 {platform}:{group_number} (group_id: {group_id}) 不存在，将创建新记录 (Peewee)。")
            logger.info(f"已为 {group_id} 创建新记录，初始数据 (filtered for model): {filtered_initial_data}")
        else:
            logger.debug(f"群组 {platform}:{group_number} (group_id: {group_id}) 已存在，返回现有记录。")

        return group_id

    async def get_group_info_by_name(self, group_name: str) -> dict | None:
        """根据 group_name 查找群组并返回基本信息 (如果找到)"""
        if not group_name:
            logger.debug("get_group_info_by_name 获取失败：group_name 不能为空")
            return None

        found_group_id = None
        for gid, name_in_cache in self.group_name_list.items():
            if name_in_cache == group_name:
                found_group_id = gid
                break

        if not found_group_id:

            def _db_find_by_name_sync(g_name_to_find: str):
                return GroupInfo.get_or_none(GroupInfo.group_name == g_name_to_find)

            record = await asyncio.to_thread(_db_find_by_name_sync, group_name)
            if record:
                found_group_id = record.group_id
                if (
                    found_group_id not in self.group_name_list
                    or self.group_name_list[found_group_id] != group_name
                ):
                    self.group_name_list[found_group_id] = group_name
            else:
                logger.debug(f"数据库中也未找到名为 '{group_name}' 的群组 (Peewee)")
                return None

        if found_group_id:
            required_fields = [
                "group_id",
                "platform",
                "group_number",
                "group_name",
                "group_impression",
                "short_impression",
                "member_count",
                "create_time",
                "last_active",
            ]
            valid_fields_to_get = [
                f
                for f in required_fields
                if f in GroupInfo._meta.fields or f in group_info_default  # type: ignore
            ]

            group_data = await self.get_values(found_group_id, valid_fields_to_get)

            if group_data:
                final_result = {key: group_data.get(key) for key in required_fields}
                return final_result
            else:
                logger.warning(f"找到了 group_id '{found_group_id}' 但 get_values 返回空 (Peewee)")
                return None

        logger.error(f"逻辑错误：未能为 '{group_name}' 确定 group_id (Peewee)")
        return None


group_info_manager = None


def get_group_info_manager():
    global group_info_manager
    if group_info_manager is None:
        group_info_manager = GroupInfoManager()
    return group_info_manager

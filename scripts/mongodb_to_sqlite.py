import os
import json
import sys  # 新增系统模块导入

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from typing import Dict, Any, List, Optional, Type
from dataclasses import dataclass, field
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from peewee import Model, Field, IntegrityError

from src.common.database.database import db
from src.common.database.database_model import (
    ChatStreams, LLMUsage, Emoji, Messages, Images, ImageDescriptions,
    OnlineTime, PersonInfo, Knowledges, ThinkingLog, GraphNodes, GraphEdges
)
from src.common.logger_manager import get_logger

logger = get_logger("mongodb_to_sqlite")


@dataclass
class MigrationConfig:
    """迁移配置类"""
    mongo_collection: str
    target_model: Type[Model]
    field_mapping: Dict[str, str]
    batch_size: int = 500
    enable_validation: bool = True
    skip_duplicates: bool = True
    unique_fields: List[str] = field(default_factory=list)  # 用于重复检查的字段


@dataclass
class MigrationStats:
    """迁移统计信息"""
    total_documents: int = 0
    processed_count: int = 0
    success_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    duplicate_count: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_error(self, doc_id: Any, error: str, doc_data: Optional[Dict] = None):
        """添加错误记录"""
        self.errors.append({
            'doc_id': str(doc_id),
            'error': error,
            'timestamp': datetime.now().isoformat(),
            'doc_data': doc_data
        })
        self.error_count += 1


class MongoToSQLiteMigrator:
    """MongoDB到SQLite数据迁移器 - 使用Peewee ORM"""
    
    def __init__(self, mongo_uri: Optional[str] = None, database_name: Optional[str] = None):
        self.database_name = database_name or os.getenv("DATABASE_NAME", "MegBot")
        self.mongo_uri = mongo_uri or self._build_mongo_uri()
        self.mongo_client: Optional[MongoClient] = None
        self.mongo_db = None
        
        # 迁移配置
        self.migration_configs = self._initialize_migration_configs()
    
    def _build_mongo_uri(self) -> str:
        """构建MongoDB连接URI"""
        if mongo_uri := os.getenv("MONGODB_URI"):
            return mongo_uri
        
        user = os.getenv('MONGODB_USER')
        password = os.getenv('MONGODB_PASS')
        host = os.getenv('MONGODB_HOST', 'localhost')
        port = os.getenv('MONGODB_PORT', '27017')
        auth_source = os.getenv('MONGODB_AUTH_SOURCE', 'admin')
        
        if user and password:
            return f"mongodb://{user}:{password}@{host}:{port}/{self.database_name}?authSource={auth_source}"
        else:
            return f"mongodb://{host}:{port}/{self.database_name}"
    
    def _initialize_migration_configs(self) -> List[MigrationConfig]:
        """初始化迁移配置"""
        return [
            # 表情包迁移配置
            MigrationConfig(
                mongo_collection="emoji",
                target_model=Emoji,
                field_mapping={
                    "full_path": "full_path",
                    "format": "format", 
                    "hash": "emoji_hash",
                    "description": "description",
                    "emotion": "emotion",
                    "usage_count": "usage_count",
                    "last_used_time": "last_used_time",
                    "last_used_time": "record_time" # 这个纯粹是为了应付整体映射格式，实际上直接用当前时间戳填了record_time
                },
                unique_fields=["full_path", "emoji_hash"]
            ),
            
            # 聊天流迁移配置
            MigrationConfig(
                mongo_collection="chat_streams",
                target_model=ChatStreams,
                field_mapping={
                    "stream_id": "stream_id",
                    "create_time": "create_time",
                    "group_info.platform": "group_platform",# 由于Mongodb处理私聊时会让group_info值为null，而新的数据库不允许为null，所以私聊聊天流是没法迁移的，等更新吧。
                    "group_info.group_id": "group_id",  # 同上
                    "group_info.group_name": "group_name", # 同上
                    "last_active_time": "last_active_time",
                    "platform": "platform",
                    "user_info.platform": "user_platform",
                    "user_info.user_id": "user_id",
                    "user_info.user_nickname": "user_nickname",
                    "user_info.user_cardname": "user_cardname"
                },
                unique_fields=["stream_id"]
            ),
            
            # LLM使用记录迁移配置
            MigrationConfig(
                mongo_collection="llm_usage",
                target_model=LLMUsage,
                field_mapping={
                    "model_name": "model_name",
                    "user_id": "user_id",
                    "request_type": "request_type",
                    "endpoint": "endpoint",
                    "prompt_tokens": "prompt_tokens",
                    "completion_tokens": "completion_tokens",
                    "total_tokens": "total_tokens",
                    "cost": "cost",
                    "status": "status",
                    "timestamp": "timestamp"
                },
                unique_fields=["user_id", "timestamp"]  # 组合唯一性
            ),
            
            # 消息迁移配置
            MigrationConfig(
                mongo_collection="messages",
                target_model=Messages,
                field_mapping={
                    "message_id": "message_id",
                    "time": "time",
                    "chat_id": "chat_id",
                    "chat_info.stream_id": "chat_info_stream_id",
                    "chat_info.platform": "chat_info_platform",
                    "chat_info.user_info.platform": "chat_info_user_platform",
                    "chat_info.user_info.user_id": "chat_info_user_id",
                    "chat_info.user_info.user_nickname": "chat_info_user_nickname",
                    "chat_info.user_info.user_cardname": "chat_info_user_cardname",
                    "chat_info.group_info.platform": "chat_info_group_platform",
                    "chat_info.group_info.group_id": "chat_info_group_id",
                    "chat_info.group_info.group_name": "chat_info_group_name",
                    "chat_info.create_time": "chat_info_create_time",
                    "chat_info.last_active_time": "chat_info_last_active_time",
                    "user_info.platform": "user_platform",
                    "user_info.user_id": "user_id",
                    "user_info.user_nickname": "user_nickname",
                    "user_info.user_cardname": "user_cardname",
                    "processed_plain_text": "processed_plain_text",
                    "detailed_plain_text": "detailed_plain_text",
                    "memorized_times": "memorized_times"
                },
                unique_fields=["message_id"]
            ),
            
            # 图片迁移配置
            MigrationConfig(
                mongo_collection="images",
                target_model=Images,
                field_mapping={
                    "hash": "emoji_hash",
                    "description": "description",
                    "path": "path",
                    "timestamp": "timestamp",
                    "type": "type"
                },
                unique_fields=["path"]
            ),
            
            # 图片描述迁移配置
            MigrationConfig(
                mongo_collection="image_descriptions",
                target_model=ImageDescriptions,
                field_mapping={
                    "type": "type",
                    "hash": "image_description_hash",
                    "description": "description",
                    "timestamp": "timestamp"
                },
                unique_fields=["image_description_hash", "type"]
            ),
            
            # 在线时长迁移配置
            MigrationConfig(
                mongo_collection="online_time",
                target_model=OnlineTime,
                field_mapping={
                    "timestamp": "timestamp",
                    "duration": "duration",
                    "start_timestamp": "start_timestamp",
                    "end_timestamp": "end_timestamp"
                },
                unique_fields=["start_timestamp", "end_timestamp"]
            ),
            
            # 个人信息迁移配置
            MigrationConfig(
                mongo_collection="person_info",
                target_model=PersonInfo,
                field_mapping={
                    "person_id": "person_id",
                    "person_name": "person_name",
                    "name_reason": "name_reason",
                    "platform": "platform",
                    "user_id": "user_id",
                    "nickname": "nickname",
                    "relationship_value": "relationship_value",
                    "konw_time": "know_time",
                    "msg_interval": "msg_interval",
                    "msg_interval_list": "msg_interval_list"
                },
                unique_fields=["person_id"]
            ),
            
            # 知识库迁移配置
            MigrationConfig(
                mongo_collection="knowledges",
                target_model=Knowledges,
                field_mapping={
                    "content": "content",
                    "embedding": "embedding"
                },
                unique_fields=["content"]  # 假设内容唯一
            ),
            
            # 思考日志迁移配置
            MigrationConfig(
                mongo_collection="thinking_log",
                target_model=ThinkingLog,
                field_mapping={
                    "chat_id": "chat_id",
                    "trigger_text": "trigger_text",
                    "response_text": "response_text",
                    "trigger_info": "trigger_info_json",
                    "response_info": "response_info_json",
                    "timing_results": "timing_results_json",
                    "chat_history": "chat_history_json",
                    "chat_history_in_thinking": "chat_history_in_thinking_json",
                    "chat_history_after_response": "chat_history_after_response_json",
                    "heartflow_data": "heartflow_data_json",
                    "reasoning_data": "reasoning_data_json",
                },
                unique_fields=["chat_id", "trigger_text"]
            ),
            
            # 图节点迁移配置
            MigrationConfig(
                mongo_collection="graph_data.nodes",
                target_model=GraphNodes,
                field_mapping={
                    "concept": "concept",
                    "memory_items": "memory_items",
                    "hash": "hash",
                    "created_time": "created_time",
                    "last_modified": "last_modified"
                },
                unique_fields=["concept"]
            ),
            
            # 图边迁移配置
            MigrationConfig(
                mongo_collection="graph_data.edges",
                target_model=GraphEdges,
                field_mapping={
                    "source": "source",
                    "target": "target",
                    "strength": "strength",
                    "hash": "hash",
                    "created_time": "created_time",
                    "last_modified": "last_modified"
                },
                unique_fields=["source", "target"]  # 组合唯一性
            )
        ]
    
    def connect_mongodb(self) -> bool:
        """连接到MongoDB"""
        try:
            self.mongo_client = MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000, 
                maxPoolSize=10
            )
            
            # 测试连接
            self.mongo_client.admin.command('ping')
            self.mongo_db = self.mongo_client[self.database_name]
            
            logger.info(f"成功连接到MongoDB: {self.database_name}")
            return True
            
        except ConnectionFailure as e:
            logger.error(f"MongoDB连接失败: {e}")
            return False
        except Exception as e:
            logger.error(f"MongoDB连接异常: {e}")
            return False
    
    def disconnect_mongodb(self):
        """断开MongoDB连接"""
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("MongoDB连接已关闭")
    
    def _get_nested_value(self, document: Dict[str, Any], field_path: str) -> Any:
        """获取嵌套字段的值"""
        if "." not in field_path:
            return document.get(field_path)
        
        parts = field_path.split(".")
        value = document
        
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
            
            if value is None:
                break
        
        return value
    
    def _convert_field_value(self, value: Any, target_field: Field) -> Any:
        """根据目标字段类型转换值"""
        if value is None:
            return None
        
        field_type = target_field.__class__.__name__
        
        try:
            if target_field.name == "record_time" and field_type == "DateTimeField":
                return datetime.now()

            if field_type in ["CharField", "TextField"]:
                if isinstance(value, (list, dict)):
                    return json.dumps(value, ensure_ascii=False)
                return str(value) if value is not None else ""
            
            elif field_type == "IntegerField":
                if isinstance(value, str):
                    # 处理字符串数字
                    clean_value = value.strip()
                    if clean_value.replace('.', '').replace('-', '').isdigit():
                        return int(float(clean_value))
                    return 0
                return int(value) if value is not None else 0
            
            elif field_type in ["FloatField", "DoubleField"]:
                return float(value) if value is not None else 0.0
            
            elif field_type == "BooleanField":
                if isinstance(value, str):
                    return value.lower() in ('true', '1', 'yes', 'on')
                return bool(value)
            
            elif field_type == "DateTimeField":
                if isinstance(value, (int, float)):
                    return datetime.fromtimestamp(value)
                elif isinstance(value, str):
                    try:
                        # 尝试解析ISO格式日期
                        return datetime.fromisoformat(value.replace('Z', '+00:00'))
                    except ValueError:
                        try:
                            # 尝试解析时间戳字符串
                            return datetime.fromtimestamp(float(value))
                        except ValueError:
                            return datetime.now()
                return datetime.now()
            
            return value
            
        except (ValueError, TypeError) as e:
            logger.warning(f"字段值转换失败 ({field_type}): {value} -> {e}")
            return self._get_default_value_for_field(target_field)
        
    def _get_default_value_for_field(self, field: Field) -> Any:
        """获取字段的默认值"""
        field_type = field.__class__.__name__
        
        if hasattr(field, 'default') and field.default is not None:
            return field.default
        
        if field.null:
            return None
            
        # 根据字段类型返回默认值
        if field_type in ["CharField", "TextField"]:
            return ""
        elif field_type == "IntegerField":
            return 0
        elif field_type in ["FloatField", "DoubleField"]:
            return 0.0
        elif field_type == "BooleanField":
            return False
        elif field_type == "DateTimeField":
            return datetime.now()
        
        return None
    
    def _check_duplicate_by_unique_fields(self, model: Type[Model], data: Dict[str, Any], 
                                        unique_fields: List[str]) -> bool:
        """根据唯一字段检查重复"""
        if not unique_fields:
            return False
        
        try:
            query = model.select()
            for field_name in unique_fields:
                if field_name in data and data[field_name] is not None:
                    field_obj = getattr(model, field_name)
                    query = query.where(field_obj == data[field_name])
            
            return query.exists()
        except Exception as e:
            logger.debug(f"重复检查失败: {e}")
            return False
    
    def _create_model_instance(self, model: Type[Model], data: Dict[str, Any]) -> Optional[Model]:
        """使用ORM创建模型实例"""
        try:
            # 过滤掉不存在的字段
            valid_data = {}
            for field_name, value in data.items():
                if hasattr(model, field_name):
                    valid_data[field_name] = value
                else:
                    logger.debug(f"跳过未知字段: {field_name}")
            
            # 创建实例
            instance = model.create(**valid_data)
            return instance
            
        except IntegrityError as e:
            # 处理唯一约束冲突等完整性错误
            logger.debug(f"完整性约束冲突: {e}")
            return None
        except Exception as e:
            logger.error(f"创建模型实例失败: {e}")
            return None
    
    def migrate_collection(self, config: MigrationConfig) -> MigrationStats:
        """迁移单个集合 - 使用ORM方式"""
        stats = MigrationStats()
        
        logger.info(f"开始迁移: {config.mongo_collection} -> {config.target_model._meta.table_name}")
        
        try:
            # 获取MongoDB集合
            mongo_collection = self.mongo_db[config.mongo_collection]
            stats.total_documents = mongo_collection.count_documents({})
            
            if stats.total_documents == 0:
                logger.warning(f"集合 {config.mongo_collection} 为空，跳过迁移")
                return stats
            
            logger.info(f"待迁移文档数量: {stats.total_documents}")
            
            # 逐个处理文档
            batch_count = 0
            for mongo_doc in mongo_collection.find().batch_size(config.batch_size):
                try:
                    stats.processed_count += 1
                    doc_id = mongo_doc.get('_id', 'unknown')
                    
                    # 构建目标数据
                    target_data = {}
                    for mongo_field, sqlite_field in config.field_mapping.items():
                        value = self._get_nested_value(mongo_doc, mongo_field)
                        
                        # 获取目标字段对象并转换类型
                        if hasattr(config.target_model, sqlite_field):
                            field_obj = getattr(config.target_model, sqlite_field)
                            converted_value = self._convert_field_value(value, field_obj)
                            target_data[sqlite_field] = converted_value
                    
                    # 重复检查
                    if config.skip_duplicates and self._check_duplicate_by_unique_fields(
                        config.target_model, target_data, config.unique_fields
                    ):
                        stats.duplicate_count += 1
                        stats.skipped_count += 1
                        logger.debug(f"跳过重复记录: {doc_id}")
                        continue
                    
                    # 使用ORM创建实例
                    with db.atomic():  # 每个实例的事务保护
                        instance = self._create_model_instance(config.target_model, target_data)
                        
                        if instance:
                            stats.success_count += 1
                        else:
                            stats.add_error(doc_id, "ORM创建实例失败", target_data)
                
                except Exception as e:
                    doc_id = mongo_doc.get('_id', 'unknown')
                    stats.add_error(doc_id, f"处理文档异常: {e}", mongo_doc)
                    logger.error(f"处理文档失败 (ID: {doc_id}): {e}")
                
                # 进度报告
                batch_count += 1
                if batch_count % config.batch_size == 0:
                    progress = (stats.processed_count / stats.total_documents) * 100
                    logger.info(
                        f"迁移进度: {stats.processed_count}/{stats.total_documents} "
                        f"({progress:.1f}%) - 成功: {stats.success_count}, "
                        f"错误: {stats.error_count}, 跳过: {stats.skipped_count}"
                    )
            
            logger.info(
                f"迁移完成: {config.mongo_collection} -> {config.target_model._meta.table_name}\n"
                f"总计: {stats.total_documents}, 成功: {stats.success_count}, "
                f"错误: {stats.error_count}, 跳过: {stats.skipped_count}, 重复: {stats.duplicate_count}"
            )
            
        except Exception as e:
            logger.error(f"迁移集合 {config.mongo_collection} 时发生异常: {e}")
            stats.add_error("collection_error", str(e))
        
        return stats
    
    def migrate_all(self) -> Dict[str, MigrationStats]:
        """执行所有迁移任务"""
        logger.info("开始执行数据库迁移...")
        
        if not self.connect_mongodb():
            logger.error("无法连接到MongoDB，迁移终止")
            return {}
        
        all_stats = {}
        
        try:
            for config in self.migration_configs:
                logger.info(f"\n开始处理集合: {config.mongo_collection}")
                stats = self.migrate_collection(config)
                all_stats[config.mongo_collection] = stats
                
                # 错误率检查
                if stats.processed_count > 0:
                    error_rate = stats.error_count / stats.processed_count
                    if error_rate > 0.1:  # 错误率超过10%
                        logger.warning(
                            f"集合 {config.mongo_collection} 错误率较高: {error_rate:.1%} "
                            f"({stats.error_count}/{stats.processed_count})"
                        )
        
        finally:
            self.disconnect_mongodb()
        
        self._print_migration_summary(all_stats)
        return all_stats
    
    def _print_migration_summary(self, all_stats: Dict[str, MigrationStats]):
        """打印迁移汇总信息"""
        logger.info("\n" + "="*60)
        logger.info("数据迁移汇总报告")
        logger.info("="*60)
        
        total_processed = sum(stats.processed_count for stats in all_stats.values())
        total_success = sum(stats.success_count for stats in all_stats.values())
        total_errors = sum(stats.error_count for stats in all_stats.values())
        total_skipped = sum(stats.skipped_count for stats in all_stats.values())
        total_duplicates = sum(stats.duplicate_count for stats in all_stats.values())
        
        # 表头
        logger.info(f"{'集合名称':<20} | {'处理':<6} | {'成功':<6} | {'错误':<6} | {'跳过':<6} | {'重复':<6} | {'成功率':<8}")
        logger.info("-" * 75)
        
        for collection_name, stats in all_stats.items():
            success_rate = (stats.success_count / stats.processed_count * 100) if stats.processed_count > 0 else 0
            logger.info(
                f"{collection_name:<20} | "
                f"{stats.processed_count:<6} | "
                f"{stats.success_count:<6} | "  
                f"{stats.error_count:<6} | "
                f"{stats.skipped_count:<6} | "
                f"{stats.duplicate_count:<6} | "
                f"{success_rate:<7.1f}%"
            )
        
        logger.info("-" * 75)
        total_success_rate = (total_success / total_processed * 100) if total_processed > 0 else 0
        logger.info(
            f"{'总计':<20} | "
            f"{total_processed:<6} | "
            f"{total_success:<6} | "
            f"{total_errors:<6} | "
            f"{total_skipped:<6} | "
            f"{total_duplicates:<6} | "
            f"{total_success_rate:<7.1f}%"
        )
        
        if total_errors > 0:
            logger.warning(f"\n⚠️  存在 {total_errors} 个错误，请检查日志详情")
        
        if total_duplicates > 0:
            logger.info(f"ℹ️  跳过了 {total_duplicates} 个重复记录")
        
        logger.info("="*60)
    
    def add_migration_config(self, config: MigrationConfig):
        """添加新的迁移配置"""
        self.migration_configs.append(config)
    
    def migrate_single_collection(self, collection_name: str) -> Optional[MigrationStats]:
        """迁移单个指定的集合"""
        config = next((c for c in self.migration_configs if c.mongo_collection == collection_name), None)
        if not config:
            logger.error(f"未找到集合 {collection_name} 的迁移配置")
            return None
        
        if not self.connect_mongodb():
            logger.error("无法连接到MongoDB")
            return None
        
        try:
            stats = self.migrate_collection(config)
            self._print_migration_summary({collection_name: stats})
            return stats
        finally:
            self.disconnect_mongodb()
    
    def export_error_report(self, all_stats: Dict[str, MigrationStats], filepath: str):
        """导出错误报告"""
        error_report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                collection: {
                    'total': stats.total_documents,
                    'processed': stats.processed_count,
                    'success': stats.success_count,
                    'errors': stats.error_count,
                    'skipped': stats.skipped_count,
                    'duplicates': stats.duplicate_count
                }
                for collection, stats in all_stats.items()
            },
            'errors': {
                collection: stats.errors
                for collection, stats in all_stats.items()
                if stats.errors
            }
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(error_report, f, ensure_ascii=False, indent=2)
            logger.info(f"错误报告已导出到: {filepath}")
        except Exception as e:
            logger.error(f"导出错误报告失败: {e}")


def main():
    """主程序入口"""
    migrator = MongoToSQLiteMigrator()
    
    # 执行迁移
    migration_results = migrator.migrate_all()
    
    # 导出错误报告（如果有错误）
    if any(stats.error_count > 0 for stats in migration_results.values()):
        error_report_path = f"migration_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        migrator.export_error_report(migration_results, error_report_path)
    
    logger.info("数据迁移完成！")


if __name__ == "__main__":
    main()
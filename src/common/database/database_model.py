from peewee import Model, DoubleField, IntegerField, SqliteDatabase, BooleanField, TextField, FloatField

# 请在此处定义您的数据库实例。
# 您需要取消注释并配置适合您的数据库的部分。
# 例如，对于 SQLite:
db = SqliteDatabase('my_application.db')
#
# 对于 PostgreSQL:
# db = PostgresqlDatabase('your_db_name', user='your_user', password='your_password',
#                         host='localhost', port=5432)
#
# 对于 MySQL:
# db = MySQLDatabase('your_db_name', user='your_user', password='your_password',
#                    host='localhost', port=3306)

# 定义一个基础模型是一个好习惯，所有其他模型都应继承自它。
# 这允许您在一个地方为所有模型指定数据库。
class BaseModel(Model):
    class Meta:
        # 将下面的 'db' 替换为您实际的数据库实例变量名。
        database = db  # 例如: database = my_actual_db_instance
        pass # 在用户定义数据库实例之前，此处为占位符

class ChatStreams(BaseModel):
    """
    用于存储流式记录数据的模型，类似于提供的 MongoDB 结构。
    """
    # stream_id: "a544edeb1a9b73e3e1d77dff36e41264"
    # 假设 stream_id 是唯一的，并为其创建索引以提高查询性能。
    stream_id = TextField(unique=True, index=True)

    # create_time: 1746096761.4490178 (时间戳，精确到小数点后7位)
    # DoubleField 用于存储浮点数，适合此类时间戳。
    create_time = DoubleField()

    # group_info 字段:
    #   platform: "qq"
    #   group_id: "941657197"
    #   group_name: "测试"
    group_platform = TextField()
    group_id = TextField()
    group_name = TextField()

    # last_active_time: 1746623771.4825106 (时间戳，精确到小数点后7位)
    last_active_time = DoubleField()

    # platform: "qq" (顶层平台字段)
    platform = TextField()

    # user_info 字段:
    #   platform: "qq"
    #   user_id: "1787882683"
    #   user_nickname: "墨梓柒(IceSakurary)"
    #   user_cardname: ""
    user_platform = TextField()
    user_id = TextField()
    user_nickname = TextField()
    # user_cardname 可能为空字符串或不存在，设置 null=True 更具灵活性。
    user_cardname = TextField(null=True)

    class Meta:
        # 如果 BaseModel.Meta.database 已设置，则此模型将继承该数据库配置。
        # 如果不使用带有数据库实例的 BaseModel，或者想覆盖它，
        # 请取消注释并在下面设置数据库实例：
        # database = db 
        table_name = 'chat_streams' # 可选：明确指定数据库中的表名

class LLMUsage(BaseModel):
    """
    用于存储 API 使用日志数据的模型。
    """
    model_name = TextField()
    user_id = TextField()
    request_type = TextField()
    endpoint = TextField()
    prompt_tokens = IntegerField()
    completion_tokens = IntegerField()
    total_tokens = IntegerField()
    cost = DoubleField()
    status = TextField()
    # timestamp: "$date": "2025-05-01T18:52:50.870Z" (存储为字符串)
    timestamp = TextField()

    class Meta:
        # 如果 BaseModel.Meta.database 已设置，则此模型将继承该数据库配置。
        # database = db 
        table_name = 'llm_usage'

class Emoji(BaseModel):
    """表情包"""

    full_path = TextField(unique=True, index=True)  # 文件的完整路径 (包括文件名)
    format = TextField()  # 图片格式
    hash = TextField(index=True)  # 表情包的哈希值
    description = TextField()  # 表情包的描述
    query_count = IntegerField(default=0)  # 查询次数（用于统计表情包被查询描述的次数）
    is_registered = BooleanField(default=False)  # 是否已注册
    is_banned = BooleanField(default=False)  # 是否被禁止注册
    # emotion: list[str]  # 表情包的情感标签 - 存储为文本，应用层处理序列化/反序列化
    emotion = TextField(null=True)
    record_time = FloatField()  # 记录时间（被创建的时间）
    register_time = FloatField(null=True)  # 注册时间（被注册为可用表情包的时间）
    usage_count = IntegerField(default=0)  # 使用次数（被使用的次数）
    last_used_time = FloatField(null=True)  # 上次使用时间

    class Meta:
        # database = db # 继承自 BaseModel
        table_name = 'emoji'

class Messages(BaseModel):
    """
    用于存储消息数据的模型。
    """
    message_id = IntegerField(index=True) # 消息 ID
    time = DoubleField() # 消息时间戳

    chat_id = TextField(index=True) # 对应的 ChatStreams stream_id

    # 从 chat_info 扁平化而来的字段
    chat_info_stream_id = TextField()
    chat_info_platform = TextField()
    chat_info_user_platform = TextField()
    chat_info_user_id = TextField()
    chat_info_user_nickname = TextField()
    chat_info_user_cardname = TextField(null=True)
    chat_info_group_platform = TextField(null=True) # 群聊信息可能不存在
    chat_info_group_id = TextField(null=True)
    chat_info_group_name = TextField(null=True)
    chat_info_create_time = DoubleField()
    chat_info_last_active_time = DoubleField()

    # 从顶层 user_info 扁平化而来的字段 (消息发送者信息)
    user_platform = TextField()
    user_id = TextField()
    user_nickname = TextField()
    user_cardname = TextField(null=True)

    processed_plain_text = TextField(null=True) # 处理后的纯文本消息
    detailed_plain_text = TextField(null=True) # 详细的纯文本消息
    memorized_times = IntegerField(default=0) # 被记忆的次数

    class Meta:
        # database = db # 继承自 BaseModel
        table_name = 'messages'

class Images(BaseModel):
    """
    用于存储图像信息的模型。
    """
    hash = TextField(index=True)  # 图像的哈希值
    description = TextField(null=True)  # 图像的描述
    path = TextField(unique=True)  # 图像文件的路径
    timestamp = FloatField()  # 时间戳
    type = TextField()  # 图像类型，例如 "emoji"

    class Meta:
        # database = db # 继承自 BaseModel
        table_name = 'images'

class ImageDescriptions(BaseModel):
    """
    用于存储图像描述信息的模型。
    """
    type = TextField()  # 类型，例如 "emoji"
    hash = TextField(index=True)  # 图像的哈希值
    description = TextField()  # 图像的描述
    timestamp = FloatField()  # 时间戳

    class Meta:
        # database = db # 继承自 BaseModel
        table_name = 'image_descriptions'

class OnlineTime(BaseModel):
    """
    用于存储在线时长记录的模型。
    """
    # timestamp: "$date": "2025-05-01T18:52:18.191Z" (存储为字符串)
    timestamp = TextField()
    duration = IntegerField()  # 时长，单位分钟

    class Meta:
        # database = db # 继承自 BaseModel
        table_name = 'online_time'


"""
该目录存放各类数据库Model（DO）的Manager类，所有Model均在Manager进行CURD操作
项目其他部分不直接访问DO，而是通过Manager获得的DTO对象进行操作

1. 项目实现了 global_cache 缓存机制，缓存键规范：
  - f"{model_name}:pk:{pk_value}"：主键缓存，主键缓存可直接获取DTO对象
    - model_name：DO名称
    - pk_value：主键值 - 对于联合主键，请使用冒号':'分隔
        - 例如：f"chat_group_user:pk:{group_id}:{user_id}"
  - f"{model_name}:{index_name}:{index_value}"：索引缓存，要求索引缓存单射到主键缓存
    - model_name：DO名称
    - index_name：索引名称
    - index_value：索引值 - 对于联合索引，请使用冒号':'分隔
      - 例如：f"chat_user:platform_info:{platform}:{platform_user_id}"
"""
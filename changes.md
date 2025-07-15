# 插件API与规范修改

1. 现在`plugin_system`的`__init__.py`文件中包含了所有插件API的导入，用户可以直接使用`from plugin_system import *`来导入所有API。

2. register_plugin函数现在转移到了`plugin_system.apis.plugin_register_api`模块中，用户可以通过`from plugin_system.apis.plugin_register_api import register_plugin`来导入。

3. 现在强制要求的property如下：
    - `plugin_name`: 插件名称，必须是唯一的。（与文件夹相同）
    - `enable_plugin`: 是否启用插件，默认为`True`。
    - `dependencies`: 插件依赖的其他插件列表，默认为空。**现在并不检查（也许）**
    - `python_dependencies`: 插件依赖的Python包列表，默认为空。**现在并不检查**
    - `config_file_name`: 插件配置文件名，默认为`config.toml`。
    - `config_schema`: 插件配置文件的schema，用于自动生成配置文件。

# 插件系统修改
1. 现在所有的匹配模式不再是关键字了，而是枚举类。**（可能有遗漏）**
2. 修复了一下显示插件信息不显示的问题。同时精简了一下显示内容
3. 修复了插件系统混用了`plugin_name`和`display_name`的问题。现在所有的插件信息都使用`display_name`来显示，而内部标识仍然使用`plugin_name`。**（可能有遗漏）**
3. 部分API的参数类型和返回值进行了调整
  - `chat_api.py`中获取流的参数中可以使用一个特殊的枚举类型来获得所有平台的 ChatStream 了。
  - `config_api.py`中的`get_global_config`和`get_plugin_config`方法现在支持嵌套访问的配置键名。
  - `database_api.py`中的`db_query`方法调整了参数顺序以增强参数限制的同时，保证了typing正确；`db_get`方法增加了`single_result`参数，与`db_query`保持一致。

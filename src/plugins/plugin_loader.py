import importlib
import pkgutil
import os
from typing import Dict, Tuple
from src.common.logger_manager import get_logger

logger = get_logger("plugin_loader")


class PluginLoader:
    """统一的插件加载器，负责加载插件的所有组件（actions、commands等）"""

    def __init__(self):
        self.loaded_actions = 0
        self.loaded_commands = 0
        self.plugin_stats: Dict[str, Dict[str, int]] = {}  # 统计每个插件加载的组件数量
        self.plugin_sources: Dict[str, str] = {}  # 记录每个插件来自哪个路径

    def load_all_plugins(self) -> Tuple[int, int]:
        """加载所有插件的所有组件

        Returns:
            Tuple[int, int]: (加载的动作数量, 加载的命令数量)
        """
        # 定义插件搜索路径（优先级从高到低）
        plugin_paths = [
            ("plugins", "plugins"),  # 项目根目录的plugins文件夹
            ("src.plugins", os.path.join("src", "plugins")),  # src下的plugins文件夹
        ]

        total_plugins_found = 0

        for plugin_import_path, plugin_dir_path in plugin_paths:
            try:
                plugins_loaded = self._load_plugins_from_path(plugin_import_path, plugin_dir_path)
                total_plugins_found += plugins_loaded

            except Exception as e:
                logger.error(f"从路径 {plugin_dir_path} 加载插件失败: {e}")
                import traceback

                logger.error(traceback.format_exc())

        if total_plugins_found == 0:
            logger.info("未找到任何插件目录或插件")

        # 输出加载统计
        self._log_loading_stats()

        return self.loaded_actions, self.loaded_commands

    def _load_plugins_from_path(self, plugin_import_path: str, plugin_dir_path: str) -> int:
        """从指定路径加载插件

        Args:
            plugin_import_path: 插件的导入路径 (如 "plugins" 或 "src.plugins")
            plugin_dir_path: 插件目录的文件系统路径

        Returns:
            int: 找到的插件包数量
        """
        # 检查插件目录是否存在
        if not os.path.exists(plugin_dir_path):
            logger.debug(f"插件目录 {plugin_dir_path} 不存在，跳过")
            return 0

        logger.info(f"正在从 {plugin_dir_path} 加载插件...")

        # 导入插件包
        try:
            plugins_package = importlib.import_module(plugin_import_path)
            logger.info(f"成功导入插件包: {plugin_import_path}")
        except ImportError as e:
            logger.warning(f"导入插件包 {plugin_import_path} 失败: {e}")
            return 0

        # 遍历插件包中的所有子包
        plugins_found = 0
        for _, plugin_name, is_pkg in pkgutil.iter_modules(plugins_package.__path__, plugins_package.__name__ + "."):
            if not is_pkg:
                continue

            logger.debug(f"检测到插件: {plugin_name}")
            # 记录插件来源
            self.plugin_sources[plugin_name] = plugin_dir_path
            self._load_single_plugin(plugin_name)
            plugins_found += 1

        if plugins_found > 0:
            logger.info(f"从 {plugin_dir_path} 找到 {plugins_found} 个插件包")
        else:
            logger.debug(f"从 {plugin_dir_path} 未找到任何插件包")

        return plugins_found

    def _load_single_plugin(self, plugin_name: str) -> None:
        """加载单个插件的所有组件

        Args:
            plugin_name: 插件名称
        """
        plugin_stats = {"actions": 0, "commands": 0}

        # 加载动作组件
        actions_count = self._load_plugin_actions(plugin_name)
        plugin_stats["actions"] = actions_count
        self.loaded_actions += actions_count

        # 加载命令组件
        commands_count = self._load_plugin_commands(plugin_name)
        plugin_stats["commands"] = commands_count
        self.loaded_commands += commands_count

        # 记录插件统计信息
        if actions_count > 0 or commands_count > 0:
            self.plugin_stats[plugin_name] = plugin_stats
            logger.info(f"插件 {plugin_name} 加载完成: {actions_count} 个动作, {commands_count} 个命令")

    def _load_plugin_actions(self, plugin_name: str) -> int:
        """加载插件的动作组件

        Args:
            plugin_name: 插件名称

        Returns:
            int: 加载的动作数量
        """
        loaded_count = 0

        # 优先检查插件是否有actions子包
        plugin_actions_path = f"{plugin_name}.actions"
        plugin_actions_dir = plugin_name.replace(".", os.path.sep) + os.path.sep + "actions"

        actions_loaded_from_subdir = False

        # 首先尝试从actions子目录加载
        if os.path.exists(plugin_actions_dir):
            loaded_count += self._load_from_actions_subdir(plugin_name, plugin_actions_path, plugin_actions_dir)
            if loaded_count > 0:
                actions_loaded_from_subdir = True

        # 如果actions子目录不存在或加载失败，尝试从插件根目录加载
        if not actions_loaded_from_subdir:
            loaded_count += self._load_actions_from_root_dir(plugin_name)

        return loaded_count

    def _load_plugin_commands(self, plugin_name: str) -> int:
        """加载插件的命令组件

        Args:
            plugin_name: 插件名称

        Returns:
            int: 加载的命令数量
        """
        loaded_count = 0

        # 优先检查插件是否有commands子包
        plugin_commands_path = f"{plugin_name}.commands"
        plugin_commands_dir = plugin_name.replace(".", os.path.sep) + os.path.sep + "commands"

        commands_loaded_from_subdir = False

        # 首先尝试从commands子目录加载
        if os.path.exists(plugin_commands_dir):
            loaded_count += self._load_from_commands_subdir(plugin_name, plugin_commands_path, plugin_commands_dir)
            if loaded_count > 0:
                commands_loaded_from_subdir = True

        # 如果commands子目录不存在或加载失败，尝试从插件根目录加载
        if not commands_loaded_from_subdir:
            loaded_count += self._load_commands_from_root_dir(plugin_name)

        return loaded_count

    def _load_from_actions_subdir(self, plugin_name: str, plugin_actions_path: str, plugin_actions_dir: str) -> int:
        """从actions子目录加载动作"""
        loaded_count = 0

        try:
            # 尝试导入插件的actions包
            actions_module = importlib.import_module(plugin_actions_path)
            logger.debug(f"成功加载插件动作模块: {plugin_actions_path}")

            # 遍历actions目录中的所有Python文件
            actions_dir = os.path.dirname(actions_module.__file__)
            for file in os.listdir(actions_dir):
                if file.endswith(".py") and file != "__init__.py":
                    action_module_name = f"{plugin_actions_path}.{file[:-3]}"
                    try:
                        importlib.import_module(action_module_name)
                        logger.info(f"成功加载动作: {action_module_name}")
                        loaded_count += 1
                    except Exception as e:
                        logger.error(f"加载动作失败: {action_module_name}, 错误: {e}")

        except ImportError as e:
            logger.debug(f"插件 {plugin_name} 的actions子包导入失败: {e}")

        return loaded_count

    def _load_from_commands_subdir(self, plugin_name: str, plugin_commands_path: str, plugin_commands_dir: str) -> int:
        """从commands子目录加载命令"""
        loaded_count = 0

        try:
            # 尝试导入插件的commands包
            commands_module = importlib.import_module(plugin_commands_path)
            logger.debug(f"成功加载插件命令模块: {plugin_commands_path}")

            # 遍历commands目录中的所有Python文件
            commands_dir = os.path.dirname(commands_module.__file__)
            for file in os.listdir(commands_dir):
                if file.endswith(".py") and file != "__init__.py":
                    command_module_name = f"{plugin_commands_path}.{file[:-3]}"
                    try:
                        importlib.import_module(command_module_name)
                        logger.info(f"成功加载命令: {command_module_name}")
                        loaded_count += 1
                    except Exception as e:
                        logger.error(f"加载命令失败: {command_module_name}, 错误: {e}")

        except ImportError as e:
            logger.debug(f"插件 {plugin_name} 的commands子包导入失败: {e}")

        return loaded_count

    def _load_actions_from_root_dir(self, plugin_name: str) -> int:
        """从插件根目录加载动作文件"""
        loaded_count = 0

        try:
            # 导入插件包本身
            plugin_module = importlib.import_module(plugin_name)
            logger.debug(f"尝试从插件根目录加载动作: {plugin_name}")

            # 遍历插件根目录中的所有Python文件
            plugin_dir = os.path.dirname(plugin_module.__file__)
            for file in os.listdir(plugin_dir):
                if file.endswith(".py") and file != "__init__.py":
                    # 跳过非动作文件（根据命名约定）
                    if not (file.endswith("_action.py") or file.endswith("_actions.py") or "action" in file):
                        continue

                    action_module_name = f"{plugin_name}.{file[:-3]}"
                    try:
                        importlib.import_module(action_module_name)
                        logger.info(f"成功加载动作: {action_module_name}")
                        loaded_count += 1
                    except Exception as e:
                        logger.error(f"加载动作失败: {action_module_name}, 错误: {e}")

        except ImportError as e:
            logger.debug(f"插件 {plugin_name} 导入失败: {e}")

        return loaded_count

    def _load_commands_from_root_dir(self, plugin_name: str) -> int:
        """从插件根目录加载命令文件"""
        loaded_count = 0

        try:
            # 导入插件包本身
            plugin_module = importlib.import_module(plugin_name)
            logger.debug(f"尝试从插件根目录加载命令: {plugin_name}")

            # 遍历插件根目录中的所有Python文件
            plugin_dir = os.path.dirname(plugin_module.__file__)
            for file in os.listdir(plugin_dir):
                if file.endswith(".py") and file != "__init__.py":
                    # 跳过非命令文件（根据命名约定）
                    if not (file.endswith("_command.py") or file.endswith("_commands.py") or "command" in file):
                        continue

                    command_module_name = f"{plugin_name}.{file[:-3]}"
                    try:
                        importlib.import_module(command_module_name)
                        logger.info(f"成功加载命令: {command_module_name}")
                        loaded_count += 1
                    except Exception as e:
                        logger.error(f"加载命令失败: {command_module_name}, 错误: {e}")

        except ImportError as e:
            logger.debug(f"插件 {plugin_name} 导入失败: {e}")

        return loaded_count

    def _log_loading_stats(self) -> None:
        """输出加载统计信息"""
        logger.success(f"插件加载完成: 总计 {self.loaded_actions} 个动作, {self.loaded_commands} 个命令")

        if self.plugin_stats:
            logger.info("插件加载详情:")
            for plugin_name, stats in self.plugin_stats.items():
                plugin_display_name = plugin_name.split(".")[-1]  # 只显示插件名称，不显示完整路径
                source_path = self.plugin_sources.get(plugin_name, "未知路径")
                logger.info(
                    f"  {plugin_display_name} (来源: {source_path}): {stats['actions']} 动作, {stats['commands']} 命令"
                )


# 创建全局插件加载器实例
plugin_loader = PluginLoader()

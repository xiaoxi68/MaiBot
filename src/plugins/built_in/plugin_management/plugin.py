from typing import List, Tuple, Type
from src.plugin_system import (
    BasePlugin,
    BaseCommand,
    CommandInfo,
    ConfigField,
    register_plugin,
    plugin_manage_api,
    component_manage_api,
    ComponentInfo,
    ComponentType,
)
from src.plugin_system.base.base_action import BaseAction
from src.plugin_system.base.base_events_handler import BaseEventHandler
from src.plugin_system.base.component_types import ActionInfo, EventHandlerInfo


class ManagementCommand(BaseCommand):
    command_name: str = "management"
    description: str = "管理命令"
    command_pattern: str = r"(?P<manage_command>^/p_m(\s[a-zA-Z0-9_]+)*\s*$)"
    intercept_message: bool = True

    async def execute(self) -> Tuple[bool, str]:
        command_list = self.matched_groups["manage_command"].strip().split(" ")
        if len(command_list) == 1:
            await self.show_help("all")
            return True, "帮助已发送"
        if len(command_list) == 2:
            match command_list[1]:
                case "plugin":
                    await self.show_help("plugin")
                case "component":
                    await self.show_help("component")
                case "help":
                    await self.show_help("all")
                case _:
                    return False, "命令不合法"
        if len(command_list) == 3:
            if command_list[1] == "plugin":
                match command_list[2]:
                    case "help":
                        await self.show_help("plugin")
                    case "list":
                        await self._list_registered_plugins()
                    case "list_enabled":
                        await self._list_loaded_plugins()
                    case "rescan":
                        await self._rescan_plugin_dirs()
                    case _:
                        return False, "命令不合法"
            elif command_list[1] == "component":
                match command_list[2]:
                    case "help":
                        await self.show_help("component")
                        return True, "帮助已发送"
                    case "list":
                        pass
                    case _:
                        return False, "命令不合法"
            else:
                return False, "命令不合法"
        if len(command_list) == 4:
            if command_list[1] == "plugin":
                match command_list[2]:
                    case "load":
                        await self._load_plugin(command_list[3])
                    case "unload":
                        await self._unload_plugin(command_list[3])
                    case "reload":
                        await self._reload_plugin(command_list[3])
                    case "add_dir":
                        await self._add_dir(command_list[3])
                    case _:
                        return False, "命令不合法"
            elif command_list[1] == "component":
                pass
            else:
                return False, "命令不合法"
        if len(command_list) == 5:
            pass
        if len(command_list) == 6:
            pass

        return True, "命令执行完成"

    async def show_help(self, target: str):
        help_msg = ""
        match target:
            case "all":
                help_msg = (
                    "管理命令帮助\n"
                    "/p_m help 管理命令提示\n"
                    "/p_m plugin 插件管理命令\n"
                    "/p_m component 组件管理命令\n"
                    "使用 /p_m plugin help 或 /p_m component help 获取具体帮助"
                )
            case "plugin":
                help_msg = (
                    "插件管理命令帮助\n"
                    "/p_m plugin help 插件管理命令提示\n"
                    "/p_m plugin list 列出所有注册的插件\n"
                    "/p_m plugin list_enabled 列出所有加载（启用）的插件\n"
                    "/p_m plugin rescan 重新扫描所有目录\n"
                    "/p_m plugin load <plugin_name> 加载指定插件\n"
                    "/p_m plugin unload <plugin_name> 卸载指定插件\n"
                    "/p_m plugin reload <plugin_name> 重新加载指定插件\n"
                    "/p_m plugin add_dir <directory_path> 添加插件目录\n"
                )
            case "component":
                help_msg = (
                    "组件管理命令帮助\n"
                    "/p_m component help 组件管理命令提示\n"
                    "/p_m component list 列出所有注册的组件\n"
                    "/p_m component list enabled <可选: type> 列出所有启用的组件\n"
                    "/p_m component list disabled <可选: type> 列出所有禁用的组件\n"
                    "  - <type> 可选项: local，代表当前聊天中的；global，代表全局的\n"
                    "  - <type> 不填时为 global\n"
                    "/p_m component list type <component_type> 列出指定类型的组件\n"
                    "/p_m component global enable <component_name> <可选: component_type> 全局启用组件\n"
                    "/p_m component global disable <component_name> <可选: component_type> 全局禁用组件\n"
                    "/p_m component local enable <component_name> <可选: component_type> 本聊天启用组件\n"
                    "/p_m component local disable <component_name> <可选: component_type> 本聊天禁用组件\n"
                    "  - <component_type> 可选项: action, command, event_handler\n"
                )
            case _:
                return
        await self.send_text(help_msg)

    async def _list_loaded_plugins(self):
        plugins = plugin_manage_api.list_loaded_plugins()
        await self.send_text(f"已加载的插件: {', '.join(plugins)}")

    async def _list_registered_plugins(self):
        plugins = plugin_manage_api.list_registered_plugins()
        await self.send_text(f"已注册的插件: {', '.join(plugins)}")

    async def _rescan_plugin_dirs(self):
        plugin_manage_api.rescan_plugin_directory()
        await self.send_text("插件目录重新扫描执行中")

    async def _load_plugin(self, plugin_name: str):
        await self.send_text(f"正在加载插件: {plugin_name}")
        success, count = plugin_manage_api.load_plugin(plugin_name)
        if success:
            await self.send_text(f"插件加载成功: {plugin_name}")
        else:
            if count == 0:
                await self.send_text(f"插件{plugin_name}为禁用状态")
            await self.send_text(f"插件加载失败: {plugin_name}")

    async def _unload_plugin(self, plugin_name: str):
        await self.send_text(f"正在卸载插件: {plugin_name}")
        success = plugin_manage_api.remove_plugin(plugin_name)
        if success:
            await self.send_text(f"插件卸载成功: {plugin_name}")
        else:
            await self.send_text(f"插件卸载失败: {plugin_name}")

    async def _reload_plugin(self, plugin_name: str):
        await self.send_text(f"正在重新加载插件: {plugin_name}")
        success = plugin_manage_api.reload_plugin(plugin_name)
        if success:
            await self.send_text(f"插件重新加载成功: {plugin_name}")
        else:
            await self.send_text(f"插件重新加载失败: {plugin_name}")

    async def _add_dir(self, dir_path: str):
        await self.send_text(f"正在添加插件目录: {dir_path}")
        success = plugin_manage_api.add_plugin_directory(dir_path)
        if success:
            await self.send_text(f"插件目录添加成功: {dir_path}")
        else:
            await self.send_text(f"插件目录添加失败: {dir_path}")

    def _fetch_all_registered_components(self) -> List[ComponentInfo]:
        all_plugin_info = component_manage_api.get_all_plugin_info()
        if not all_plugin_info:
            return []

        components_info: List[ComponentInfo] = []
        for plugin_info in all_plugin_info.values():
            components_info.extend(plugin_info.components)
        return components_info

    def _fetch_locally_disabled_components(self) -> List[str]:
        locally_disabled_components_actions = component_manage_api.get_locally_disabled_components(
            self.message.chat_stream.stream_id, ComponentType.ACTION
        )
        locally_disabled_components_commands = component_manage_api.get_locally_disabled_components(
            self.message.chat_stream.stream_id, ComponentType.COMMAND
        )
        locally_disabled_components_event_handlers = component_manage_api.get_locally_disabled_components(
            self.message.chat_stream.stream_id, ComponentType.EVENT_HANDLER
        )
        return (
            locally_disabled_components_actions
            + locally_disabled_components_commands
            + locally_disabled_components_event_handlers
        )

    async def _list_all_registered_components(self):
        components_info = self._fetch_all_registered_components()
        if not components_info:
            await self.send_text("没有注册的组件")
            return

        all_components_str = ", ".join(
            f"{component.name} ({component.component_type})" for component in components_info
        )
        await self.send_text(f"已注册的组件: {all_components_str}")

    async def _list_enabled_components(self, target_type: str = "global"):
        components_info = self._fetch_all_registered_components()
        if not components_info:
            await self.send_text("没有注册的组件")
            return

        if target_type == "global":
            enabled_components = [component for component in components_info if component.enabled]
            if not enabled_components:
                await self.send_text("没有启用的全局组件")
                return
            enabled_components_str = ", ".join(
                f"{component.name} ({component.component_type})" for component in enabled_components
            )
            await self.send_text(f"启用的全局组件: {enabled_components_str}")
        elif target_type == "local":
            locally_disabled_components = self._fetch_locally_disabled_components()
            


@register_plugin
class PluginManagementPlugin(BasePlugin):
    plugin_name: str = "plugin_management_plugin"
    enable_plugin: bool = True
    dependencies: list[str] = []
    python_dependencies: list[str] = []
    config_file_name: str = "config.toml"
    config_schema: dict = {"plugin": {"enable": ConfigField(bool, default=True, description="是否启用插件")}}

    def get_plugin_components(self) -> List[Tuple[CommandInfo, Type[BaseCommand]]]:
        components = []
        if self.get_config("plugin.enable", True):
            components.append((ManagementCommand.get_command_info(), ManagementCommand))
        return components

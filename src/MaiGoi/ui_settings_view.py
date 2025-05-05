import flet as ft
import tomlkit

from .state import AppState
from .utils import show_snackbar  # Assuming show_snackbar is in utils
from .toml_form_generator import create_toml_form, load_bot_config, get_bot_config_path
from .config_manager import load_config, save_config
from .ui_env_editor import create_env_editor_page_content


def save_bot_config(page: ft.Page, app_state: AppState, new_config_data: dict):
    """将修改后的 Bot 配置保存回文件。"""
    config_path = get_bot_config_path(app_state)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            # Use tomlkit.dumps to preserve formatting/comments as much as possible
            # It might need refinement based on how UI controls update the dict
            tomlkit.dump(new_config_data, f)
        show_snackbar(page, "Bot 配置已保存！")
        # Optionally reload config into app_state if needed immediately elsewhere
        # app_state.bot_config = new_config_data # Or reload using a dedicated function
    except Exception as e:
        print(f"Error saving bot config: {e}")
        show_snackbar(page, f"保存 Bot 配置失败: {e}", error=True)


def save_bot_config_changes(page: ft.Page, config_to_save: dict):
    """Handles saving changes for bot_config.toml"""
    print("[Settings] Saving Bot Config (TOML) changes...")
    # Assuming save_config needs path, let's build it or adapt save_config
    # For now, let's assume save_config can handle type='bot'
    # config_path = get_bot_config_path(app_state) # Need app_state if using this
    success = save_config(config_to_save, config_type="bot")
    if success:
        message = "Bot 配置已保存！"
    else:
        message = "保存 Bot 配置失败。"
    show_snackbar(page, message, error=(not success))


def save_lpmm_config_changes(page: ft.Page, config_to_save: dict):
    """Handles saving changes for lpmm_config.toml"""
    print("[Settings] Saving LPMM Config (TOML) changes...")
    success = save_config(config_to_save, config_type="lpmm")  # Use type 'lpmm'
    if success:
        message = "LPMM 配置已保存！"
    else:
        message = "保存 LPMM 配置失败。"
    show_snackbar(page, message, error=(not success))


def save_gui_config_changes(page: ft.Page, app_state: AppState):
    """Handles saving changes for gui_config.toml (currently just theme)"""
    print("[Settings] Saving GUI Config changes...")
    # gui_config is directly in app_state, no need to pass config_to_save
    success = save_config(app_state.gui_config, config_type="gui")
    if success:
        message = "GUI 配置已保存！"
    else:
        message = "保存 GUI 配置失败。"
    show_snackbar(page, message, error=(not success))


def create_settings_view(page: ft.Page, app_state: AppState) -> ft.View:
    """Creates the settings view with sections for different config files."""

    # --- State for switching between editors ---
    content_area = ft.Column([], expand=True, scroll=ft.ScrollMode.ADAPTIVE)
    current_config_data = {}  # Store loaded data for saving

    # --- Function to load Bot config editor (Original TOML editor) ---
    def show_bot_config_editor(e=None):
        nonlocal current_config_data
        print("[Settings] Loading Bot Config Editor")
        try:
            current_bot_config = load_bot_config(app_state)
            if not current_bot_config:
                raise ValueError("Bot config could not be loaded.")
            current_config_data = current_bot_config
            content_area.controls.clear()
            # Pass the correct template filename string
            form_generator = create_toml_form(
                page, current_bot_config, content_area, template_filename="bot_config_template.toml"
            )
            save_button = ft.ElevatedButton(
                "保存 Bot 配置更改",
                icon=ft.icons.SAVE,
                on_click=lambda _: save_bot_config_changes(
                    page, form_generator.config_data if hasattr(form_generator, "config_data") else current_config_data
                ),
            )
            content_area.controls.append(ft.Divider())
            content_area.controls.append(save_button)
        except Exception as ex:
            content_area.controls.clear()
            content_area.controls.append(ft.Text(f"加载 Bot 配置时出错: {ex}", color=ft.colors.ERROR))
        if page:
            page.update()

    # --- Function to load LPMM config editor ---
    def show_lpmm_editor(e=None):
        nonlocal current_config_data
        print("[Settings] Loading LPMM Config Editor")
        try:
            lpmm_config = load_config(config_type="lpmm")
            if not lpmm_config:
                raise ValueError("LPMM config could not be loaded.")
            current_config_data = lpmm_config
            content_area.controls.clear()
            # Pass the correct template filename string
            form_generator = create_toml_form(
                page, lpmm_config, content_area, template_filename="lpmm_config_template.toml"
            )
            save_button = ft.ElevatedButton(
                "保存 LPMM 配置更改",
                icon=ft.icons.SAVE,
                on_click=lambda _: save_lpmm_config_changes(
                    page, form_generator.config_data if hasattr(form_generator, "config_data") else current_config_data
                ),
            )
            content_area.controls.append(ft.Divider())
            content_area.controls.append(save_button)
        except Exception as ex:
            content_area.controls.clear()
            content_area.controls.append(ft.Text(f"加载 LPMM 配置时出错: {ex}", color=ft.colors.ERROR))
        if page:
            page.update()

    # --- Function to load GUI settings editor ---
    def show_gui_settings(e=None):
        # GUI config is simpler, might not need full form generator
        # We'll load it directly from app_state and save app_state.gui_config
        print("[Settings] Loading GUI Settings Editor")
        content_area.controls.clear()

        def change_theme(ev):
            selected_theme = ev.control.value.upper()
            page.theme_mode = ft.ThemeMode[selected_theme]
            app_state.gui_config["theme"] = selected_theme
            print(f"Theme changed to: {page.theme_mode}, updating app_state.gui_config")
            page.update()  # Update theme immediately

        # Get current theme from app_state or page
        current_theme_val = app_state.gui_config.get("theme", str(page.theme_mode).split(".")[-1]).capitalize()
        if current_theme_val not in ["System", "Light", "Dark"]:
            current_theme_val = "System"  # Default fallback

        theme_dropdown = ft.Dropdown(
            label="界面主题",
            value=current_theme_val,
            options=[
                ft.dropdown.Option("System"),
                ft.dropdown.Option("Light"),
                ft.dropdown.Option("Dark"),
            ],
            on_change=change_theme,
            # expand=True, # Maybe not expand in this layout
        )

        save_button = ft.ElevatedButton(
            "保存 GUI 设置", icon=ft.icons.SAVE, on_click=lambda _: save_gui_config_changes(page, app_state)
        )

        content_area.controls.extend(
            [
                ft.Text("界面设置:", weight=ft.FontWeight.BOLD),
                ft.Row([theme_dropdown]),
                # Add more GUI controls here if needed in the future
                ft.Divider(),
                save_button,
            ]
        )
        if page:
            page.update()

    # --- Function to load .env editor ---
    def show_env_editor(e=None):
        # No config data to manage here, it handles its own save
        print("[Settings] Loading .env Editor")
        content_area.controls.clear()
        env_editor_content = create_env_editor_page_content(page, app_state)
        content_area.controls.append(env_editor_content)
        if page:
            page.update()

    # --- Initial View Setup ---
    # Load the Bot config editor by default
    show_bot_config_editor()

    return ft.View(
        "/settings",
        [
            ft.AppBar(title=ft.Text("设置"), bgcolor=ft.colors.SURFACE_VARIANT),
            ft.Row(
                [
                    ft.ElevatedButton("Bot 配置", icon=ft.icons.SETTINGS_SUGGEST, on_click=show_bot_config_editor),
                    ft.ElevatedButton("LPMM 配置", icon=ft.icons.MEMORY, on_click=show_lpmm_editor),
                    ft.ElevatedButton("GUI 设置", icon=ft.icons.BRUSH, on_click=show_gui_settings),
                    ft.ElevatedButton(".env 配置", icon=ft.icons.EDIT, on_click=show_env_editor),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                wrap=True,  # Allow buttons to wrap on smaller widths
            ),
            ft.Divider(),
            content_area,  # This holds the currently selected editor
        ],
        scroll=ft.ScrollMode.ADAPTIVE,
    )


# Note: Assumes save_config function exists and can handle saving
# the bot_config dictionary back to its TOML file. You might need to
# adjust the save_bot_config_changes function based on how saving is implemented.
# Also assumes load_bot_config loads the data correctly for the TOML editor.


def create_settings_view_old(page: ft.Page, app_state: AppState) -> ft.View:
    """创建设置页面视图。"""

    # --- GUI Settings ---
    def change_theme(e):
        selected_theme = e.control.value.upper()
        page.theme_mode = ft.ThemeMode[selected_theme]
        # Persist theme choice? Maybe in gui_config?
        app_state.gui_config["theme"] = selected_theme  # Example persistence
        # Need a way to save gui_config too (similar to bot_config?)
        print(f"Theme changed to: {page.theme_mode}")
        page.update()

    theme_dropdown = ft.Dropdown(
        label="界面主题",
        value=str(page.theme_mode).split(".")[-1].capitalize()
        if page.theme_mode
        else "System",  # Handle None theme_mode
        options=[
            ft.dropdown.Option("System"),
            ft.dropdown.Option("Light"),
            ft.dropdown.Option("Dark"),
        ],
        on_change=change_theme,
        expand=True,
    )

    gui_settings_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.ListTile(title=ft.Text("GUI 设置")),
                    ft.Row([theme_dropdown], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    # Add more GUI settings here
                ]
            ),
            padding=10,
        )
    )

    # --- Bot Settings (Placeholder) ---
    # TODO: Load bot_config.toml and dynamically generate controls
    config_path = get_bot_config_path(app_state)
    bot_config_content_area = ft.Column(expand=True, scroll=ft.ScrollMode.ADAPTIVE)
    bot_settings_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.ListTile(title=ft.Text("Bot 配置 (bot_config.toml)")),
                    ft.Text(f"配置文件路径: {config_path}", italic=True, size=10),
                    ft.Divider(),
                    # Placeholder - Controls will be added dynamically
                    bot_config_content_area,
                    ft.Divider(),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "重新加载", icon=ft.icons.REFRESH, on_click=lambda _: print("Reload TBD")
                            ),  # Placeholder action
                            ft.ElevatedButton(
                                "保存 Bot 配置", icon=ft.icons.SAVE, on_click=lambda _: print("Save TBD")
                            ),  # Placeholder action
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ]
            ),
            padding=10,
        )
    )

    # --- Load and Display Bot Config ---
    # This needs error handling and dynamic UI generation
    try:
        # 使用新的加载方法
        loaded_bot_config = load_bot_config(app_state)

        if loaded_bot_config:
            # 使用新的表单生成器创建动态表单
            create_toml_form(page, loaded_bot_config, bot_config_content_area, app_state)

            # Update the save button's action
            save_button = bot_settings_card.content.content.controls[-1].controls[1]  # Find the save button
            save_button.on_click = lambda _: save_bot_config(
                page, app_state, loaded_bot_config
            )  # Pass the loaded config dict

            # Add reload logic here
            reload_button = bot_settings_card.content.content.controls[-1].controls[0]  # Find the reload button

            def reload_action(_):
                bot_config_content_area.controls.clear()
                try:
                    reloaded_config = load_bot_config(app_state)
                    if reloaded_config:
                        # 重新创建表单
                        create_toml_form(page, reloaded_config, bot_config_content_area, app_state)
                        # Update save button reference
                        save_button.on_click = lambda _: save_bot_config(page, app_state, reloaded_config)
                        show_snackbar(page, "Bot 配置已重新加载。")
                        # 确保UI完全更新
                        bot_config_content_area.update()
                        bot_settings_card.update()
                    else:
                        bot_config_content_area.controls.append(
                            ft.Text("重新加载失败: 无法加载配置文件", color=ft.colors.ERROR)
                        )
                        bot_config_content_area.update()
                except Exception as reload_e:
                    bot_config_content_area.controls.append(ft.Text(f"重新加载失败: {reload_e}", color=ft.colors.ERROR))
                    bot_config_content_area.update()
                page.update()

            reload_button.on_click = reload_action
        else:
            bot_config_content_area.controls.append(
                ft.Text(f"错误: 无法加载配置文件 {config_path}", color=ft.colors.ERROR)
            )
    except Exception as e:
        bot_config_content_area.controls.append(ft.Text(f"加载配置文件出错: {e}", color=ft.colors.ERROR))

    return ft.View(
        "/settings",
        [
            ft.AppBar(title=ft.Text("设置"), bgcolor=ft.colors.SURFACE_VARIANT),
            gui_settings_card,
            bot_settings_card,  # Add the bot settings card
            # Add more settings sections/cards as needed
        ],
        scroll=ft.ScrollMode.ADAPTIVE,  # Allow scrolling for the whole view
        padding=10,
    )

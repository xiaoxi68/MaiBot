"""
拍照插件

功能特性：
- Action: 生成一张自拍照，prompt由人设和模板生成
- Command: 展示最近生成的照片

#此插件并不完善
#此插件并不完善

#此插件并不完善

#此插件并不完善

#此插件并不完善

#此插件并不完善

#此插件并不完善



包含组件：
- 拍照Action - 生成自拍照
- 展示照片Command - 展示最近生成的照片
"""

from typing import List, Tuple, Type, Optional
import random
import datetime
import json
import os
import asyncio
import urllib.request
import urllib.error
import base64
import traceback

from src.plugin_system.base.base_plugin import BasePlugin, register_plugin
from src.plugin_system.base.base_action import BaseAction
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.base.component_types import ComponentInfo, ActionActivationType, ChatMode
from src.plugin_system.base.config_types import ConfigField
from src.common.logger import get_logger

logger = get_logger("take_picture_plugin")

# 定义数据目录常量
DATA_DIR = os.path.join("data", "take_picture_data")
# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)
# 创建全局锁
file_lock = asyncio.Lock()


class TakePictureAction(BaseAction):
    """生成一张自拍照"""

    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD
    mode_enable = ChatMode.ALL
    parallel_action = False

    action_name = "take_picture"
    action_description = "生成一张用手机拍摄，比如自拍或者近照"
    activation_keywords = ["拍张照", "自拍", "发张照片", "看看你", "你的照片"]
    keyword_case_sensitive = False

    action_parameters = {}

    action_require = ["当用户想看你的照片时使用", "当用户让你发自拍时使用当想随手拍眼前的场景时使用"]

    associated_types = ["text", "image"]

    # 内置的Prompt模板，如果配置文件中没有定义，将使用这些模板
    DEFAULT_PROMPT_TEMPLATES = [
        "极其频繁无奇的iPhone自拍照，没有明确的主体或构图感，就是随手一拍的快照照片略带运动模糊，阳光或室内打光不均匀导致的轻微曝光过度，整体呈现出一种刻意的平庸感，就像是从口袋里拿手机时不小心拍到的一张自拍。主角是{name}，{personality}"
    ]

    # 简单的请求缓存，避免短时间内重复请求
    _request_cache = {}

    async def execute(self) -> Tuple[bool, Optional[str]]:
        logger.info(f"{self.log_prefix} 执行拍照动作")

        try:
            # 配置验证
            http_base_url = self.api.get_config("api.base_url")
            http_api_key = self.api.get_config("api.volcano_generate_api_key")

            if not (http_base_url and http_api_key):
                error_msg = "抱歉，照片生成功能所需的API配置（如API地址或密钥）不完整，无法提供服务。"
                await self.send_text(error_msg)
                logger.error(f"{self.log_prefix} HTTP调用配置缺失: base_url 或 volcano_generate_api_key.")
                return False, "API配置不完整"

            # API密钥验证
            if http_api_key == "YOUR_DOUBAO_API_KEY_HERE":
                error_msg = "照片生成功能尚未配置，请设置正确的API密钥。"
                await self.send_text(error_msg)
                logger.error(f"{self.log_prefix} API密钥未配置")
                return False, "API密钥未配置"

            # 获取全局配置信息
            bot_nickname = self.api.get_global_config("bot.nickname", "麦麦")
            bot_personality = self.api.get_global_config("personality.personality_core", "")

            personality_sides = self.api.get_global_config("personality.personality_sides", [])
            if personality_sides:
                bot_personality += random.choice(personality_sides)

            # 准备模板变量
            template_vars = {"name": bot_nickname, "personality": bot_personality}

            logger.info(f"{self.log_prefix} 使用的全局配置: name={bot_nickname}, personality={bot_personality}")

            # 尝试从配置文件获取模板，如果没有则使用默认模板
            templates = self.api.get_config("picture.prompt_templates", self.DEFAULT_PROMPT_TEMPLATES)
            if not templates:
                logger.warning(f"{self.log_prefix} 未找到有效的提示词模板，使用默认模板")
                templates = self.DEFAULT_PROMPT_TEMPLATES

            prompt_template = random.choice(templates)

            # 填充模板
            final_prompt = prompt_template.format(**template_vars)

            logger.info(f"{self.log_prefix} 生成的最终Prompt: {final_prompt}")

            # 从配置获取参数
            model = self.api.get_config("picture.default_model", "doubao-seedream-3-0-t2i-250415")
            size = self.api.get_config("picture.default_size", "1024x1024")
            watermark = self.api.get_config("picture.default_watermark", True)
            guidance_scale = self.api.get_config("picture.default_guidance_scale", 2.5)
            seed = self.api.get_config("picture.default_seed", 42)

            # 检查缓存
            enable_cache = self.api.get_config("storage.enable_cache", True)
            if enable_cache:
                cache_key = self._get_cache_key(final_prompt, model, size)
                if cache_key in self._request_cache:
                    cached_result = self._request_cache[cache_key]
                    logger.info(f"{self.log_prefix} 使用缓存的图片结果")
                    await self.send_text("我之前拍过类似的照片，用之前的结果~")

                    # 直接发送缓存的结果
                    send_success = await self._send_image(cached_result)
                    if send_success:
                        await self.send_text("这是我的照片，好看吗？")
                        return True, "照片已发送(缓存)"
                    else:
                        # 缓存失败，清除这个缓存项并继续正常流程
                        del self._request_cache[cache_key]

            await self.send_text("正在为你拍照，请稍候...")

            try:
                seed = random.randint(1, 1000000)
                success, result = await asyncio.to_thread(
                    self._make_http_image_request,
                    prompt=final_prompt,
                    model=model,
                    size=size,
                    seed=seed,
                    guidance_scale=guidance_scale,
                    watermark=watermark,
                )
            except Exception as e:
                logger.error(f"{self.log_prefix} (HTTP) 异步请求执行失败: {e!r}", exc_info=True)
                traceback.print_exc()
                success = False
                result = f"照片生成服务遇到意外问题: {str(e)[:100]}"

            if success:
                image_url = result
                logger.info(f"{self.log_prefix} 图片URL获取成功: {image_url[:70]}... 下载并编码.")

                try:
                    encode_success, encode_result = await asyncio.to_thread(self._download_and_encode_base64, image_url)
                except Exception as e:
                    logger.error(f"{self.log_prefix} (B64) 异步下载/编码失败: {e!r}", exc_info=True)
                    traceback.print_exc()
                    encode_success = False
                    encode_result = f"图片下载或编码时发生内部错误: {str(e)[:100]}"

                if encode_success:
                    base64_image_string = encode_result
                    # 更新缓存
                    if enable_cache:
                        self._update_cache(final_prompt, model, size, base64_image_string)

                    # 发送图片
                    send_success = await self._send_image(base64_image_string)
                    if send_success:
                        # 存储到文件
                        await self._store_picture_info(final_prompt, image_url)
                        logger.info(f"{self.log_prefix} 成功生成并存储照片: {image_url}")
                        await self.send_text("当当当当~这是我刚拍的照片，好看吗？")
                        return True, f"成功生成照片: {image_url}"
                    else:
                        await self.send_text("照片生成了，但发送失败了，可能是格式问题...")
                        return False, "照片发送失败"
                else:
                    await self.send_text(f"照片下载失败: {encode_result}")
                    return False, encode_result
            else:
                await self.send_text(f"哎呀，拍照失败了: {result}")
                return False, result

        except Exception as e:
            logger.error(f"{self.log_prefix} 执行拍照动作失败: {e}", exc_info=True)
            traceback.print_exc()
            await self.send_text("呜呜，拍照的时候出了一点小问题...")
            return False, str(e)

    async def _store_picture_info(self, prompt: str, image_url: str):
        """将照片信息存入日志文件"""
        log_file = self.api.get_config("storage.log_file", "picture_log.json")
        log_path = os.path.join(DATA_DIR, log_file)
        max_photos = self.api.get_config("storage.max_photos", 50)

        async with file_lock:
            try:
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8") as f:
                        log_data = json.load(f)
                else:
                    log_data = []
            except (json.JSONDecodeError, FileNotFoundError):
                log_data = []

            # 添加新照片
            log_data.append(
                {"prompt": prompt, "image_url": image_url, "timestamp": datetime.datetime.now().isoformat()}
            )

            # 如果超过最大数量，删除最旧的
            if len(log_data) > max_photos:
                log_data = sorted(log_data, key=lambda x: x.get("timestamp", ""), reverse=True)[:max_photos]

            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    json.dump(log_data, f, ensure_ascii=False, indent=4)
            except Exception as e:
                logger.error(f"{self.log_prefix} 写入照片日志文件失败: {e}", exc_info=True)

    def _make_http_image_request(
        self, prompt: str, model: str, size: str, seed: int, guidance_scale: float, watermark: bool
    ) -> Tuple[bool, str]:
        """发送HTTP请求到火山引擎豆包API生成图片"""
        try:
            base_url = self.api.get_config("api.base_url")
            api_key = self.api.get_config("api.volcano_generate_api_key")

            # 构建请求URL和头部
            endpoint = f"{base_url.rstrip('/')}/images/generations"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            # 构建请求体
            request_body = {
                "model": model,
                "prompt": prompt,
                "response_format": "url",
                "size": size,
                "seed": seed,
                "guidance_scale": guidance_scale,
                "watermark": watermark,
                "api-key": api_key,
            }

            # 创建请求对象
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(request_body).encode("utf-8"),
                headers=headers,
                method="POST",
            )

            # 发送请求并获取响应
            with urllib.request.urlopen(req, timeout=60) as response:
                response_data = json.loads(response.read().decode("utf-8"))

            # 解析响应
            image_url = None
            if (
                isinstance(response_data.get("data"), list)
                and response_data["data"]
                and isinstance(response_data["data"][0], dict)
            ):
                image_url = response_data["data"][0].get("url")
            elif response_data.get("url"):
                image_url = response_data.get("url")

            if image_url:
                return True, image_url
            else:
                error_msg = response_data.get("error", {}).get("message", "未知错误")
                logger.error(f"API返回错误: {error_msg}")
                return False, f"API错误: {error_msg}"

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            logger.error(f"HTTP错误 {e.code}: {error_body}")
            return False, f"HTTP错误 {e.code}: {error_body[:100]}..."
        except Exception as e:
            logger.error(f"请求异常: {e}", exc_info=True)
            return False, f"请求异常: {str(e)}"

    def _download_and_encode_base64(self, image_url: str) -> Tuple[bool, str]:
        """下载图片并转换为Base64编码"""
        try:
            with urllib.request.urlopen(image_url) as response:
                image_data = response.read()

            base64_encoded = base64.b64encode(image_data).decode("utf-8")
            return True, base64_encoded
        except Exception as e:
            logger.error(f"图片下载编码失败: {e}", exc_info=True)
            return False, str(e)

    async def _send_image(self, base64_image: str) -> bool:
        """发送图片"""
        try:
            # 使用聊天流信息确定发送目标
            chat_stream = self.api.get_service("chat_stream")
            if not chat_stream:
                logger.error(f"{self.log_prefix} 没有可用的聊天流发送图片")
                return False

            if chat_stream.group_info:
                # 群聊
                return await self.api.send_message_to_target(
                    message_type="image",
                    content=base64_image,
                    platform=chat_stream.platform,
                    target_id=str(chat_stream.group_info.group_id),
                    is_group=True,
                    display_message="发送生成的照片",
                )
            else:
                # 私聊
                return await self.api.send_message_to_target(
                    message_type="image",
                    content=base64_image,
                    platform=chat_stream.platform,
                    target_id=str(chat_stream.user_info.user_id),
                    is_group=False,
                    display_message="发送生成的照片",
                )
        except Exception as e:
            logger.error(f"{self.log_prefix} 发送图片时出错: {e}")
            return False

    @classmethod
    def _get_cache_key(cls, description: str, model: str, size: str) -> str:
        """生成缓存键"""
        return f"{description}|{model}|{size}"

    def _update_cache(self, description: str, model: str, size: str, base64_image: str):
        """更新缓存"""
        max_cache_size = self.api.get_config("storage.max_cache_size", 10)
        cache_key = self._get_cache_key(description, model, size)

        # 添加到缓存
        self._request_cache[cache_key] = base64_image

        # 如果缓存超过最大大小，删除最旧的项
        if len(self._request_cache) > max_cache_size:
            oldest_key = next(iter(self._request_cache))
            del self._request_cache[oldest_key]


class ShowRecentPicturesCommand(BaseCommand):
    """展示最近生成的照片"""

    command_name = "show_recent_pictures"
    command_description = "展示最近生成的5张照片"
    command_pattern = r"^/show_pics$"
    command_help = "用法: /show_pics"
    command_examples = ["/show_pics"]
    intercept_message = True

    async def execute(self) -> Tuple[bool, Optional[str]]:
        logger.info(f"{self.log_prefix} 执行展示最近照片命令")
        log_file = self.api.get_config("storage.log_file", "picture_log.json")
        log_path = os.path.join(DATA_DIR, log_file)

        async with file_lock:
            try:
                if not os.path.exists(log_path):
                    await self.send_text("最近还没有拍过照片哦，快让我自拍一张吧！")
                    return True, "没有照片日志文件"

                with open(log_path, "r", encoding="utf-8") as f:
                    log_data = json.load(f)

                if not log_data:
                    await self.send_text("最近还没有拍过照片哦，快让我自拍一张吧！")
                    return True, "没有照片"

                # 获取最新的5张照片
                recent_pics = sorted(log_data, key=lambda x: x["timestamp"], reverse=True)[:5]

                # 先发送文本消息
                await self.send_text("这是我最近拍的几张照片~")

                # 逐个发送图片
                for pic in recent_pics:
                    # 尝试获取图片URL
                    image_url = pic.get("image_url")
                    if image_url:
                        try:
                            # 下载图片并转换为Base64
                            with urllib.request.urlopen(image_url) as response:
                                image_data = response.read()
                            base64_encoded = base64.b64encode(image_data).decode("utf-8")

                            # 发送图片
                            await self.send_type(
                                message_type="image", content=base64_encoded, display_message="发送最近的照片"
                            )
                        except Exception as e:
                            logger.error(f"{self.log_prefix} 下载或发送照片失败: {e}", exc_info=True)

                return True, "成功展示最近的照片"

            except json.JSONDecodeError:
                await self.send_text("照片记录文件好像损坏了...")
                return False, "JSON解码错误"
            except Exception as e:
                logger.error(f"{self.log_prefix} 展示照片失败: {e}", exc_info=True)
                await self.send_text("哎呀，查找照片的时候出错了。")
                return False, str(e)


@register_plugin
class TakePicturePlugin(BasePlugin):
    """拍照插件"""

    plugin_name = "take_picture_plugin"  # 内部标识符
    enable_plugin = True
    config_file_name = "config.toml"

    # 配置节描述
    config_section_descriptions = {
        "plugin": "插件基本信息配置",
        "api": "API相关配置，包含火山引擎API的访问信息",
        "components": "组件启用控制",
        "picture": "拍照功能核心配置",
        "storage": "照片存储相关配置",
    }

    # 配置Schema定义
    config_schema = {
        "plugin": {
            "name": ConfigField(type=str, default="take_picture_plugin", description="插件名称", required=True),
            "version": ConfigField(type=str, default="1.0.0", description="插件版本号"),
            "enabled": ConfigField(type=bool, default=False, description="是否启用插件"),
            "description": ConfigField(
                type=str, default="提供生成自拍照和展示最近照片的功能", description="插件描述", required=True
            ),
        },
        "api": {
            "base_url": ConfigField(
                type=str,
                default="https://ark.cn-beijing.volces.com/api/v3",
                description="API基础URL",
                example="https://api.example.com/v1",
            ),
            "volcano_generate_api_key": ConfigField(
                type=str, default="YOUR_DOUBAO_API_KEY_HERE", description="火山引擎豆包API密钥", required=True
            ),
        },
        "components": {
            "enable_take_picture_action": ConfigField(type=bool, default=True, description="是否启用拍照Action"),
            "enable_show_pics_command": ConfigField(type=bool, default=True, description="是否启用展示照片Command"),
        },
        "picture": {
            "default_model": ConfigField(
                type=str,
                default="doubao-seedream-3-0-t2i-250415",
                description="默认使用的文生图模型",
                choices=["doubao-seedream-3-0-t2i-250415", "doubao-seedream-2-0-t2i"],
            ),
            "default_size": ConfigField(
                type=str,
                default="1024x1024",
                description="默认图片尺寸",
                example="1024x1024",
                choices=["1024x1024", "1024x1280", "1280x1024", "1024x1536", "1536x1024"],
            ),
            "default_watermark": ConfigField(type=bool, default=True, description="是否默认添加水印"),
            "default_guidance_scale": ConfigField(
                type=float, default=2.5, description="模型指导强度，影响图片与提示的关联性", example="2.0"
            ),
            "default_seed": ConfigField(type=int, default=42, description="随机种子，用于复现图片"),
            "prompt_templates": ConfigField(
                type=list, default=TakePictureAction.DEFAULT_PROMPT_TEMPLATES, description="用于生成自拍照的prompt模板"
            ),
        },
        "storage": {
            "max_photos": ConfigField(type=int, default=50, description="最大保存的照片数量"),
            "log_file": ConfigField(type=str, default="picture_log.json", description="照片日志文件名"),
            "enable_cache": ConfigField(type=bool, default=True, description="是否启用请求缓存"),
            "max_cache_size": ConfigField(type=int, default=10, description="最大缓存数量"),
        },
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""
        components = []
        if self.get_config("components.enable_take_picture_action", True):
            components.append((TakePictureAction.get_action_info(), TakePictureAction))
        if self.get_config("components.enable_show_pics_command", True):
            components.append((ShowRecentPicturesCommand.get_command_info(), ShowRecentPicturesCommand))
        return components

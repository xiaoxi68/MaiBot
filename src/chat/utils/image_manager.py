import base64
import time
from typing import Optional
from PIL import Image as PilImage
import io

from model_manager.image import ImageDTO, ImageManager
from utils.calc_hash import calc_bytes_hash
from utils.image import gif2jpg


from ...config.config import global_config
from manager.model_manager import global_model_manager
from maibot_api_adapter.payload_content.message import MessageBuilder
from src.common.logger_manager import get_logger
from rich.traceback import install

install(extra_lines=3)

logger = get_logger("chat_image")

IMAGE_DIR = f"{global_config.storage.data_path}/image"


class ChatImageManager:
    """聊天图片管理器，负责处理图片的描述"""

    def __init__(self):
        # self._llm = global_model_manager["image_describe"]
        # """VLM模型请求对象，用于图像描述生成"
        pass

    async def _get_image_desc_by_llm(self, image_bytes: bytes, image_type: str = "normal") -> Optional[str]:
        """
        使用VLM模型获取图片描述

        :param image_b64: 图片的base64字符串
        :param type: 图片类型（默认normal，可选emoji）
        :return: 图片描述
        （如果是None/空字符串，表示获取失败）
        """
        image = PilImage.open(io.BytesIO(image_bytes))
        image_format = image.format.lower()

        if image_format == "gif":
            # GIF图像需要转换为拼接JPG图像
            image, cols, rows, n_frames = gif2jpg(image)
            image_format = "jpg"
            with io.BytesIO() as io_buffer:
                image.save(io_buffer, format="JPEG")
                jpg_bytes = io_buffer.getvalue()
            image_b64 = base64.b64encode(jpg_bytes).decode("utf-8")
            if image_type == "emoji":
                text_content = f"这是一个动态图表情包的拼接图像，从上至下，从左至右，共{rows}行{cols}列。{n_frames}张图像各代表了动态图的某一帧，黑色背景代表透明。请使用简短的语言描述一下表情包表达的情感和内容。"
            else:
                text_content = f"这是一个动态图的拼接图像，从上至下，从左至右，共{rows}行{cols}列。{n_frames}张图像各代表了动态图的某一帧，黑色背景代表透明。请用中文简要描述这张动态图的内容并尝试猜测这个图片的含义。如果有文字，请把文字都描述出来。所有描述最多100个字。"
        else:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            if image_type == "emoji":
                text_content = "这是一个表情包，请使用简短的语言描述一下表情包表达的情感和内容。"
            else:
                text_content = "请用中文简要描述这张图片的内容并尝试猜测这个图片的含义。如果有文字，请把文字都描述出来。所有描述最多100个字。"

        prompt = MessageBuilder().add_text_content(text_content).add_image_content(image_format, image_b64).build()

        response = await global_model_manager["image_describe"].get_response(
            messages=[prompt],
        )
        return response.content.strip()

    async def get_image_description(self, image_b64: str, image_type: str = "normal") -> Optional[str]:
        """
        根据给出的图片路径获取图片描述

        :param image_b64: 图片的base64字符串
        :param type: 图片类型（默认normal，可选emoji）
        :return: 图片DTO对象（如果是None，则表示获取失败）
        """

        # 1. 尝试从持久化层中获取图片描述

        # 解码base64字符串为字节数据
        image_bytes = base64.b64decode(image_b64)
        # 计算图片的SHA-256哈希值
        image_hash = calc_bytes_hash(image_bytes)
        # 创建ImageDTO对象
        image_dto = ImageDTO(img_hash=image_hash)

        if cached_image_dto := ImageManager.get_image(image_dto):
            # 更新查询记录（可用于清理缓存的指标）
            cached_image_dto.query_count += 1
            cached_image_dto.last_queried_at = time.time()
            ImageManager.update_image(cached_image_dto)
            logger.debug(f"成功从持久化层获取图片 {cached_image_dto.img_hash} 的描述")
            return cached_image_dto.description

        # 2. 无法直接取出图片描述，尝试使用VLM模型生成描述

        logger.debug(f"持久化层中没有图片 {image_dto.img_hash} 的描述，尝试使用VLM模型生成描述")

        # 2.1. 创建条目
        image_dto = ImageManager.create_image(image_dto)

        # 2.2. 获取图片描述
        description = await self._get_image_desc_by_llm(image_bytes, image_type)
        if not description:
            # 2.2.1. 如果描述为空，视为获取描述失败
            # 删除数据库中的条目
            ImageManager.delete_image(image_dto)
            logger.debug(f"获取图片 {image_dto.img_hash} 的描述失败，已删除数据库中的条目")
            return None

        # 2.2.2. 成功获取描述，更新数据库中的条目
        image_dto.description = description
        ImageManager.update_image(image_dto)

        logger.debug(f"成功获取图片 {image_dto.img_hash} 的描述：{description}")

        # 2.3. 返回描述
        return description


chat_image_manager = ChatImageManager()
"""全局聊天图片管理器"""

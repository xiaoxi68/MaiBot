import asyncio
import base64
from datetime import datetime, timedelta
import io
import json
import os
import numpy as np
import random
from typing import Optional
from chat.models.utils_model import LLMRequest
from common.logger_manager import get_logger
from src.config.config import global_config
from chat.utils.image_manager import chat_image_manager
from model_manager.emoji import EmojiDTO, EmojiManager
from utils.calc_hash import calc_bytes_hash
from PIL import Image

from utils.image import gif2jpg


logger = get_logger("emoji")


def _emoji_registered_dir():
    """获取表情包已注册目录的完整路径"""
    return f"{global_config.storage.data_path}/emoji/emoji_registered"


def _emoji_banned_dir():
    """获取表情包禁止使用目录的完整路径"""
    return f"{global_config.storage.data_path}/emoji/emoji_banned"


EMOJI_REGISTER_COOLDOWN = timedelta(days=1)
"""表情包注册冷却时间（1天）"""

MAX_SAMPLE_FOR_REPLACEMENT = 20
"""替换表情包时的最大采样数量"""


class ChatEmojiManager:
    """聊天表情包管理器"""

    def __init__(self):
        self.emoji_emotion_map: dict[str, list[str]] = {}
        """表情包映射字典
        {表情包文件hash: 表情包情感描述列表}
        """

        self._emoji_reg_tasks: dict[str, asyncio.Task] = {}
        """表情包注册任务表"""

        # TODO: API-Adapter修改标记

        self._vl_llm = LLMRequest(model=global_config.model.vlm, temperature=0.3, max_tokens=1000, request_type="emoji")
        """VLM模型请求对象"""

        self._tag_gen_llm = LLMRequest(
            model=global_config.model.normal, temperature=0.7, max_tokens=600, request_type="emoji"
        )
        """Tag生成模型请求对象"""

        self._content_filter_llm = LLMRequest(model=global_config.model.vlm, max_tokens=600, request_type="emoji")
        """内容过滤模型请求对象"""

        self._emoji_judge_llm = LLMRequest(
            model=global_config.model.normal, temperature=0.8, max_tokens=600, request_type="emoji"
        )
        """表情包判断模型请求对象"""

        # 1. 从持久化层加载表情包信息
        self._load_emoji_emotions()

        # 2. 检查文件系统中的表情包文件
        self._check_file_exist()

    def _load_emoji_emotions(self) -> None:
        """加载表情包情感描述"""
        all_registered_emojis = EmojiManager.get_all_registered_emojis()
        for emoji_dto in all_registered_emojis:
            try:
                self.emoji_emotion_map[emoji_dto.img_hash] = json.loads(emoji_dto.emotions)
            except json.JSONDecodeError as e:
                logger.warning(f"表情包 {emoji_dto.img_hash} 的情感描述解析失败: {e}")
                continue

    def _check_file_exist(self) -> None:
        """从文件系统加载表情包列表"""
        # 1. 确保目录存在
        os.makedirs(_emoji_registered_dir(), exist_ok=True)
        os.makedirs(_emoji_banned_dir(), exist_ok=True)

        all_emojis = {emoji_dto.img_hash: emoji_dto for emoji_dto in EmojiManager.get_all_emojis()}

        # 2. 检查已注册、禁止使用的表情包文件是否存在
        for emoji_hash, emoji_dto in all_emojis.items():
            if emoji_dto.is_registered:
                # 1.1. 如果是已注册的表情包，检查注册目录
                if not os.path.exists(f"{_emoji_registered_dir()}/{emoji_dto.file_name}"):
                    logger.warning(f"表情包 {emoji_hash} 的图片文件不存在，更新记录为未注册状态")
                    self.emoji_emotion_map.pop(emoji_hash, None)
                    emoji_dto.is_registered = False
                    emoji_dto.last_try_register_at = None
                    EmojiManager.update_emoji(emoji_dto)
            elif emoji_dto.is_banned:
                # 1.2. 如果是禁止使用的表情包，检查禁止目录
                if not os.path.exists(f"{_emoji_banned_dir()}/{emoji_dto.file_name}"):
                    logger.warning(f"表情包 {emoji_hash} 的图片文件不存在，更新记录为未注册状态")
                    emoji_dto.is_banned = False
                    emoji_dto.is_registered = False
                    emoji_dto.last_try_register_at = None
                    EmojiManager.update_emoji(emoji_dto)

    def _ban_emoji(self, emoji_hash: str) -> None:
        """禁止使用表情包

        :param emoji_hash: 表情包的哈希值
        """
        emoji_dto = EmojiManager.get_emoji(EmojiDTO(img_hash=emoji_hash))
        if not emoji_dto:
            logger.error(f"尝试禁止不存在的表情包 {emoji_hash}")
            return

        if emoji_dto.is_banned:
            logger.info(f"表情包 {emoji_hash} 已经被禁止，跳过")
            return

        # 将表情包移动到禁止目录
        os.rename(f"{_emoji_registered_dir()}/{emoji_dto.file_name}", f"{_emoji_banned_dir()}/{emoji_dto.file_name}")

        emoji_dto.is_banned = True
        emoji_dto.is_registered = False
        emoji_dto.last_try_register_at = None
        EmojiManager.update_emoji(emoji_dto)

        self.emoji_emotion_map.pop(emoji_hash, None)
        logger.info(f"表情包 {emoji_hash} 已被禁止使用")

    async def _get_or_create_emoji_dto(self, image_b64: str, hash: str) -> Optional[EmojiDTO]:
        """
        获取或创建表情包DTO对象

        :param image_b64: 表情包的base64字符串
        :param hash: 表情包的哈希值
        :return: 表情包DTO对象
        """
        emoji_dto = EmojiManager.get_emoji(EmojiDTO(img_hash=hash))
        if not emoji_dto:
            image_bytes = base64.b64decode(image_b64)
            image = Image.open(io.BytesIO(image_bytes))

            if image.format.lower() == "gif":
                image, cols, rows, n_frames = gif2jpg(image)
                prompt = f"这是一个动态图表情包的拼接图像，从上至下，从左至右，共{rows}行{cols}列。{n_frames}张图像代表了动态图的某一帧，黑色背景代表透明。描述一下表情包表达的情感和内容，尽可能多的描述细节，从互联网梗、meme的角度去分析"
                image_b64 = base64.b64encode(image.tobytes()).decode("utf-8")
                description, _ = await self._vl_llm.generate_response_for_image(prompt, image_b64, "jpg")
            else:
                prompt = "这是一个表情包，请详细描述一下表情包所表达的情感和内容，尽可能多的描述细节，从互联网梗、meme的角度去分析"
                description, _ = await self._vl_llm.generate_response_for_image(prompt, image_b64, image.format.lower())

            if not description:
                logger.error(f"表情包 {hash} 的描述获取失败，注册失败")
                return None

            # TODO: 进行内容过滤

            emotion_prompt = f"请你识别这个表情包的含义和适用场景，给我简短的描述，每个描述不要超过15个字\n这是一个基于这个表情包的描述：'{description}'\n你可以关注其幽默和讽刺意味，动用贴吧，微博，小红书的知识，必须从互联网梗、meme的角度去分析\n请直接输出描述，不要出现任何其他内容，如果有多个描述，可以用英文逗号(\",\")分隔"
            emotions_text, _ = await self._tag_gen_llm.generate_response_async(emotion_prompt, temperature=0.7)

            emotions = [emotion.strip() for emotion in emotions_text.split(",") if emotion.strip()]

            # 避免情感描述过多
            if len(emotions) > 5:
                emotions = random.sample(emotions, 3)
            elif len(emotions) > 2:
                emotions = random.sample(emotions, 2)

            if not emotions:
                logger.error(f"表情包 {hash} 的情感描述获取失败，注册失败")
                return None

            emoji_dto = EmojiDTO(
                img_hash=hash,
                emotions=json.dumps(emotions, ensure_ascii=False),
            )
            emoji_dto = EmojiManager.create_emoji(emoji_dto)

        return emoji_dto

    async def _async_register_emoji(self, image_b64: str, hash: str) -> None:
        """
        异步任务：尝试注册表情包

        :param image_b64: 表情包的base64字符串
        :param hash: 表情包的哈希值
        """
        emoji_dto = await self._get_or_create_emoji_dto(image_b64, hash)
        if not emoji_dto:
            return

        if emoji_dto.is_banned:
            logger.info(f"表情包 {hash} 已被禁用，跳过注册")
            return
        elif (
            emoji_dto.last_try_register_at and emoji_dto.last_try_register_at + EMOJI_REGISTER_COOLDOWN > datetime.now()
        ):
            logger.info(f"表情包 {hash} 在注册冷却期内，跳过注册")
            return

        if len(self.emoji_emotion_map) >= global_config.emoji.max_emoji_num and not global_config.emoji.do_replace:
            logger.debug("表情包数量已达到最大限制，且不允许替换已有表情包，跳过注册")
            return

        if len(self.emoji_emotion_map) >= global_config.emoji.max_emoji_num:
            await self._replace_emoji()

        await self._register_new_emoji(image_b64, emoji_dto, hash)

    async def _replace_emoji(self):
        """替换已有表情包"""
        logger.warning("表情包数量已达到最大限制，已设置允许替换已有表情包，将尝试替换...")
        registered_emojis = EmojiManager.get_all_registered_emojis()
        weights = np.array([1 / (e.usage_count + 1) for e in registered_emojis])
        probs = weights / weights.sum()
        indices = random.choices(
            registered_emojis,
            weights=probs,
            k=1,
        )
        emoji_to_replace = indices[0]

        logger.debug(f"将替换表情包 {emoji_to_replace.img_hash}，使用次数：{emoji_to_replace.usage_count}")

        emoji_to_replace.is_registered = False
        emoji_to_replace.last_try_register_at = datetime.now()  # 更新尝试注册时间戳，避免频繁换入换出
        EmojiManager.update_emoji(emoji_to_replace)

        os.remove(f"{_emoji_registered_dir()}/{emoji_to_replace.file_name}")

        self.emoji_emotion_map.pop(emoji_to_replace.img_hash, None)
        logger.debug(f"表情包 {emoji_to_replace.img_hash} 已被替换，移动到缓存目录")

    async def _register_new_emoji(self, image_b64: str, emoji_dto: EmojiDTO, hash: str):
        """注册新的表情包"""

        # 将表情包图片保存到已注册目录
        image_data = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(image_data))
        file_name = f"{hash}.{image.format.lower()}"
        image.save(f"{_emoji_registered_dir()}/{file_name}")

        emoji_dto.file_name = file_name
        emoji_dto.is_registered = True
        emoji_dto.last_try_register_at = datetime.now()
        EmojiManager.update_emoji(emoji_dto)

        self.emoji_emotion_map[hash] = json.loads(emoji_dto.emotions)
        logger.info(f"表情包 {hash} 注册成功，情感描述：{emoji_dto.emotions}")

    def _register_task_callback(self, task: asyncio.Task):
        """注册任务完成后的回调函数"""
        image_hash = task.get_name()
        try:
            task.result()  # 获取任务结果，如果任务被取消或失败会抛出异常
            logger.info(f"表情包注册任务 EmojiHash '{image_hash}' 完成")
        except asyncio.CancelledError:
            logger.info(f"表情包注册任务 EmojiHash '{image_hash}' 被取消")
        except Exception as e:
            logger.error(f"表情包注册任务 EmojiHash '{image_hash}' 执行时发生异常: {e}", exc_info=True)
        finally:
            # 清理任务
            self._emoji_reg_tasks.pop(image_hash, None)

    def get_emoji_description(self, image_b64: str) -> str:
        """
        根据给出的表情包的base64字符串获取表情包描述

        :param image_b64: 表情包的base64字符串
        :return: 表情包描述
        （如果是None/空字符串，表示已有其它正在进行的获取描述的请求）
        """

        # 1. 从ChatImageManager获取表情包图片描述
        description = chat_image_manager.get_image_description(image_b64, image_type="emoji")

        if not description:
            return None  # 如果获取失败，返回None/空字符串

        # 2. 若该表情包尚未注册，发起异步任务尝试注册表情包

        # 解码base64字符串为字节数据
        image_bytes = base64.b64decode(image_b64)
        # 计算图片的SHA-256哈希值
        image_hash = calc_bytes_hash(image_bytes)
        # 表情包尚未注册，且没有对这个表情包正在进行的注册任务
        if image_hash not in self.emoji_emotion_map and image_hash not in self._emoji_reg_tasks:
            # 2.1. 创建注册任务
            self._emoji_reg_tasks[image_hash] = asyncio.create_task(self._async_register_emoji(image_b64, image_hash))
            self._emoji_reg_tasks[image_hash].set_name(image_hash)
            self._emoji_reg_tasks[image_hash].add_done_callback(
                self._register_task_callback
            )  # 回调函数，当任务完成时移除任务

        return description

    def _calc_emoji_similarity(self, text_emotions: str) -> list[tuple[str, float]]:
        """
        计算表情包与输入文本的相似度

        :param text_emotions: 输入的情感描述文本
        :return: 表情包哈希值和相似度列表
        """
        emoji_list: list[tuple[str, float]] = []
        for emoji_hash, emoji_emotions in self.emoji_emotion_map.items():
            max_similarity = 0
            for emotion in emoji_emotions:
                similarity = _calc_similarity(text_emotions, emotion)  # 计算相似度
                if similarity > max_similarity:
                    max_similarity = similarity

            if max_similarity > 0:
                emoji_list.append((emoji_hash, max_similarity))

        return emoji_list

    def search_emoji_for_text(self, text_emotions: str) -> Optional[bytes]:
        """
        根据给出的文本内容搜索表情包

        :param text_emotions: 输入的情感描述文本
        :return: 表情包图像
        """
        if not self.emoji_emotion_map:
            return None

        # 1. 未提供参考文本，随机抽取一个表情包
        if not text_emotions:
            emoji_hash = random.choice(list(self.emoji_emotion_map.keys()))
            emoji_dto = _get_emoji_dto(emoji_hash)
            logger.info(f"随机选择表情包 {emoji_hash}")
            return emoji_dto

        # 2. 提供了参考文本，根据相似度匹配选择表情包

        # 2.1. 遍历表情包映射字典，计算与输入文本的相似度
        emoji_list = self._calc_emoji_similarity(text_emotions)

        # 2.2. 按相似度降序排序，截取前5个，从中随机抽取一个
        emoji_list.sort(key=lambda x: x[1], reverse=True)
        emoji_list = emoji_list[:5]

        if not emoji_list:
            logger.debug(f"没有找到与输入文本 '{text_emotions}' 匹配的表情包")
            return None

        emoji_hash, similarity = random.choice(emoji_list)

        # 2.3. 从持久化层获取表情包DTO
        emoji_dto = _get_emoji_dto(emoji_hash)

        logger.info(f"找到与输入文本 '{text_emotions}' 匹配的表情包 {emoji_hash}，相似度为: {similarity}")

        if os.path.exists(f"{_emoji_registered_dir()}/{emoji_dto.file_name}"):
            return open(f"{_emoji_registered_dir()}/{emoji_dto.file_name}", "rb").read()

        logger.error(f"表情包 {emoji_hash} 的文件不存在，可能已被删除或移动")
        return None


def _calc_similarity(s1: str, s2: str) -> float:
    """计算两个字符串之间的相似度

    此处使用编辑距离（Levenshtein distance）算法
    """
    if len(s1) < len(s2):
        s1, s2 = s2, s1  # 保证s1较长，减少空间使用

    if not s1:
        return 1  # 如果s1为空，说明输入了两个空串，直接返回1（相似度为100%）

    previous = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1, 1):
        current = [i]
        for j, c2 in enumerate(s2, 1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            replace = previous[j - 1] + (c1 != c2)
            current.append(min(insert, delete, replace))
        previous = current

    diff = previous[-1]

    return 1 - (diff / len(s1))


def _get_emoji_dto(emoji_hash: str) -> Optional[EmojiDTO]:
    """
    从持久化层获取表情包信息

    :param emoji_hash: 表情包的哈希值
    :return: 表情包DTO对象
    """
    emoji_dto = EmojiManager.get_emoji(EmojiDTO(img_hash=emoji_hash))

    if not emoji_dto:
        logger.error(f"未能从持久化层获取表情包 {emoji_hash} 的信息")
        return None

    emoji_dto.usage_count += 1
    emoji_dto.last_used_at = datetime.now()
    EmojiManager.update_emoji(emoji_dto)

    return emoji_dto


chat_emoji_manager = ChatEmojiManager()
"""全局聊天表情包管理器"""

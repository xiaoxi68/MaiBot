#!/usr/bin/env python3
"""
NormalChat 启动停止测试脚本
"""

import asyncio
import logging
from src.common.logger import get_logger

logger = get_logger("test_normal_chat_stop")


async def test_task_cancel_behavior():
    """测试任务取消行为"""

    class MockNormalChat:
        def __init__(self):
            self._disabled = False
            self._chat_task = None
            self.stream_name = "test_stream"

        async def mock_reply_loop(self):
            """模拟回复循环"""
            logger.info("模拟回复循环开始")
            try:
                while True:
                    # 检查停用标志
                    if self._disabled:
                        logger.info("检测到停用标志，退出循环")
                        break

                    # 模拟工作
                    logger.info("模拟处理消息...")
                    await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                logger.info("模拟回复循环被取消")
                raise
            except Exception as e:
                logger.error(f"模拟回复循环出错: {e}")
            finally:
                logger.info("模拟回复循环结束")

        async def start_chat(self):
            """启动聊天"""
            if self._chat_task and not self._chat_task.done():
                logger.info("任务已在运行")
                return

            self._disabled = False
            self._chat_task = asyncio.create_task(self.mock_reply_loop())
            logger.info("聊天任务已启动")

        async def stop_chat(self):
            """停止聊天"""
            logger.info("开始停止聊天")

            # 设置停用标志
            self._disabled = True

            if not self._chat_task or self._chat_task.done():
                logger.info("没有运行中的任务")
                return

            # 保存任务引用并清空
            task_to_cancel = self._chat_task
            self._chat_task = None

            # 取消任务
            task_to_cancel.cancel()

            logger.info("聊天任务停止完成")

    # 测试正常启动停止
    logger.info("=== 测试正常启动停止 ===")
    chat = MockNormalChat()

    # 启动
    await chat.start_chat()
    await asyncio.sleep(0.5)  # 让任务运行一会

    # 停止
    await chat.stop_chat()
    await asyncio.sleep(0.1)  # 让取消操作完成

    logger.info("=== 测试完成 ===")


async def main():
    """主函数"""
    logger.info("开始 NormalChat 停止测试")

    try:
        await test_task_cancel_behavior()
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback

        logger.error(traceback.format_exc())

    logger.info("测试结束")


if __name__ == "__main__":
    # 设置日志级别
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

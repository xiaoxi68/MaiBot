# 定义了来自外部世界的信息
# 外部世界可以是某个聊天 不同平台的聊天 也可以是任意媒体
from datetime import datetime
from src.common.logger import get_logger
from src.chat.focus_chat.hfc_utils import CycleDetail
from typing import List
# Import the new utility function

logger = get_logger("loop_info")


# 所有观察的基类
class FocusLoopInfo:
    def __init__(self, observe_id):
        self.observe_id = observe_id
        self.last_observe_time = datetime.now().timestamp()  # 初始化为当前时间
        self.history_loop: List[CycleDetail] = []

    def add_loop_info(self, loop_info: CycleDetail):
        self.history_loop.append(loop_info)

    async def observe(self):
        recent_active_cycles: List[CycleDetail] = []
        for cycle in reversed(self.history_loop):
            # 只关心实际执行了动作的循环
            # action_taken = cycle.loop_action_info["action_taken"]
            # if action_taken:
            recent_active_cycles.append(cycle)
            if len(recent_active_cycles) == 5:
                break

        cycle_info_block = ""
        action_detailed_str = ""
        consecutive_text_replies = 0
        responses_for_prompt = []

        cycle_last_reason = ""

        # 检查这最近的活动循环中有多少是连续的文本回复 (从最近的开始看)
        for cycle in recent_active_cycles:
            action_result = cycle.loop_plan_info.get("action_result", {})
            action_type = action_result.get("action_type", "unknown")
            action_reasoning = action_result.get("reasoning", "未提供理由")
            is_taken = cycle.loop_action_info.get("action_taken", False)
            action_taken_time = cycle.loop_action_info.get("taken_time", 0)
            action_taken_time_str = (
                datetime.fromtimestamp(action_taken_time).strftime("%H:%M:%S") if action_taken_time > 0 else "未知时间"
            )
            if action_reasoning != cycle_last_reason:
                cycle_last_reason = action_reasoning
                action_reasoning_str = f"你选择这个action的原因是:{action_reasoning}"
            else:
                action_reasoning_str = ""

            if action_type == "reply":
                consecutive_text_replies += 1
                response_text = cycle.loop_action_info.get("reply_text", "")
                responses_for_prompt.append(response_text)

                if is_taken:
                    action_detailed_str += f"{action_taken_time_str}时，你选择回复(action:{action_type},内容是:'{response_text}')。{action_reasoning_str}\n"
                else:
                    action_detailed_str += f"{action_taken_time_str}时，你选择回复(action:{action_type},内容是:'{response_text}')，但是动作失败了。{action_reasoning_str}\n"
            elif action_type == "no_reply":
                pass
            else:
                if is_taken:
                    action_detailed_str += (
                        f"{action_taken_time_str}时，你选择执行了(action:{action_type})，{action_reasoning_str}\n"
                    )
                else:
                    action_detailed_str += f"{action_taken_time_str}时，你选择执行了(action:{action_type})，但是动作失败了。{action_reasoning_str}\n"

        if action_detailed_str:
            cycle_info_block = f"\n你最近做的事：\n{action_detailed_str}\n"
        else:
            cycle_info_block = "\n"


        # 获取history_loop中最新添加的
        if self.history_loop:
            last_loop = self.history_loop[0]
            start_time = last_loop.start_time
            end_time = last_loop.end_time
            if start_time is not None and end_time is not None:
                time_diff = int(end_time - start_time)
                if time_diff > 60:
                    cycle_info_block += f"距离你上一次阅读消息并思考和规划，已经过去了{int(time_diff / 60)}分钟\n"
                else:
                    cycle_info_block += f"距离你上一次阅读消息并思考和规划，已经过去了{time_diff}秒\n"
            else:
                cycle_info_block += "你还没看过消息\n"
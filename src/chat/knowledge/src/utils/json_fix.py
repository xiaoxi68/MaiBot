import json
from json_repair import repair_json

# 以下代码用于修复损坏的 JSON 字符串。

def fix_broken_generated_json(json_str: str) -> str:
    """
    使用 json-repair 库修复格式错误的 JSON 字符串。

    如果原始 json_str 字符串可以被 json.loads() 成功加载，则直接返回而不进行任何修改。

    参数:
        json_str (str): 需要修复的格式错误的 JSON 字符串。

    返回:
        str: 修复后的 JSON 字符串。
    """
    try:
        # 尝试加载 JSON 以查看其是否有效
        json.loads(json_str)
        return json_str  # 如果有效则按原样返回
    except json.JSONDecodeError:
        # 如果无效，则尝试修复它
        return repair_json(json_str)

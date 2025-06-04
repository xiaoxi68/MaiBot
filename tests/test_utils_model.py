import asyncio
import pytest
from src.llm_models.utils_model import LLMRequest
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

@pytest.mark.asyncio
async def test_model_request():
    # 创建模型配置
    model_config = {
        "name": "deepseek-v3",  # 使用测试模型
        "provider": "CHATANY",  # 使用测试提供商
        "temp": 0.3,
        "enable_thinking": False
    }
    
    # 创建LLMRequest实例
    llm = LLMRequest(model=model_config)
    
    # 测试提示词
    test_prompt = "你好，请做个自我介绍"
    
    try:
        # 测试生成响应
        content, (reasoning_content, model_name) = await llm.generate_response_async(test_prompt)
        
        # 打印结果
        print(f"\n模型名称: {model_name}")
        print(f"回复内容: {content}")
        print(f"推理内容: {reasoning_content}")
        
        # 基本断言
        assert content is not None, "回复内容不应为空"
        assert isinstance(content, str), "回复内容应为字符串"
        
    except Exception as e:
        pytest.fail(f"测试失败: {str(e)}")

if __name__ == "__main__":
    # 直接运行测试
    asyncio.run(test_model_request()) 
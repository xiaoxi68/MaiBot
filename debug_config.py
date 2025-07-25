#!/usr/bin/env python3
"""
调试配置加载问题，查看API provider的配置是否正确传递
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def debug_config_loading():
    try:
        # 临时配置API key
        import toml
        config_path = "config/model_config.toml"
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = toml.load(f)
        
        original_keys = {}
        for provider in config['api_providers']:
            original_keys[provider['name']] = provider['api_key']
            provider['api_key'] = f"sk-test-key-for-{provider['name'].lower()}-12345"
        
        with open(config_path, 'w', encoding='utf-8') as f:
            toml.dump(config, f)
        
        print("✅ 配置了测试API key")
        
        try:
            # 清空缓存
            modules_to_remove = [
                'src.config.config',
                'src.config.api_ada_configs',
                'src.llm_models.model_manager',
                'src.llm_models.model_client',
                'src.llm_models.utils_model'
            ]
            for module in modules_to_remove:
                if module in sys.modules:
                    del sys.modules[module]
            
            # 导入配置
            from src.config.config import model_config
            print("\n🔍 调试配置加载:")
            print(f"model_config类型: {type(model_config)}")
            
            # 检查API providers
            if hasattr(model_config, 'api_providers'):
                print(f"API providers数量: {len(model_config.api_providers)}")
                for name, provider in model_config.api_providers.items():
                    print(f"  - {name}: {provider.base_url}")
                    print(f"    API key: {provider.api_key[:10]}...{provider.api_key[-5:] if len(provider.api_key) > 15 else provider.api_key}")
                    print(f"    Client type: {provider.client_type}")
            
            # 检查模型配置
            if hasattr(model_config, 'models'):
                print(f"模型数量: {len(model_config.models)}")
                for name, model in model_config.models.items():
                    print(f"  - {name}: {model.model_identifier} (提供商: {model.api_provider})")
            
            # 检查任务配置
            if hasattr(model_config, 'task_model_arg_map'):
                print(f"任务配置数量: {len(model_config.task_model_arg_map)}")
                for task_name, task_config in model_config.task_model_arg_map.items():
                    print(f"  - {task_name}: {task_config}")
                    
            # 尝试初始化ModelManager
            print("\n🔍 调试ModelManager初始化:")
            from src.llm_models.model_manager import ModelManager
            
            try:
                model_manager = ModelManager(model_config)
                print("✅ ModelManager初始化成功")
                
                # 检查API客户端映射
                print(f"API客户端数量: {len(model_manager.api_client_map)}")
                for name, client in model_manager.api_client_map.items():
                    print(f"  - {name}: {type(client).__name__}")
                    if hasattr(client, 'client') and hasattr(client.client, 'api_key'):
                        api_key = client.client.api_key
                        print(f"    Client API key: {api_key[:10]}...{api_key[-5:] if len(api_key) > 15 else api_key}")
                
                # 尝试获取任务处理器
                try:
                    handler = model_manager["llm_normal"]
                    print("✅ 成功获取llm_normal任务处理器")
                    print(f"任务处理器类型: {type(handler).__name__}")
                except Exception as e:
                    print(f"❌ 获取任务处理器失败: {e}")
                
            except Exception as e:
                print(f"❌ ModelManager初始化失败: {e}")
                import traceback
                traceback.print_exc()
                
        finally:
            # 恢复配置
            for provider in config['api_providers']:
                provider['api_key'] = original_keys[provider['name']]
            
            with open(config_path, 'w', encoding='utf-8') as f:
                toml.dump(config, f)
            print("\n✅ 配置已恢复")
        
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_config_loading()

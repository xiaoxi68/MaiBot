# 📦 依赖管理完整示例

> 这个示例展示了如何在插件中正确使用Python依赖管理功能。

## 🎯 示例插件：智能数据分析插件

这个插件展示了如何处理必需依赖、可选依赖，以及优雅降级处理。

```python
"""
智能数据分析插件
展示依赖管理的完整用法
"""

from src.plugin_system import (
    BasePlugin, 
    BaseAction, 
    register_plugin,
    ActionInfo,
    PythonDependency,
    ActionActivationType
)
from src.common.logger import get_logger

logger = get_logger("data_analysis_plugin")


@register_plugin
class DataAnalysisPlugin(BasePlugin):
    """智能数据分析插件"""
    
    plugin_name = "data_analysis_plugin"
    plugin_description = "提供数据分析和可视化功能的示例插件"
    plugin_version = "1.0.0"
    plugin_author = "MaiBot Team"
    
    # 声明Python包依赖
    python_dependencies = [
        # 必需依赖 - 核心功能
        PythonDependency(
            package_name="requests",
            version=">=2.25.0",
            description="HTTP库，用于获取外部数据"
        ),
        
        # 可选依赖 - 数据处理
        PythonDependency(
            package_name="pandas",
            version=">=1.3.0",
            optional=True,
            description="数据处理库，提供高级数据操作功能"
        ),
        
        # 可选依赖 - 数值计算
        PythonDependency(
            package_name="numpy",
            version=">=1.20.0",
            optional=True,
            description="数值计算库，用于数学运算"
        ),
        
        # 可选依赖 - 数据可视化
        PythonDependency(
            package_name="matplotlib",
            version=">=3.3.0",
            optional=True,
            description="绘图库，用于生成数据图表"
        ),
        
        # 特殊情况：导入名与安装名不同
        PythonDependency(
            package_name="PIL",
            install_name="Pillow",
            version=">=8.0.0",
            optional=True,
            description="图像处理库，用于图表保存和处理"
        ),
    ]
    
    def get_plugin_components(self):
        """返回插件组件"""
        return [
            # 基础数据获取（只依赖requests）
            (ActionInfo(
                name="fetch_data_action",
                description="获取外部数据",
                focus_activation_type=ActionActivationType.KEYWORD,
                normal_activation_type=ActionActivationType.KEYWORD,
                activation_keywords=["获取数据", "下载数据"],
            ), FetchDataAction),
            
            # 数据分析（依赖pandas和numpy）
            (ActionInfo(
                name="analyze_data_action",
                description="数据分析和统计",
                focus_activation_type=ActionActivationType.KEYWORD,
                normal_activation_type=ActionActivationType.KEYWORD,
                activation_keywords=["分析数据", "数据统计"],
            ), AnalyzeDataAction),
            
            # 数据可视化（依赖matplotlib）
            (ActionInfo(
                name="visualize_data_action",
                description="数据可视化",
                focus_activation_type=ActionActivationType.KEYWORD,
                normal_activation_type=ActionActivationType.KEYWORD,
                activation_keywords=["数据图表", "可视化"],
            ), VisualizeDataAction),
        ]


class FetchDataAction(BaseAction):
    """数据获取Action - 仅依赖必需的requests库"""
    
    async def execute(self, action_input, context=None):
        """获取外部数据"""
        try:
            import requests
            
            # 模拟数据获取
            url = action_input.get("url", "https://api.github.com/users/octocat")
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            return {
                "status": "success",
                "message": f"成功获取数据，响应大小: {len(str(data))} 字符",
                "data": data,
                "capabilities": ["basic_fetch"]
            }
            
        except ImportError:
            return {
                "status": "error",
                "message": "缺少必需依赖：requests库",
                "hint": "请运行: pip install requests>=2.25.0",
                "error_code": "MISSING_DEPENDENCY"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"数据获取失败: {str(e)}",
                "error_code": "FETCH_ERROR"
            }


class AnalyzeDataAction(BaseAction):
    """数据分析Action - 支持多级功能降级"""
    
    async def execute(self, action_input, context=None):
        """分析数据，支持功能降级"""
        
        # 检查可用的依赖
        has_pandas = self._check_dependency("pandas")
        has_numpy = self._check_dependency("numpy")
        
        # 获取输入数据
        data = action_input.get("data", [1, 2, 3, 4, 5])
        
        if has_pandas and has_numpy:
            return await self._advanced_analysis(data)
        elif has_numpy:
            return await self._numpy_analysis(data)
        else:
            return await self._basic_analysis(data)
    
    def _check_dependency(self, package_name):
        """检查依赖是否可用"""
        try:
            __import__(package_name)
            return True
        except ImportError:
            return False
    
    async def _advanced_analysis(self, data):
        """高级分析（使用pandas + numpy）"""
        import pandas as pd
        import numpy as np
        
        # 转换为DataFrame
        df = pd.DataFrame({"values": data})
        
        # 高级统计分析
        stats = {
            "count": len(df),
            "mean": df["values"].mean(),
            "median": df["values"].median(),
            "std": df["values"].std(),
            "min": df["values"].min(),
            "max": df["values"].max(),
            "quartiles": df["values"].quantile([0.25, 0.5, 0.75]).to_dict(),
            "skewness": df["values"].skew(),
            "kurtosis": df["values"].kurtosis()
        }
        
        return {
            "status": "success",
            "message": "高级数据分析完成",
            "data": stats,
            "method": "advanced",
            "capabilities": ["pandas", "numpy", "advanced_stats"]
        }
    
    async def _numpy_analysis(self, data):
        """中级分析（仅使用numpy）"""
        import numpy as np
        
        arr = np.array(data)
        
        stats = {
            "count": len(arr),
            "mean": np.mean(arr),
            "median": np.median(arr),
            "std": np.std(arr),
            "min": np.min(arr),
            "max": np.max(arr),
            "sum": np.sum(arr)
        }
        
        return {
            "status": "success",
            "message": "数值计算分析完成",
            "data": stats,
            "method": "numpy",
            "capabilities": ["numpy", "basic_stats"]
        }
    
    async def _basic_analysis(self, data):
        """基础分析（纯Python）"""
        
        stats = {
            "count": len(data),
            "mean": sum(data) / len(data) if data else 0,
            "min": min(data) if data else None,
            "max": max(data) if data else None,
            "sum": sum(data)
        }
        
        return {
            "status": "success",
            "message": "基础数据分析完成",
            "data": stats,
            "method": "basic",
            "capabilities": ["pure_python"],
            "note": "安装numpy和pandas可获得更多分析功能"
        }


class VisualizeDataAction(BaseAction):
    """数据可视化Action - 展示条件功能启用"""
    
    async def execute(self, action_input, context=None):
        """数据可视化"""
        
        # 检查可视化依赖
        visualization_available = self._check_visualization_deps()
        
        if not visualization_available:
            return {
                "status": "unavailable",
                "message": "数据可视化功能不可用",
                "reason": "缺少matplotlib和PIL依赖",
                "install_hint": "pip install matplotlib>=3.3.0 Pillow>=8.0.0",
                "alternative": "可以使用基础数据分析功能"
            }
        
        return await self._create_visualization(action_input)
    
    def _check_visualization_deps(self):
        """检查可视化所需的依赖"""
        try:
            import matplotlib
            import PIL
            return True
        except ImportError:
            return False
    
    async def _create_visualization(self, action_input):
        """创建数据可视化"""
        import matplotlib.pyplot as plt
        import io
        import base64
        from PIL import Image
        
        # 获取数据
        data = action_input.get("data", [1, 2, 3, 4, 5])
        chart_type = action_input.get("type", "line")
        
        # 创建图表
        plt.figure(figsize=(10, 6))
        
        if chart_type == "line":
            plt.plot(data)
            plt.title("线性图")
        elif chart_type == "bar":
            plt.bar(range(len(data)), data)
            plt.title("柱状图")
        elif chart_type == "hist":
            plt.hist(data, bins=10)
            plt.title("直方图")
        else:
            plt.plot(data)
            plt.title("默认线性图")
        
        plt.xlabel("索引")
        plt.ylabel("数值")
        plt.grid(True)
        
        # 保存为字节流
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        
        # 转换为base64
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        plt.close()  # 释放内存
        
        return {
            "status": "success",
            "message": f"生成{chart_type}图表成功",
            "data": {
                "chart_type": chart_type,
                "data_points": len(data),
                "image_base64": image_base64
            },
            "capabilities": ["matplotlib", "pillow", "visualization"]
        }


# 测试和演示代码
async def demo_dependency_management():
    """演示依赖管理功能"""
    
    print("🔍 插件依赖管理演示")
    print("=" * 50)
    
    # 创建插件实例
    plugin = DataAnalysisPlugin()
    
    print("\n📦 插件依赖信息:")
    for dep in plugin.python_dependencies:
        status = "✅" if plugin._check_dependency_available(dep.package_name) else "❌"
        optional_str = " (可选)" if dep.optional else " (必需)"
        print(f"  {status} {dep.package_name} {dep.version}{optional_str}")
        print(f"     {dep.description}")
    
    print("\n🧪 功能测试:")
    
    # 测试数据获取
    fetch_action = FetchDataAction()
    result = await fetch_action.execute({"url": "https://httpbin.org/json"})
    print(f"  数据获取: {result['status']}")
    
    # 测试数据分析
    analyze_action = AnalyzeDataAction()
    test_data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    result = await analyze_action.execute({"data": test_data})
    print(f"  数据分析: {result['status']} (方法: {result.get('method', 'unknown')})")
    print(f"    可用功能: {result.get('capabilities', [])}")
    
    # 测试数据可视化
    viz_action = VisualizeDataAction()
    result = await viz_action.execute({"data": test_data, "type": "line"})
    print(f"  数据可视化: {result['status']}")
    
    print("\n💡 依赖管理建议:")
    missing_deps = plugin.plugin_info.get_missing_packages()
    if missing_deps:
        print("  缺失的必需依赖:")
        for dep in missing_deps:
            print(f"    - {dep.get_pip_requirement()}")
        print(f"\n  安装命令:")
        print(f"    pip install {' '.join([dep.get_pip_requirement() for dep in missing_deps])}")
    else:
        print("  ✅ 所有必需依赖都已安装")


if __name__ == "__main__":
    import asyncio
    
    # 为演示添加依赖检查方法
    def _check_dependency_available(package_name):
        try:
            __import__(package_name)
            return True
        except ImportError:
            return False
    
    DataAnalysisPlugin._check_dependency_available = _check_dependency_available
    
    # 运行演示
    asyncio.run(demo_dependency_management())
```

## 🎯 示例说明

### 1. 依赖分层设计

这个示例展示了三层依赖设计：

- **必需依赖**: `requests` - 核心功能必需
- **增强依赖**: `pandas`, `numpy` - 提供更强大的分析能力
- **可选依赖**: `matplotlib`, `PIL` - 提供可视化功能

### 2. 优雅降级策略

```python
# 三级功能降级
if has_pandas and has_numpy:
    return await self._advanced_analysis(data)      # 最佳体验
elif has_numpy:
    return await self._numpy_analysis(data)         # 中等体验
else:
    return await self._basic_analysis(data)         # 基础体验
```

### 3. 条件功能启用

```python
# 只有依赖可用时才提供功能
visualization_available = self._check_visualization_deps()
if not visualization_available:
    return {"status": "unavailable", "install_hint": "..."}
```

## 🚀 使用这个示例

### 1. 复制代码

将示例代码保存为 `plugins/data_analysis_plugin/plugin.py`

### 2. 测试依赖检查

```python
from src.plugin_system import plugin_manager

# 检查这个插件的依赖
result = plugin_manager.check_all_dependencies()
print(result['plugin_status']['data_analysis_plugin'])
```

### 3. 安装缺失依赖

```python
# 生成requirements文件
plugin_manager.generate_plugin_requirements("data_plugin_deps.txt")

# 手动安装
# pip install -r data_plugin_deps.txt
```

### 4. 测试功能降级

```bash
# 测试基础功能（只安装requests）
pip install requests>=2.25.0

# 测试增强功能（添加数据处理）
pip install numpy>=1.20.0 pandas>=1.3.0

# 测试完整功能（添加可视化）
pip install matplotlib>=3.3.0 Pillow>=8.0.0
```

## 💡 最佳实践总结

1. **分层依赖设计**: 区分核心、增强、可选依赖
2. **优雅降级处理**: 提供多级功能体验
3. **明确错误信息**: 告诉用户如何解决依赖问题
4. **条件功能启用**: 根据依赖可用性动态调整功能
5. **详细依赖描述**: 说明每个依赖的用途

这个示例展示了如何构建一个既强大又灵活的插件，即使在依赖不完整的情况下也能提供有用的功能。 
#!/usr/bin/env python3
"""
版本兼容性检查测试脚本

测试版本号标准化、比较和兼容性检查功能
"""

import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.plugin_system.utils.manifest_utils import VersionComparator


def test_version_normalization():
    """测试版本号标准化功能"""
    print("🧪 测试版本号标准化...")
    
    test_cases = [
        ("0.8.0-snapshot.1", "0.8.0"),
        ("0.8.0-snapshot.2", "0.8.0"),
        ("0.8.0", "0.8.0"),
        ("0.9.0-snapshot.1", "0.9.0"),
        ("1.0.0", "1.0.0"),
        ("2.1", "2.1.0"),
        ("3", "3.0.0"),
        ("", "0.0.0"),
        ("invalid", "0.0.0"),
    ]
    
    for input_version, expected in test_cases:
        result = VersionComparator.normalize_version(input_version)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {input_version} -> {result} (期望: {expected})")


def test_version_comparison():
    """测试版本号比较功能"""
    print("\n🧪 测试版本号比较...")
    
    test_cases = [
        ("0.8.0", "0.9.0", -1),  # 0.8.0 < 0.9.0
        ("0.9.0", "0.8.0", 1),   # 0.9.0 > 0.8.0
        ("1.0.0", "1.0.0", 0),   # 1.0.0 == 1.0.0
        ("0.8.0-snapshot.1", "0.8.0", 0),  # 标准化后相等
        ("1.2.3", "1.2.4", -1), # 1.2.3 < 1.2.4
        ("2.0.0", "1.9.9", 1),   # 2.0.0 > 1.9.9
    ]
    
    for v1, v2, expected in test_cases:
        result = VersionComparator.compare_versions(v1, v2)
        status = "✅" if result == expected else "❌"
        comparison = "<" if expected == -1 else ">" if expected == 1 else "=="
        print(f"  {status} {v1} {comparison} {v2} (结果: {result})")


def test_version_range_check():
    """测试版本范围检查功能"""
    print("\n🧪 测试版本范围检查...")
    
    test_cases = [
        ("0.8.0", "0.7.0", "0.9.0", True),   # 在范围内
        ("0.6.0", "0.7.0", "0.9.0", False),  # 低于最小版本
        ("1.0.0", "0.7.0", "0.9.0", False),  # 高于最大版本
        ("0.8.0", "0.8.0", "0.8.0", True),   # 等于边界
        ("0.8.0", "", "0.9.0", True),        # 只有最大版本限制
        ("0.8.0", "0.7.0", "", True),        # 只有最小版本限制
        ("0.8.0", "", "", True),             # 无版本限制
    ]
    
    for version, min_ver, max_ver, expected in test_cases:
        is_compatible, error_msg = VersionComparator.is_version_in_range(version, min_ver, max_ver)
        status = "✅" if is_compatible == expected else "❌"
        range_str = f"[{min_ver or '无限制'}, {max_ver or '无限制'}]"
        print(f"  {status} {version} 在范围 {range_str}: {is_compatible}")
        if error_msg:
            print(f"      错误信息: {error_msg}")


def test_current_version():
    """测试获取当前版本功能"""
    print("\n🧪 测试获取当前主机版本...")
    
    try:
        current_version = VersionComparator.get_current_host_version()
        print(f"  ✅ 当前主机版本: {current_version}")
        
        # 验证版本号格式
        parts = current_version.split('.')
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            print(f"  ✅ 版本号格式正确")
        else:
            print(f"  ❌ 版本号格式错误")
            
    except Exception as e:
        print(f"  ❌ 获取当前版本失败: {e}")


def test_manifest_compatibility():
    """测试manifest兼容性检查"""
    print("\n🧪 测试manifest兼容性检查...")
    
    # 模拟manifest数据
    test_manifests = [
        {
            "name": "兼容插件",
            "host_application": {
                "min_version": "0.1.0",
                "max_version": "2.0.0"
            }
        },
        {
            "name": "版本过高插件",
            "host_application": {
                "min_version": "10.0.0",
                "max_version": "20.0.0"
            }
        },
        {
            "name": "版本过低插件",
            "host_application": {
                "min_version": "0.1.0",
                "max_version": "0.2.0"
            }
        },
        {
            "name": "无版本要求插件",
            # 没有host_application字段
        }
    ]
    
    # 这里需要导入PluginManager来测试，但可能会有依赖问题
    # 所以我们直接使用VersionComparator进行测试
    current_version = VersionComparator.get_current_host_version()
    
    for manifest in test_manifests:
        plugin_name = manifest["name"]
        
        if "host_application" in manifest:
            host_app = manifest["host_application"]
            min_version = host_app.get("min_version", "")
            max_version = host_app.get("max_version", "")
            
            is_compatible, error_msg = VersionComparator.is_version_in_range(
                current_version, min_version, max_version
            )
            
            status = "✅" if is_compatible else "❌"
            print(f"  {status} {plugin_name}: {is_compatible}")
            if error_msg:
                print(f"      {error_msg}")
        else:
            print(f"  ✅ {plugin_name}: True (无版本要求)")


def test_additional_snapshot_formats():
    """测试额外的snapshot版本格式"""
    print("\n🧪 测试额外的snapshot版本格式...")
    
    test_cases = [
        # 用户提到的版本格式
        ("0.8.0-snapshot.1", "0.8.0"),
        ("0.8.0-snapshot.2", "0.8.0"),
        ("0.8.0", "0.8.0"),
        ("0.9.0-snapshot.1", "0.9.0"),
        
        # 边界情况
        ("1.0.0-snapshot.999", "1.0.0"),
        ("2.15.3-snapshot.42", "2.15.3"),
        ("10.5.0-snapshot.1", "10.5.0"),
          # 不正确的snapshot格式（应该被忽略或正确处理）
        ("0.8.0-snapshot", "0.0.0"),  # 无数字后缀，应该标准化为0.0.0
        ("0.8.0-snapshot.abc", "0.0.0"),  # 非数字后缀，应该标准化为0.0.0
        ("0.8.0-beta.1", "0.0.0"),  # 其他预发布版本，应该标准化为0.0.0
    ]
    
    for input_version, expected in test_cases:
        result = VersionComparator.normalize_version(input_version)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {input_version} -> {result} (期望: {expected})")


def test_snapshot_version_comparison():
    """测试snapshot版本的比较功能"""
    print("\n🧪 测试snapshot版本比较...")
    
    test_cases = [
        # snapshot版本与正式版本比较
        ("0.8.0-snapshot.1", "0.8.0", 0),   # 应该相等
        ("0.8.0-snapshot.2", "0.8.0", 0),   # 应该相等
        ("0.9.0-snapshot.1", "0.8.0", 1),   # 应该大于
        ("0.7.0-snapshot.1", "0.8.0", -1),  # 应该小于
        
        # snapshot版本之间比较
        ("0.8.0-snapshot.1", "0.8.0-snapshot.2", 0),  # 都标准化为0.8.0，相等
        ("0.9.0-snapshot.1", "0.8.0-snapshot.1", 1),  # 0.9.0 > 0.8.0
        
        # 边界情况
        ("1.0.0-snapshot.1", "0.9.9", 1),    # 主版本更高
        ("0.9.0-snapshot.1", "0.8.99", 1),   # 次版本更高
    ]
    
    for version1, version2, expected in test_cases:
        result = VersionComparator.compare_versions(version1, version2)
        status = "✅" if result == expected else "❌"
        comparison = "<" if expected < 0 else "==" if expected == 0 else ">"
        print(f"  {status} {version1} {comparison} {version2} (结果: {result})")


def main():
    """主函数"""
    print("🔧 MaiBot插件版本兼容性检查测试")
    print("=" * 50)
    
    try:
        test_version_normalization()
        test_version_comparison()
        test_version_range_check()
        test_current_version()
        test_manifest_compatibility()
        test_additional_snapshot_formats()
        test_snapshot_version_comparison()
        
        print("\n🎉 所有测试完成！")
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

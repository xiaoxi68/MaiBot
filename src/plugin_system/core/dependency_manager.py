"""
插件依赖管理器

负责检查和安装插件的Python包依赖
"""

import subprocess
import sys
import importlib
from typing import List, Dict, Tuple, Optional
from pathlib import Path

from src.common.logger import get_logger
from src.plugin_system.base.component_types import PythonDependency

logger = get_logger("dependency_manager")


class DependencyManager:
    """依赖管理器"""

    def __init__(self):
        self.install_log: List[str] = []
        self.failed_installs: Dict[str, str] = {}
    
    def check_dependencies(self, dependencies: List[PythonDependency]) -> Tuple[List[PythonDependency], List[PythonDependency]]:
        """检查依赖包状态
        
        Args:
            dependencies: 依赖包列表
            
        Returns:
            Tuple[List[PythonDependency], List[PythonDependency]]: (缺失的依赖, 可选缺失的依赖)
        """
        missing_required = []
        missing_optional = []
        
        for dep in dependencies:
            if not self._is_package_available(dep.package_name):
                if dep.optional:
                    missing_optional.append(dep)
                    logger.warning(f"可选依赖包缺失: {dep.package_name} - {dep.description}")
                else:
                    missing_required.append(dep)
                    logger.error(f"必需依赖包缺失: {dep.package_name} - {dep.description}")
            else:
                logger.debug(f"依赖包已存在: {dep.package_name}")
        
        return missing_required, missing_optional
    
    def _is_package_available(self, package_name: str) -> bool:
        """检查包是否可用"""
        try:
            importlib.import_module(package_name)
            return True
        except ImportError:
            return False
    
    def install_dependencies(self, dependencies: List[PythonDependency], auto_install: bool = False) -> bool:
        """安装依赖包
        
        Args:
            dependencies: 需要安装的依赖包列表
            auto_install: 是否自动安装（True时不询问用户）
            
        Returns:
            bool: 安装是否成功
        """
        if not dependencies:
            return True
        
        logger.info(f"需要安装 {len(dependencies)} 个依赖包")
        
        # 显示将要安装的包
        for dep in dependencies:
            install_cmd = dep.get_pip_requirement()
            logger.info(f"  - {install_cmd} {'(可选)' if dep.optional else '(必需)'}")
            if dep.description:
                logger.info(f"    说明: {dep.description}")
        
        if not auto_install:
            # 这里可以添加用户确认逻辑
            logger.warning("手动安装模式：请手动运行 pip install 命令安装依赖包")
            return False
        
        # 执行安装
        success_count = 0
        for dep in dependencies:
            if self._install_single_package(dep):
                success_count += 1
            else:
                self.failed_installs[dep.package_name] = f"安装失败: {dep.get_pip_requirement()}"
        
        logger.info(f"依赖安装完成: {success_count}/{len(dependencies)} 个成功")
        return success_count == len(dependencies)
    
    def _install_single_package(self, dependency: PythonDependency) -> bool:
        """安装单个包"""
        pip_requirement = dependency.get_pip_requirement()
        
        try:
            logger.info(f"正在安装: {pip_requirement}")
            
            # 使用subprocess安装包
            cmd = [sys.executable, "-m", "pip", "install", pip_requirement]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode == 0:
                logger.info(f"✅ 成功安装: {pip_requirement}")
                self.install_log.append(f"成功安装: {pip_requirement}")
                return True
            else:
                logger.error(f"❌ 安装失败: {pip_requirement}")
                logger.error(f"错误输出: {result.stderr}")
                self.install_log.append(f"安装失败: {pip_requirement} - {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"❌ 安装超时: {pip_requirement}")
            return False
        except Exception as e:
            logger.error(f"❌ 安装异常: {pip_requirement} - {str(e)}")
            return False
    
    def generate_requirements_file(self, plugins_dependencies: List[List[PythonDependency]], 
                                 output_path: str = "plugin_requirements.txt") -> bool:
        """生成插件依赖的requirements文件
        
        Args:
            plugins_dependencies: 所有插件的依赖列表
            output_path: 输出文件路径
            
        Returns:
            bool: 生成是否成功
        """
        try:
            all_deps = {}
            
            # 合并所有插件的依赖
            for plugin_deps in plugins_dependencies:
                for dep in plugin_deps:
                    key = dep.install_name
                    if key in all_deps:
                        # 如果已存在，可以添加版本兼容性检查逻辑
                        existing = all_deps[key]
                        if dep.version and existing.version != dep.version:
                            logger.warning(f"依赖版本冲突: {key} ({existing.version} vs {dep.version})")
                    else:
                        all_deps[key] = dep
            
            # 写入requirements文件
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("# 插件依赖包自动生成\n")
                f.write("# Auto-generated plugin dependencies\n\n")
                
                # 按包名排序
                sorted_deps = sorted(all_deps.values(), key=lambda x: x.install_name)
                
                for dep in sorted_deps:
                    requirement = dep.get_pip_requirement()
                    if dep.description:
                        f.write(f"# {dep.description}\n")
                    if dep.optional:
                        f.write(f"# Optional dependency\n")
                    f.write(f"{requirement}\n\n")
            
            logger.info(f"已生成插件依赖文件: {output_path} ({len(all_deps)} 个包)")
            return True
            
        except Exception as e:
            logger.error(f"生成requirements文件失败: {str(e)}")
            return False
    
    def get_install_summary(self) -> Dict[str, any]:
        """获取安装摘要"""
        return {
            "install_log": self.install_log.copy(),
            "failed_installs": self.failed_installs.copy(),
            "total_attempts": len(self.install_log),
            "failed_count": len(self.failed_installs)
        }


# 全局依赖管理器实例
dependency_manager = DependencyManager() 
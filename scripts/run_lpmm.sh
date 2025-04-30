#!/bin/sh

# ==============================================
# 环境初始化：确保Python脚本在正确的目录下运行
# ==============================================

# Step 1: 自动定位项目根目录（即 scripts 目录的上级目录）
SCRIPTS_DIR="scripts"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

# Step 2: 检查 scripts 目录是否存在
if [ ! -d "$PROJECT_ROOT/$SCRIPTS_DIR" ]; then
    echo "❌ 错误：项目根目录中找不到 scripts 目录" >&2
    echo "当前路径: $PROJECT_ROOT" >&2
    exit 1
fi

# Step 3: 设置Python运行环境
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"  # 将项目根目录加入Python路径
cd "$PROJECT_ROOT" || {
    echo "❌ 无法切换到项目根目录: $PROJECT_ROOT" >&2
    exit 1
}

# Step 4: 打印关键路径信息（调试用）
echo "============================"
echo "项目根目录: $PROJECT_ROOT"
echo "Python路径: $PYTHONPATH"
echo "当前工作目录: $(pwd)"
echo "============================"

# ==============================================
# 执行Python脚本
# ==============================================

run_python_script() {
    local script_name=$1
    echo "🔄 正在运行 $script_name"
    python3 "scripts/$script_name"
    if [ $? -ne 0 ]; then
        echo "❌ $script_name 执行失败" >&2
        exit 1
    fi
}

# 按顺序运行脚本
run_python_script "raw_data_preprocessor.py"
run_python_script "info_extraction.py"
run_python_script "import_openie.py"

echo "✅ 所有脚本执行完成"
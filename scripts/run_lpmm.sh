#!/bin/sh

# Step 1: 自动定位项目根目录（即 scripts 目录的上级目录）
SCRIPTS_DIR="scripts"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

# Step 2: 检查 scripts 目录是否存在
if [ ! -d "$PROJECT_ROOT/$SCRIPTS_DIR" ]; then
    echo "❌ 错误：项目根目录中找不到 scripts 目录" >&2
    echo "当前路径: $SCRIPT_DIR" >&2
    exit 1
fi

# Step 3: 切换到项目根目录
cd "$PROJECT_ROOT" || {
    echo "❌ 无法切换到项目根目录: $PROJECT_ROOT" >&2
    exit 1
}

# Step 4: 运行每个 Python 脚本并检查退出状态
echo "🔄 正在运行 text_pre_process.py"
python3 scripts/text_pre_process.py
if [ $? -ne 0 ]; then
    echo "❌ text_pre_process.py 执行失败" >&2
    exit 1
fi

echo "🔄 正在运行 info_extraction.py"
python3 scripts/info_extraction.py
if [ $? -ne 0 ]; then
    echo "❌ info_extraction.py 执行失败" >&2
    exit 1
fi

echo "🔄 正在运行 import_openie.py"
python3 scripts/import_openie.py
if [ $? -ne 0 ]; then
    echo "❌ import_openie.py 执行失败" >&2
    exit 1
fi

echo "✅ 所有脚本执行完成"
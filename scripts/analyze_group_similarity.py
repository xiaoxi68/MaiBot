import json
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import matplotlib.pyplot as plt
import seaborn as sns
import sqlite3

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]  # 使用微软雅黑
plt.rcParams["axes.unicode_minus"] = False  # 用来正常显示负号
plt.rcParams["font.family"] = "sans-serif"

# 获取脚本所在目录
SCRIPT_DIR = Path(__file__).parent


def get_group_name(stream_id):
    """从数据库中获取群组名称"""
    conn = sqlite3.connect("data/maibot.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT group_name, user_nickname, platform 
        FROM chat_streams 
        WHERE stream_id = ?
    """,
        (stream_id,),
    )

    result = cursor.fetchone()
    conn.close()

    if result:
        group_name, user_nickname, platform = result
        if group_name:
            return group_name
        if user_nickname:
            return user_nickname
        if platform:
            return f"{platform}-{stream_id[:8]}"
    return stream_id


def load_group_data(group_dir):
    """加载单个群组的数据"""
    json_path = Path(group_dir) / "expressions.json"
    if not json_path.exists():
        return [], [], [], 0

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    situations = []
    styles = []
    combined = []
    total_count = sum(item["count"] for item in data)

    for item in data:
        count = item["count"]
        situations.extend([item["situation"]] * int(count))
        styles.extend([item["style"]] * int(count))
        combined.extend([f"{item['situation']} {item['style']}"] * int(count))

    return situations, styles, combined, total_count


def analyze_group_similarity():
    # 获取所有群组目录
    base_dir = Path("data/expression/learnt_style")
    group_dirs = [d for d in base_dir.iterdir() if d.is_dir()]

    # 加载所有群组的数据并过滤
    valid_groups = []
    valid_names = []
    valid_situations = []
    valid_styles = []
    valid_combined = []

    for d in group_dirs:
        situations, styles, combined, total_count = load_group_data(d)
        if total_count >= 50:  # 只保留数据量大于等于50的群组
            valid_groups.append(d)
            valid_names.append(get_group_name(d.name))
            valid_situations.append(" ".join(situations))
            valid_styles.append(" ".join(styles))
            valid_combined.append(" ".join(combined))

    if not valid_groups:
        print("没有找到数据量大于等于50的群组")
        return

    # 创建TF-IDF向量化器
    vectorizer = TfidfVectorizer()

    # 计算三种相似度矩阵
    situation_matrix = cosine_similarity(vectorizer.fit_transform(valid_situations))
    style_matrix = cosine_similarity(vectorizer.fit_transform(valid_styles))
    combined_matrix = cosine_similarity(vectorizer.fit_transform(valid_combined))

    # 对相似度矩阵进行对数变换
    log_situation_matrix = np.log10(situation_matrix * 100 + 1) * 10 / np.log10(4)
    log_style_matrix = np.log10(style_matrix * 100 + 1) * 10 / np.log10(4)
    log_combined_matrix = np.log10(combined_matrix * 100 + 1) * 10 / np.log10(4)

    # 创建一个大图，包含三个子图
    plt.figure(figsize=(45, 12))

    # 场景相似度热力图
    plt.subplot(1, 3, 1)
    sns.heatmap(
        log_situation_matrix,
        xticklabels=valid_names,
        yticklabels=valid_names,
        cmap="YlOrRd",
        annot=True,
        fmt=".1f",
        vmin=0,
        vmax=30,
    )
    plt.title("群组场景相似度热力图 (对数百分比)")
    plt.xticks(rotation=45, ha="right")

    # 表达方式相似度热力图
    plt.subplot(1, 3, 2)
    sns.heatmap(
        log_style_matrix,
        xticklabels=valid_names,
        yticklabels=valid_names,
        cmap="YlOrRd",
        annot=True,
        fmt=".1f",
        vmin=0,
        vmax=30,
    )
    plt.title("群组表达方式相似度热力图 (对数百分比)")
    plt.xticks(rotation=45, ha="right")

    # 组合相似度热力图
    plt.subplot(1, 3, 3)
    sns.heatmap(
        log_combined_matrix,
        xticklabels=valid_names,
        yticklabels=valid_names,
        cmap="YlOrRd",
        annot=True,
        fmt=".1f",
        vmin=0,
        vmax=30,
    )
    plt.title("群组场景+表达方式相似度热力图 (对数百分比)")
    plt.xticks(rotation=45, ha="right")

    plt.tight_layout()
    plt.savefig(SCRIPT_DIR / "group_similarity_heatmaps.png", dpi=300, bbox_inches="tight")
    plt.close()

    # 保存匹配详情到文本文件
    with open(SCRIPT_DIR / "group_similarity_details.txt", "w", encoding="utf-8") as f:
        f.write("群组相似度详情\n")
        f.write("=" * 50 + "\n\n")

        for i in range(len(valid_names)):
            for j in range(i + 1, len(valid_names)):
                if log_combined_matrix[i][j] > 50:
                    f.write(f"群组1: {valid_names[i]}\n")
                    f.write(f"群组2: {valid_names[j]}\n")
                    f.write(f"场景相似度: {situation_matrix[i][j]:.4f}\n")
                    f.write(f"表达方式相似度: {style_matrix[i][j]:.4f}\n")
                    f.write(f"组合相似度: {combined_matrix[i][j]:.4f}\n")

                    # 获取两个群组的数据
                    situations1, styles1, _ = load_group_data(valid_groups[i])
                    situations2, styles2, _ = load_group_data(valid_groups[j])

                    # 找出共同的场景
                    common_situations = set(situations1) & set(situations2)
                    if common_situations:
                        f.write("\n共同场景:\n")
                        for situation in common_situations:
                            f.write(f"- {situation}\n")

                    # 找出共同的表达方式
                    common_styles = set(styles1) & set(styles2)
                    if common_styles:
                        f.write("\n共同表达方式:\n")
                        for style in common_styles:
                            f.write(f"- {style}\n")

                    f.write("\n" + "-" * 50 + "\n\n")


if __name__ == "__main__":
    analyze_group_similarity()


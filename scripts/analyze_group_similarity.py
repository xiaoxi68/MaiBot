import json
import os
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import matplotlib.pyplot as plt
import seaborn as sns
import networkx as nx
import matplotlib as mpl
import sqlite3

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']  # 使用微软雅黑
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号
plt.rcParams['font.family'] = 'sans-serif'

# 获取脚本所在目录
SCRIPT_DIR = Path(__file__).parent

def get_group_name(stream_id):
    """从数据库中获取群组名称"""
    conn = sqlite3.connect('data/maibot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT group_name, user_nickname, platform 
        FROM chat_streams 
        WHERE stream_id = ?
    ''', (stream_id,))
    
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

def load_group_expressions(group_dir):
    """加载单个群组的表达方式数据"""
    json_path = Path(group_dir) / "expressions.json"
    if not json_path.exists():
        return []
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 将所有表达方式合并成一个文本
    all_expressions = []
    for item in data:
        all_expressions.extend([item['style']] * item['count'])
    
    return ' '.join(all_expressions)

def analyze_group_similarity():
    # 获取所有群组目录
    base_dir = Path("data/expression/learnt_style")
    group_dirs = [d for d in base_dir.iterdir() if d.is_dir()]
    group_ids = [d.name for d in group_dirs]
    
    # 获取群组名称
    group_names = [get_group_name(group_id) for group_id in group_ids]
    
    # 加载所有群组的表达方式
    group_texts = [load_group_expressions(d) for d in group_dirs]
    
    # 使用TF-IDF向量化文本
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(group_texts)
    
    # 计算余弦相似度
    similarity_matrix = cosine_similarity(tfidf_matrix)
    
    # 对相似度矩阵进行对数变换
    log_similarity_matrix = np.log1p(similarity_matrix)
    
    # 创建热力图
    plt.figure(figsize=(15, 12))
    sns.heatmap(log_similarity_matrix, 
                xticklabels=group_names,
                yticklabels=group_names,
                cmap='YlOrRd',
                annot=True,
                fmt='.2f',
                vmin=0,
                vmax=np.log1p(0.2))  # 调整最大值以匹配对数变换
    plt.title('群组表达方式相似度热力图 (对数变换)')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(SCRIPT_DIR / 'group_similarity_heatmap.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 创建网络图
    G = nx.Graph()
    
    # 添加节点
    for group_id, group_name in zip(group_ids, group_names):
        G.add_node(group_id, label=group_name)
    
    # 添加边（使用对数变换后的相似度）
    for i in range(len(group_ids)):
        for j in range(i+1, len(group_ids)):
            if log_similarity_matrix[i][j] > np.log1p(0.05):  # 调整阈值
                G.add_edge(group_ids[i], group_ids[j], 
                          weight=log_similarity_matrix[i][j])
    
    # 绘制网络图
    plt.figure(figsize=(20, 20))
    pos = nx.spring_layout(G, k=1, iterations=50)
    
    # 绘制节点
    nx.draw_networkx_nodes(G, pos, node_size=20000, node_color='lightblue', alpha=0.8)
    
    # 绘制边
    edges = G.edges()
    weights = [G[u][v]['weight'] * 40 for u, v in edges]  # 增加线条粗细系数
    nx.draw_networkx_edges(G, pos, width=weights, alpha=0.6, edge_color='gray')
    
    # 添加标签
    labels = {node: G.nodes[node]['label'] for node in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels, font_size=20, font_weight='bold')
    
    plt.title('群组表达方式相似度网络图\n(连线粗细表示对数变换后的相似度)')
    plt.axis('off')
    plt.tight_layout()
    plt.savefig(SCRIPT_DIR / 'group_similarity_network.png', dpi=300, bbox_inches='tight')
    plt.close()

if __name__ == "__main__":
    analyze_group_similarity()

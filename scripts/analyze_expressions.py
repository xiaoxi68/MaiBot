import os
import json
import time
import re
from datetime import datetime
from typing import Dict, List, Any
import pandas as pd
from pathlib import Path
import sqlite3

def clean_group_name(name: str) -> str:
    """清理群组名称，只保留中文和英文字符"""
    # 提取中文和英文字符
    cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', name)
    # 如果清理后为空，使用当前日期
    if not cleaned:
        cleaned = datetime.now().strftime("%Y%m%d")
    return cleaned

def get_group_name(stream_id: str) -> str:
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
            return clean_group_name(group_name)
        if user_nickname:
            return clean_group_name(user_nickname)
        if platform:
            return clean_group_name(f"{platform}{stream_id[:8]}")
    return stream_id

def load_expressions(chat_id: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """加载指定群组的表达方式"""
    learnt_style_file = os.path.join("data", "expression", "learnt_style", str(chat_id), "expressions.json")
    learnt_grammar_file = os.path.join("data", "expression", "learnt_grammar", str(chat_id), "expressions.json")
    personality_file = os.path.join("data", "expression", "personality", "expressions.json")
    
    style_expressions = []
    grammar_expressions = []
    personality_expressions = []
    
    if os.path.exists(learnt_style_file):
        with open(learnt_style_file, "r", encoding="utf-8") as f:
            style_expressions = json.load(f)
    
    if os.path.exists(learnt_grammar_file):
        with open(learnt_grammar_file, "r", encoding="utf-8") as f:
            grammar_expressions = json.load(f)
            
    if os.path.exists(personality_file):
        with open(personality_file, "r", encoding="utf-8") as f:
            personality_expressions = json.load(f)
    
    return style_expressions, grammar_expressions, personality_expressions

def format_time(timestamp: float) -> str:
    """格式化时间戳为可读字符串"""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

def write_expressions(f, expressions: List[Dict[str, Any]], title: str):
    """写入表达方式列表"""
    if not expressions:
        f.write(f"{title}：暂无数据\n")
        f.write("-" * 40 + "\n")
        return
    
    f.write(f"{title}：\n")
    for expr in expressions:
        count = expr.get("count", 0)
        last_active = expr.get("last_active_time", time.time())
        f.write(f"场景: {expr['situation']}\n")
        f.write(f"表达: {expr['style']}\n")
        f.write(f"计数: {count:.2f}\n")
        f.write(f"最后活跃: {format_time(last_active)}\n")
        f.write("-" * 40 + "\n")

def write_group_report(group_file: str, group_name: str, chat_id: str, style_exprs: List[Dict[str, Any]], grammar_exprs: List[Dict[str, Any]]):
    """写入群组详细报告"""
    with open(group_file, "w", encoding="utf-8") as gf:
        gf.write(f"群组: {group_name} (ID: {chat_id})\n")
        gf.write("=" * 80 + "\n\n")
        
        # 写入语言风格
        gf.write("【语言风格】\n")
        gf.write("=" * 40 + "\n")
        write_expressions(gf, style_exprs, "语言风格")
        gf.write("\n")
        
        # 写入句法特点
        gf.write("【句法特点】\n")
        gf.write("=" * 40 + "\n")
        write_expressions(gf, grammar_exprs, "句法特点")

def analyze_expressions():
    """分析所有群组的表达方式"""
    # 获取所有群组ID
    style_dir = os.path.join("data", "expression", "learnt_style")
    chat_ids = [d for d in os.listdir(style_dir) if os.path.isdir(os.path.join(style_dir, d))]
    
    # 创建输出目录
    output_dir = "data/expression_analysis"
    personality_dir = os.path.join(output_dir, "personality")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(personality_dir, exist_ok=True)
    
    # 生成时间戳
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 创建总报告
    summary_file = os.path.join(output_dir, f"summary_{timestamp}.txt")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"表达方式分析报告 - 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        # 先处理人格表达
        personality_exprs = []
        personality_file = os.path.join("data", "expression", "personality", "expressions.json")
        if os.path.exists(personality_file):
            with open(personality_file, "r", encoding="utf-8") as pf:
                personality_exprs = json.load(pf)
        
        # 保存人格表达总数
        total_personality = len(personality_exprs)
        
        # 排序并取前20条
        personality_exprs.sort(key=lambda x: x.get("count", 0), reverse=True)
        personality_exprs = personality_exprs[:20]
        
        # 写入人格表达报告
        personality_report = os.path.join(personality_dir, f"expressions_{timestamp}.txt")
        with open(personality_report, "w", encoding="utf-8") as pf:
            pf.write("【人格表达方式】\n")
            pf.write("=" * 40 + "\n")
            write_expressions(pf, personality_exprs, "人格表达")
        
        # 写入总报告摘要中的人格表达部分
        f.write("【人格表达方式】\n")
        f.write("=" * 40 + "\n")
        f.write(f"人格表达总数: {total_personality} (显示前20条)\n")
        f.write(f"详细报告: {personality_report}\n")
        f.write("-" * 40 + "\n\n")
        
        # 处理各个群组的表达方式
        f.write("【群组表达方式】\n")
        f.write("=" * 40 + "\n\n")
        
        for chat_id in chat_ids:
            style_exprs, grammar_exprs, _ = load_expressions(chat_id)
            
            # 保存总数
            total_style = len(style_exprs)
            total_grammar = len(grammar_exprs)
            
            # 分别排序
            style_exprs.sort(key=lambda x: x.get("count", 0), reverse=True)
            grammar_exprs.sort(key=lambda x: x.get("count", 0), reverse=True)
            
            # 只取前20条
            style_exprs = style_exprs[:20]
            grammar_exprs = grammar_exprs[:20]
            
            # 获取群组名称
            group_name = get_group_name(chat_id)
            
            # 创建群组子目录（使用清理后的名称）
            safe_group_name = clean_group_name(group_name)
            group_dir = os.path.join(output_dir, f"{safe_group_name}_{chat_id}")
            os.makedirs(group_dir, exist_ok=True)
            
            # 写入群组详细报告
            group_file = os.path.join(group_dir, f"expressions_{timestamp}.txt")
            write_group_report(group_file, group_name, chat_id, style_exprs, grammar_exprs)
            
            # 写入总报告摘要
            f.write(f"群组: {group_name} (ID: {chat_id})\n")
            f.write("-" * 40 + "\n")
            f.write(f"语言风格总数: {total_style} (显示前20条)\n")
            f.write(f"句法特点总数: {total_grammar} (显示前20条)\n")
            f.write(f"详细报告: {group_file}\n")
            f.write("-" * 40 + "\n\n")
    
    print(f"分析报告已生成:")
    print(f"总报告: {summary_file}")
    print(f"人格表达报告: {personality_report}")
    print(f"各群组详细报告位于: {output_dir}")

if __name__ == "__main__":
    analyze_expressions() 
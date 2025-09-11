#!/usr/bin/env python3
"""
基于Embedding的兴趣度计算测试脚本
使用MaiBot-Core的EmbeddingStore计算兴趣描述与目标文本的关联度
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Dict, Tuple, Optional
import time
import json
import asyncio
from src.chat.knowledge.embedding_store import EmbeddingStore, cosine_similarity
from src.chat.knowledge.embedding_store import EMBEDDING_DATA_DIR_STR
from src.llm_models.utils_model import LLMRequest
from src.config.config import model_config


class InterestScorer:
    """基于Embedding的兴趣度计算器"""
    
    def __init__(self, namespace: str = "interest_test"):
        """初始化兴趣度计算器"""
        self.embedding_store = EmbeddingStore(namespace, EMBEDDING_DATA_DIR_STR)
        
    async def get_embedding(self, text: str) -> Tuple[Optional[List[float]], float]:
        """获取文本的嵌入向量"""
        start_time = time.time()
        try:
            # 直接使用异步方式获取嵌入
            from src.llm_models.utils_model import LLMRequest
            from src.config.config import model_config
            
            llm = LLMRequest(model_set=model_config.model_task_config.embedding, request_type="embedding")
            embedding, _ = await llm.get_embedding(text)
            
            end_time = time.time()
            elapsed = end_time - start_time
            
            if embedding and len(embedding) > 0:
                return embedding, elapsed
            return None, elapsed
        except Exception as e:
            print(f"获取嵌入向量失败: {e}")
            return None, 0.0
    
    async def calculate_similarity(self, text1: str, text2: str) -> Tuple[float, float, float]:
        """计算两段文本的余弦相似度，返回(相似度, 文本1耗时, 文本2耗时)"""
        emb1, time1 = await self.get_embedding(text1)
        emb2, time2 = await self.get_embedding(text2)
        
        if emb1 is None or emb2 is None:
            return 0.0, time1, time2
            
        return cosine_similarity(emb1, emb2), time1, time2
    
    async def calculate_interest_score(self, interest_text: str, target_text: str) -> Dict:
        """
        计算兴趣度分数
        
        Args:
            interest_text: 兴趣描述文本
            target_text: 目标文本
            
        Returns:
            包含各种分数的字典
        """
        # 只计算语义相似度（嵌入分数）
        semantic_score, interest_time, target_time = await self.calculate_similarity(interest_text, target_text)
        
        # 直接使用语义相似度作为最终分数
        final_score = semantic_score
        
        return {
            "final_score": final_score,
            "semantic_score": semantic_score,
            "timing": {
                "interest_embedding_time": interest_time,
                "target_embedding_time": target_time,
                "total_time": interest_time + target_time
            }
        }
    
    async def batch_calculate(self, interest_text: str, target_texts: List[str]) -> List[Dict]:
        """批量计算兴趣度"""
        results = []
        total_start_time = time.time()
        
        print(f"开始批量计算兴趣度...")
        print(f"兴趣文本: {interest_text}")
        print(f"目标文本数量: {len(target_texts)}")
        
        # 获取兴趣文本的嵌入向量（只需要一次）
        interest_embedding, interest_time = await self.get_embedding(interest_text)
        if interest_embedding is None:
            print("无法获取兴趣文本的嵌入向量")
            return []
        
        print(f"兴趣文本嵌入计算耗时: {interest_time:.3f}秒")
        
        total_target_time = 0.0
        
        for i, target_text in enumerate(target_texts):
            print(f"处理第 {i+1}/{len(target_texts)} 个文本...")
            
            # 获取目标文本的嵌入向量
            target_embedding, target_time = await self.get_embedding(target_text)
            total_target_time += target_time
            
            if target_embedding is None:
                semantic_score = 0.0
            else:
                semantic_score = cosine_similarity(interest_embedding, target_embedding)
            
            # 直接使用语义相似度作为最终分数
            final_score = semantic_score
            
            results.append({
                "target_text": target_text,
                "final_score": final_score,
                "semantic_score": semantic_score,
                "timing": {
                    "target_embedding_time": target_time,
                    "item_total_time": target_time
                }
            })
        
        # 按分数排序
        results.sort(key=lambda x: x["final_score"], reverse=True)
        
        total_time = time.time() - total_start_time
        avg_target_time = total_target_time / len(target_texts) if target_texts else 0
        
        print(f"\n=== 性能统计 ===")
        print(f"兴趣文本嵌入计算耗时: {interest_time:.3f}秒")
        print(f"目标文本嵌入计算总耗时: {total_target_time:.3f}秒")
        print(f"目标文本嵌入计算平均耗时: {avg_target_time:.3f}秒")
        print(f"总耗时: {total_time:.3f}秒")
        print(f"平均每个目标文本处理耗时: {total_time / len(target_texts):.3f}秒")
        
        return results

    async def generate_paraphrases(self, original_text: str, num_sentences: int = 5) -> List[str]:
        """
        使用LLM生成近义句子
        
        Args:
            original_text: 原始文本
            num_sentences: 生成句子数量
            
        Returns:
            近义句子列表
        """
        try:
            # 创建LLM请求实例
            llm_request = LLMRequest(
                model_set=model_config.model_task_config.replyer,
                request_type="paraphrase_generator"
            )
            
            # 构建生成近义句子的提示词
            prompt = f"""请为以下兴趣描述生成{num_sentences}个意义相近但表达不同的句子：

原始兴趣描述：{original_text}

要求：
1. 保持原意不变，但尽量自由发挥，使用不同的表达方式，内容也可以有差异
2. 句子结构要有所变化
3. 可以适当调整语气和重点
4. 每个句子都要完整且自然
5. 只返回句子，不要编号，每行一个句子

生成的近义句子："""
            
            print(f"正在生成近义句子...")
            content, (reasoning, model_name, tool_calls) = await llm_request.generate_response_async(prompt)
            
            # 解析生成的句子
            sentences = []
            for line in content.strip().split('\n'):
                line = line.strip()
                if line and not line.startswith('生成') and not line.startswith('近义'):
                    sentences.append(line)
            
            # 确保返回指定数量的句子
            sentences = sentences[:num_sentences]
            print(f"成功生成 {len(sentences)} 个近义句子")
            print(f"使用的模型: {model_name}")
            
            return sentences
            
        except Exception as e:
            print(f"生成近义句子失败: {e}")
            return []

    async def evaluate_all_paraphrases(self, original_text: str, target_texts: List[str], num_sentences: int = 5) -> Dict:
        """
        评估原始文本和所有近义句子的兴趣度
        
        Args:
            original_text: 原始兴趣描述文本
            target_texts: 目标文本列表
            num_sentences: 生成近义句子数量
            
        Returns:
            包含所有评估结果的字典
        """
        print(f"\n=== 开始近义句子兴趣度评估 ===")
        print(f"原始兴趣描述: {original_text}")
        print(f"目标文本数量: {len(target_texts)}")
        print(f"生成近义句子数量: {num_sentences}")
        
        # 生成近义句子
        paraphrases = await self.generate_paraphrases(original_text, num_sentences)
        if not paraphrases:
            print("生成近义句子失败，使用原始文本进行评估")
            paraphrases = []
        
        # 所有待评估的文本（原始文本 + 近义句子）
        all_texts = [original_text] + paraphrases
        
        # 对每个文本进行兴趣度评估
        evaluation_results = {}
        
        for i, text in enumerate(all_texts):
            text_type = "原始文本" if i == 0 else f"近义句子{i}"
            print(f"\n--- 评估 {text_type} ---")
            print(f"文本内容: {text}")
            
            # 计算兴趣度
            results = await self.batch_calculate(text, target_texts)
            evaluation_results[text_type] = {
                "text": text,
                "results": results,
                "top_score": results[0]["final_score"] if results else 0.0,
                "average_score": sum(r["final_score"] for r in results) / len(results) if results else 0.0
            }
        
        return {
            "original_text": original_text,
            "paraphrases": paraphrases,
            "evaluations": evaluation_results,
            "summary": self._generate_summary(evaluation_results, target_texts)
        }
    
    def _generate_summary(self, evaluation_results: Dict, target_texts: List[str]) -> Dict:
        """生成评估摘要 - 关注目标句子的表现"""
        summary = {
            "best_performer": None,
            "worst_performer": None,
            "average_scores": {},
            "max_scores": {},
            "rankings": [],
            "target_stats": {},
            "target_rankings": []
        }
        
        scores = []
        
        for text_type, data in evaluation_results.items():
            scores.append({
                "text_type": text_type,
                "text": data["text"],
                "top_score": data["top_score"],
                "average_score": data["average_score"]
            })
        
        # 按top_score排序
        scores.sort(key=lambda x: x["top_score"], reverse=True)
        
        summary["rankings"] = scores
        summary["best_performer"] = scores[0] if scores else None
        summary["worst_performer"] = scores[-1] if scores else None
        
        # 计算原始文本统计
        original_score = next((s for s in scores if s["text_type"] == "原始文本"), None)
        if original_score:
            summary["average_scores"]["original"] = original_score["average_score"]
            summary["max_scores"]["original"] = original_score["top_score"]
        
        # 计算目标句子的统计信息
        target_stats = {}
        for i, target_text in enumerate(target_texts):
            target_key = f"目标{i+1}"
            scores_for_target = []
            
            # 收集所有兴趣描述对该目标文本的分数
            for text_type, data in evaluation_results.items():
                for result in data["results"]:
                    if result["target_text"] == target_text:
                        scores_for_target.append(result["final_score"])
            
            if scores_for_target:
                target_stats[target_key] = {
                    "target_text": target_text,
                    "scores": scores_for_target,
                    "average": sum(scores_for_target) / len(scores_for_target),
                    "max": max(scores_for_target),
                    "min": min(scores_for_target),
                    "std": (sum((x - sum(scores_for_target) / len(scores_for_target)) ** 2 for x in scores_for_target) / len(scores_for_target)) ** 0.5
                }
        
        summary["target_stats"] = target_stats
        
        # 按平均分对目标文本排序
        target_rankings = []
        for target_key, stats in target_stats.items():
            target_rankings.append({
                "target_key": target_key,
                "target_text": stats["target_text"],
                "average_score": stats["average"],
                "max_score": stats["max"],
                "min_score": stats["min"],
                "std_score": stats["std"]
            })
        
        target_rankings.sort(key=lambda x: x["average_score"], reverse=True)
        summary["target_rankings"] = target_rankings
        
        # 计算目标文本的整体统计
        if target_rankings:
            all_target_averages = [t["average_score"] for t in target_rankings]
            all_target_scores = []
            for stats in target_stats.values():
                all_target_scores.extend(stats["scores"])
            
            summary["target_overall"] = {
                "avg_of_averages": sum(all_target_averages) / len(all_target_averages),
                "overall_max": max(all_target_scores),
                "overall_min": min(all_target_scores),
                "best_target": target_rankings[0]["target_text"],
                "worst_target": target_rankings[-1]["target_text"]
            }
        
        return summary


async def run_single_test():
    """运行单个测试"""
    print("单个兴趣度测试")
    print("=" * 40)
    
    # 输入兴趣文本
    # interest_text = input("请输入兴趣描述文本: ").strip()
    # if not interest_text:
    #     print("兴趣描述不能为空")
    #     return
    
    interest_text ="对技术相关话题，游戏和动漫相关话题感兴趣，也对日常话题感兴趣，不喜欢太过沉重严肃的话题"
    
    # 输入目标文本
    print("请输入目标文本 (输入空行结束):")
    import random
    target_texts = [
        "AveMujica非常好看，你看了吗",
        "明日方舟这个游戏挺好玩的",
        "你能不能说点正经的",
        "明日方舟挺好玩的",
        "你的名字非常好看，你看了吗",
        "《你的名字》非常好看，你看了吗",
        "我们来聊聊苏联政治吧",
        "轻音少女非常好看，你看了吗",
        "我还挺喜欢打游戏的",
        "我嘞个原神玩家啊",
        "我心买了PlayStation5",
        "直接Steam",
        "有没有R"
    ]
    random.shuffle(target_texts)
    # while True:
    #     line = input().strip()
    #     if not line:
    #         break
    #     target_texts.append(line)
    
    # if not target_texts:
    #     print("目标文本不能为空")
    #     return
    
    # 计算兴趣度
    scorer = InterestScorer()
    results = await scorer.batch_calculate(interest_text, target_texts)
    
    # 显示结果
    print(f"\n兴趣度排序结果:")
    print("-" * 80)
    print(f"{'排名':<4} {'最终分数':<10} {'语义分数':<10} {'耗时(秒)':<10} {'目标文本'}")
    print("-" * 80)
    
    for j, result in enumerate(results):
        target_text = result['target_text']
        if len(target_text) > 40:
            target_text = target_text[:37] + "..."
        
        timing = result.get('timing', {})
        item_time = timing.get('item_total_time', 0.0)
        
        print(f"{j+1:<4} {result['final_score']:<10.3f} {result['semantic_score']:<10.3f} "
              f"{item_time:<10.3f} {target_text}")


async def run_paraphrase_test():
    """运行近义句子测试"""
    print("近义句子兴趣度对比测试")
    print("=" * 40)
    
    # 输入兴趣文本
    interest_text = "对技术相关话题，游戏和动漫相关话题感兴趣，比如明日方舟和原神，也对日常话题感兴趣，不喜欢太过沉重严肃的话题"
    
    # 输入目标文本
    print("请输入目标文本 (输入空行结束):")
    # target_texts = []
    # while True:
    #     line = input().strip()
    #     if not line:
    #         break
    #     target_texts.append(line)
    target_texts = [
    "AveMujica非常好看，你看了吗",
    "明日方舟这个游戏挺好玩的",
    "你能不能说点正经的",
    "明日方舟挺好玩的",
    "你的名字非常好看，你看了吗",
    "《你的名字》非常好看，你看了吗",
    "我们来聊聊苏联政治吧",
    "轻音少女非常好看，你看了吗",
    "我还挺喜欢打游戏的",
    "刚加好友就视奸空间14条",
    "可乐老大加我好友，我先日一遍空间",
    "鸟一茬茬的",
    "可乐可以是m，群友可以是s"
    ]
    
    if not target_texts:
        print("目标文本不能为空")
        return
    
    # 创建评估器
    scorer = InterestScorer()
    
    # 运行评估
    result = await scorer.evaluate_all_paraphrases(interest_text, target_texts, num_sentences=5)
    
    # 显示结果
    display_paraphrase_results(result, target_texts)


def display_paraphrase_results(result: Dict, target_texts: List[str]):
    """显示近义句子评估结果"""
    print("\n" + "=" * 80)
    print("近义句子兴趣度评估结果")
    print("=" * 80)
    
    # 显示目标文本
    print(f"\n📋 目标文本列表:")
    print("-" * 40)
    for i, target in enumerate(target_texts):
        print(f"{i+1}. {target}")
    
    # 显示生成的近义句子
    print(f"\n📝 生成的近义句子 (作为兴趣描述):")
    print("-" * 40)
    for i, paraphrase in enumerate(result["paraphrases"]):
        print(f"{i+1}. {paraphrase}")
    
    # 显示摘要
    summary = result["summary"]
    print(f"\n📊 评估摘要:")
    print("-" * 40)
    
    if summary["best_performer"]:
        print(f"最佳表现: {summary['best_performer']['text_type']} (最高分: {summary['best_performer']['top_score']:.3f})")
    
    if summary["worst_performer"]:
        print(f"最差表现: {summary['worst_performer']['text_type']} (最高分: {summary['worst_performer']['top_score']:.3f})")
    
    print(f"原始文本平均分: {summary['average_scores'].get('original', 0):.3f}")
    
    # 显示目标文本的整体统计
    if "target_overall" in summary:
        overall = summary["target_overall"]
        print(f"\n📈 目标文本整体统计:")
        print("-" * 40)
        print(f"目标文本数量: {len(summary['target_rankings'])}")
        print(f"平均分的平均值: {overall['avg_of_averages']:.3f}")
        print(f"所有匹配中的最高分: {overall['overall_max']:.3f}")
        print(f"所有匹配中的最低分: {overall['overall_min']:.3f}")
        print(f"最佳匹配目标: {overall['best_target'][:50]}...")
        print(f"最差匹配目标: {overall['worst_target'][:50]}...")
    
    # 显示目标文本排名
    if "target_rankings" in summary and summary["target_rankings"]:
        print(f"\n🏆 目标文本排名 (按平均分):")
        print("-" * 80)
        print(f"{'排名':<4} {'平均分':<8} {'最高分':<8} {'最低分':<8} {'标准差':<8} {'目标文本'}")
        print("-" * 80)
        
        for i, target in enumerate(summary["target_rankings"]):
            target_text = target["target_text"][:40] + "..." if len(target["target_text"]) > 40 else target["target_text"]
            print(f"{i+1:<4} {target['average_score']:<8.3f} {target['max_score']:<8.3f} {target['min_score']:<8.3f} {target['std_score']:<8.3f} {target_text}")
    
    # 显示每个目标文本的详细分数分布
    if "target_stats" in summary:
        print(f"\n📊 目标文本详细分数分布:")
        print("-" * 80)
        
        for target_key, stats in summary["target_stats"].items():
            print(f"\n{target_key}: {stats['target_text']}")
            print(f"  平均分: {stats['average']:.3f}")
            print(f"  最高分: {stats['max']:.3f}")
            print(f"  最低分: {stats['min']:.3f}")
            print(f"  标准差: {stats['std']:.3f}")
            print(f"  所有分数: {[f'{s:.3f}' for s in stats['scores']]}")
    
    # 显示最佳和最差兴趣描述的目标表现对比
    if summary["best_performer"] and summary["worst_performer"]:
        print(f"\n🔍 最佳 vs 最差兴趣描述对比:")
        print("-" * 80)
        
        best_data = result["evaluations"][summary["best_performer"]["text_type"]]
        worst_data = result["evaluations"][summary["worst_performer"]["text_type"]]
        
        print(f"最佳兴趣描述: {summary['best_performer']['text']}")
        print(f"最差兴趣描述: {summary['worst_performer']['text']}")
        print(f"")
        print(f"{'目标文本':<30} {'最佳分数':<10} {'最差分数':<10} {'差值'}")
        print("-" * 60)
        
        for best_result, worst_result in zip(best_data["results"], worst_data["results"]):
            if best_result["target_text"] == worst_result["target_text"]:
                diff = best_result["final_score"] - worst_result["final_score"]
                target_text = best_result["target_text"][:27] + "..." if len(best_result["target_text"]) > 30 else best_result["target_text"]
                print(f"{target_text:<30} {best_result['final_score']:<10.3f} {worst_result['final_score']:<10.3f} {diff:+.3f}")
    
    # 显示排名
    print(f"\n🏆 兴趣描述性能排名:")
    print("-" * 80)
    print(f"{'排名':<4} {'文本类型':<10} {'最高分':<8} {'平均分':<8} {'兴趣描述内容'}")
    print("-" * 80)
    
    for i, item in enumerate(summary["rankings"]):
        text_content = item["text"][:40] + "..." if len(item["text"]) > 40 else item["text"]
        print(f"{i+1:<4} {item['text_type']:<10} {item['top_score']:<8.3f} {item['average_score']:<8.3f} {text_content}")
    
    # 显示每个兴趣描述的详细结果
    print(f"\n🔍 详细结果:")
    print("-" * 80)
    
    for text_type, data in result["evaluations"].items():
        print(f"\n--- {text_type} ---")
        print(f"兴趣描述: {data['text']}")
        print(f"最高分: {data['top_score']:.3f}")
        print(f"平均分: {data['average_score']:.3f}")
        
        # 显示前3个匹配结果
        top_results = data["results"][:3]
        print(f"前3个匹配的目标文本:")
        for j, result_item in enumerate(top_results):
            print(f"  {j+1}. 分数: {result_item['final_score']:.3f} - {result_item['target_text']}")
    
    # 显示对比表格
    print(f"\n📈 兴趣描述对比表格:")
    print("-" * 100)
    header = f"{'兴趣描述':<20}"
    for i, target in enumerate(target_texts):
        target_name = f"目标{i+1}"
        header += f" {target_name:<12}"
    print(header)
    print("-" * 100)
    
    # 原始文本行
    original_line = f"{'原始文本':<20}"
    original_data = result["evaluations"]["原始文本"]["results"]
    for i in range(len(target_texts)):
        if i < len(original_data):
            original_line += f" {original_data[i]['final_score']:<12.3f}"
        else:
            original_line += f" {'-':<12}"
    print(original_line)
    
    # 近义句子行
    for i, paraphrase in enumerate(result["paraphrases"]):
        text_type = f"近义句子{i+1}"
        line = f"{text_type:<20}"
        paraphrase_data = result["evaluations"][text_type]["results"]
        for j in range(len(target_texts)):
            if j < len(paraphrase_data):
                line += f" {paraphrase_data[j]['final_score']:<12.3f}"
            else:
                line += f" {'-':<12}"
        print(line)


def main():
    """主函数"""
    print("基于Embedding的兴趣度计算测试工具")
    print("1. 单个兴趣度测试")
    print("2. 近义句子兴趣度对比测试")
    
    choice = input("\n请选择 (1/2): ").strip()
    
    if choice == "1":
        asyncio.run(run_single_test())
    elif choice == "2":
        asyncio.run(run_paraphrase_test())
    else:
        print("无效选择")


if __name__ == "__main__":
    main()
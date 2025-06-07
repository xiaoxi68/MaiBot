import time
import unittest
import jieba
from difflib import SequenceMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def tfidf_similarity(s1, s2):
    """
    使用 TF-IDF 和余弦相似度计算两个句子的相似性。
    """
    # 1. 使用 jieba 进行分词
    s1_words = " ".join(jieba.cut(s1))
    s2_words = " ".join(jieba.cut(s2))
    
    # 2. 将两句话放入一个列表中
    corpus = [s1_words, s2_words]
    
    # 3. 创建 TF-IDF 向量化器并进行计算
    try:
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(corpus)
    except ValueError:
        # 如果句子完全由停用词组成，或者为空，可能会报错
        return 0.0

    # 4. 计算余弦相似度
    similarity_matrix = cosine_similarity(tfidf_matrix)
    
    # 返回 s1 和 s2 的相似度
    return similarity_matrix[0, 1]

def sequence_similarity(s1, s2):
    """
    使用 SequenceMatcher 计算两个句子的相似性。
    """
    return SequenceMatcher(None, s1, s2).ratio()

class TestSentenceSimilarity(unittest.TestCase):
    def test_similarity_comparison(self):
        """比较不同相似度计算方法的结果"""
        test_cases = [
            {
                "sentence1": "今天天气怎么样",
                "sentence2": "今天气候如何",
                "expected_similar": True
            },
            {
                "sentence1": "今天天气怎么样",
                "sentence2": "我今天要去吃麦当劳",
                "expected_similar": False
            },
            {
                "sentence1": "我今天要去吃麦当劳",
                "sentence2": "肯德基和麦当劳哪家好吃",
                "expected_similar": True
            },
            {
                "sentence1": "Vindemiatrix提到昨天三个无赖杀穿交界地",
                "sentence2": "Vindemiatrix昨天用三个无赖角色杀穿了游戏中的交界地",
                "expected_similar": True
            },
            {
                "sentence1": "tc_魔法士解释了之前templateinfo的with用法和现在的单独逻辑发送的区别",
                "sentence2": "tc_魔法士解释了templateinfo的用法，包括它是一个字典，key是prompt的名字，value是prompt的内容，格式是只支持大括号的fstring",
                "expected_similar": False
            },
            {
                "sentence1": "YXH_XianYu分享了一张舰娘街机游戏的图片，并提到'玩舰娘街机的董不懂'",
                "sentence2": "YXH_XianYu对街机游戏表现出兴趣，并分享了玩舰娘街机的经历",
                "expected_similar": True
            },
            {
                "sentence1": "YXH_XianYu在考虑入坑明日方舟，犹豫是否要从零开荒或使用初始号",
                "sentence2": "YXH_XianYu考虑入坑明日方舟，倾向于从零开荒或初始号开荒",
                "expected_similar": True
            },
            {
                "sentence1": "YXH_XianYu提到秋叶原好多人在玩maimai",
                "sentence2": "YXH_XianYu对学园偶像的付费石头机制表示惊讶",
                "expected_similar": False
            }
        ]

        print("\n相似度计算方法比较:")
        for i, case in enumerate(test_cases, 1):
            print(f"\n测试用例 {i}:")
            print(f"句子1: {case['sentence1']}")
            print(f"句子2: {case['sentence2']}")

            # TF-IDF 相似度
            start_time = time.time()
            tfidf_sim = tfidf_similarity(case['sentence1'], case['sentence2'])
            tfidf_time = time.time() - start_time

            # SequenceMatcher 相似度
            start_time = time.time()
            seq_sim = sequence_similarity(case['sentence1'], case['sentence2'])
            seq_time = time.time() - start_time

            print(f"TF-IDF相似度: {tfidf_sim:.4f} (耗时: {tfidf_time:.4f}秒)")
            print(f"SequenceMatcher相似度: {seq_sim:.4f} (耗时: {seq_time:.4f}秒)")

    def test_batch_processing(self):
        """测试批量处理性能"""
        sentences = [
            "人工智能正在改变世界",
            "AI技术发展迅速",
            "机器学习是人工智能的一个分支",
            "深度学习在图像识别领域取得了突破",
            "自然语言处理技术越来越成熟"
        ]

        print("\n批量处理测试:")
        
        # TF-IDF 批量处理
        start_time = time.time()
        tfidf_matrix = []
        for i in range(len(sentences)):
            row = []
            for j in range(len(sentences)):
                similarity = tfidf_similarity(sentences[i], sentences[j])
                row.append(similarity)
            tfidf_matrix.append(row)
        tfidf_time = time.time() - start_time

        # SequenceMatcher 批量处理
        start_time = time.time()
        seq_matrix = []
        for i in range(len(sentences)):
            row = []
            for j in range(len(sentences)):
                similarity = sequence_similarity(sentences[i], sentences[j])
                row.append(similarity)
            seq_matrix.append(row)
        seq_time = time.time() - start_time

        print(f"TF-IDF批量处理 {len(sentences)} 个句子耗时: {tfidf_time:.4f}秒")
        print(f"SequenceMatcher批量处理 {len(sentences)} 个句子耗时: {seq_time:.4f}秒")

        # 打印TF-IDF相似度矩阵
        print("\nTF-IDF相似度矩阵:")
        for row in tfidf_matrix:
            for similarity in row:
                print(f"{similarity:.4f}", end="\t")
            print()

        # 打印SequenceMatcher相似度矩阵
        print("\nSequenceMatcher相似度矩阵:")
        for row in seq_matrix:
            for similarity in row:
                print(f"{similarity:.4f}", end="\t")
            print()

if __name__ == '__main__':
    unittest.main(verbosity=2) 
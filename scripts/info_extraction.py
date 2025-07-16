import json
import os
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Event
import sys
import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# 添加项目根目录到 sys.path

from rich.progress import Progress  # 替换为 rich 进度条

from src.common.logger import get_logger
# from src.chat.knowledge.lpmmconfig import global_config
from src.chat.knowledge.ie_process import info_extract_from_str
from src.chat.knowledge.open_ie import OpenIE
from rich.progress import (
    BarColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TaskProgressColumn,
    MofNCompleteColumn,
    SpinnerColumn,
    TextColumn,
)
from raw_data_preprocessor import RAW_DATA_PATH, load_raw_data
from src.config.config import global_config
from src.llm_models.utils_model import LLMRequest
from dotenv import load_dotenv

logger = get_logger("LPMM知识库-信息提取")


ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMP_DIR = os.path.join(ROOT_PATH, "temp")
# IMPORTED_DATA_PATH = os.path.join(ROOT_PATH, "data", "imported_lpmm_data")
OPENIE_OUTPUT_DIR = os.path.join(ROOT_PATH, "data", "openie")
ENV_FILE = os.path.join(ROOT_PATH, ".env")

if os.path.exists(".env"):
    load_dotenv(".env", override=True)
    print("成功加载环境变量配置")
else:
    print("未找到.env文件，请确保程序所需的环境变量被正确设置")
    raise FileNotFoundError(".env 文件不存在，请创建并配置所需的环境变量")

env_mask = {key: os.getenv(key) for key in os.environ}
def scan_provider(env_config: dict):
    provider = {}

    # 利用未初始化 env 时获取的 env_mask 来对新的环境变量集去重
    # 避免 GPG_KEY 这样的变量干扰检查
    env_config = dict(filter(lambda item: item[0] not in env_mask, env_config.items()))

    # 遍历 env_config 的所有键
    for key in env_config:
        # 检查键是否符合 {provider}_BASE_URL 或 {provider}_KEY 的格式
        if key.endswith("_BASE_URL") or key.endswith("_KEY"):
            # 提取 provider 名称
            provider_name = key.split("_", 1)[0]  # 从左分割一次，取第一部分

            # 初始化 provider 的字典（如果尚未初始化）
            if provider_name not in provider:
                provider[provider_name] = {"url": None, "key": None}

            # 根据键的类型填充 url 或 key
            if key.endswith("_BASE_URL"):
                provider[provider_name]["url"] = env_config[key]
            elif key.endswith("_KEY"):
                provider[provider_name]["key"] = env_config[key]

    # 检查每个 provider 是否同时存在 url 和 key
    for provider_name, config in provider.items():
        if config["url"] is None or config["key"] is None:
            logger.error(f"provider 内容：{config}\nenv_config 内容：{env_config}")
            raise ValueError(f"请检查 '{provider_name}' 提供商配置是否丢失 BASE_URL 或 KEY 环境变量")

def ensure_dirs():
    """确保临时目录和输出目录存在"""
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)
        logger.info(f"已创建临时目录: {TEMP_DIR}")
    if not os.path.exists(OPENIE_OUTPUT_DIR):
        os.makedirs(OPENIE_OUTPUT_DIR)
        logger.info(f"已创建输出目录: {OPENIE_OUTPUT_DIR}")
    if not os.path.exists(RAW_DATA_PATH):
        os.makedirs(RAW_DATA_PATH)
        logger.info(f"已创建原始数据目录: {RAW_DATA_PATH}")

# 创建一个线程安全的锁，用于保护文件操作和共享数据
file_lock = Lock()
open_ie_doc_lock = Lock()

# 创建一个事件标志，用于控制程序终止
shutdown_event = Event()

lpmm_entity_extract_llm = LLMRequest(
    model=global_config.model.lpmm_entity_extract,
    request_type="lpmm.entity_extract"
)
lpmm_rdf_build_llm = LLMRequest(
    model=global_config.model.lpmm_rdf_build,
    request_type="lpmm.rdf_build"
)
def process_single_text(pg_hash, raw_data):
    """处理单个文本的函数，用于线程池"""
    temp_file_path = f"{TEMP_DIR}/{pg_hash}.json"

    # 使用文件锁检查和读取缓存文件
    with file_lock:
        if os.path.exists(temp_file_path):
            try:
                # 存在对应的提取结果
                logger.info(f"找到缓存的提取结果：{pg_hash}")
                with open(temp_file_path, "r", encoding="utf-8") as f:
                    return json.load(f), None
            except json.JSONDecodeError:
                # 如果JSON文件损坏，删除它并重新处理
                logger.warning(f"缓存文件损坏，重新处理：{pg_hash}")
                os.remove(temp_file_path)

    entity_list, rdf_triple_list = info_extract_from_str(
        lpmm_entity_extract_llm,
        lpmm_rdf_build_llm,
        raw_data,
    )
    if entity_list is None or rdf_triple_list is None:
        return None, pg_hash
    doc_item = {
        "idx": pg_hash,
        "passage": raw_data,
        "extracted_entities": entity_list,
        "extracted_triples": rdf_triple_list,
    }
    # 保存临时提取结果
    with file_lock:
        try:
            with open(temp_file_path, "w", encoding="utf-8") as f:
                json.dump(doc_item, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存缓存文件失败：{pg_hash}, 错误：{e}")
            # 如果保存失败，确保不会留下损坏的文件
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            sys.exit(0)
            return None, pg_hash
    return doc_item, None


def signal_handler(_signum, _frame):
    """处理Ctrl+C信号"""
    logger.info("\n接收到中断信号，正在优雅地关闭程序...")
    sys.exit(0)


def main():  # sourcery skip: comprehension-to-generator, extract-method
    # 设置信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    ensure_dirs()  # 确保目录存在
    env_config = {key: os.getenv(key) for key in os.environ}
    scan_provider(env_config)
    # 新增用户确认提示
    print("=== 重要操作确认，请认真阅读以下内容哦 ===")
    print("实体提取操作将会花费较多api余额和时间，建议在空闲时段执行。")
    print("举例：600万字全剧情，提取选用deepseek v3 0324，消耗约40元，约3小时。")
    print("建议使用硅基流动的非Pro模型")
    print("或者使用可以用赠金抵扣的Pro模型")
    print("请确保账户余额充足，并且在执行前确认无误。")
    confirm = input("确认继续执行？(y/n): ").strip().lower()
    if confirm != "y":
        logger.info("用户取消操作")
        print("操作已取消")
        sys.exit(1)
    print("\n" + "=" * 40 + "\n")
    ensure_dirs()  # 确保目录存在
    logger.info("--------进行信息提取--------\n")

    # 加载原始数据
    logger.info("正在加载原始数据")
    all_sha256_list, all_raw_datas = load_raw_data()

    failed_sha256 = []
    open_ie_doc = []

    workers = global_config.lpmm_knowledge.info_extraction_workers
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_hash = {
            executor.submit(process_single_text, pg_hash, raw_data): pg_hash
            for pg_hash, raw_data in zip(all_sha256_list, all_raw_datas, strict=False)
        }

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            "•",
            TimeElapsedColumn(),
            "<",
            TimeRemainingColumn(),
            transient=False,
        ) as progress:
            task = progress.add_task("正在进行提取：", total=len(future_to_hash))
            try:
                for future in as_completed(future_to_hash):
                    if shutdown_event.is_set():
                        for f in future_to_hash:
                            if not f.done():
                                f.cancel()
                        break

                    doc_item, failed_hash = future.result()
                    if failed_hash:
                        failed_sha256.append(failed_hash)
                        logger.error(f"提取失败：{failed_hash}")
                    elif doc_item:
                        with open_ie_doc_lock:
                            open_ie_doc.append(doc_item)
                    progress.update(task, advance=1)
            except KeyboardInterrupt:
                logger.info("\n接收到中断信号，正在优雅地关闭程序...")
                shutdown_event.set()
                for f in future_to_hash:
                    if not f.done():
                        f.cancel()

    # 合并所有文件的提取结果并保存
    if open_ie_doc:
        sum_phrase_chars = sum([len(e) for chunk in open_ie_doc for e in chunk["extracted_entities"]])
        sum_phrase_words = sum([len(e.split()) for chunk in open_ie_doc for e in chunk["extracted_entities"]])
        num_phrases = sum([len(chunk["extracted_entities"]) for chunk in open_ie_doc])
        openie_obj = OpenIE(
            open_ie_doc,
            round(sum_phrase_chars / num_phrases, 4) if num_phrases else 0,
            round(sum_phrase_words / num_phrases, 4) if num_phrases else 0,
        )
        # 输出文件名格式：MM-DD-HH-ss-openie.json
        now = datetime.datetime.now()
        filename = now.strftime("%m-%d-%H-%S-openie.json")
        output_path = os.path.join(OPENIE_OUTPUT_DIR, filename)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                openie_obj.to_dict() if hasattr(openie_obj, "to_dict") else openie_obj.__dict__,
                f,
                ensure_ascii=False,
                indent=4,
            )
        logger.info(f"信息提取结果已保存到: {output_path}")
    else:
        logger.warning("没有可保存的信息提取结果")

    logger.info("--------信息提取完成--------")
    logger.info(f"提取失败的文段SHA256：{failed_sha256}")


if __name__ == "__main__":
    main()

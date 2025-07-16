import json
import time
from typing import List, Union

from .global_logger import logger
from . import prompt_template
from .knowledge_lib import INVALID_ENTITY
from src.llm_models.utils_model import LLMRequest
from json_repair import repair_json
def _extract_json_from_text(text: str) -> dict:
    """从文本中提取JSON数据的高容错方法"""
    try:
        fixed_json = repair_json(text)
        if isinstance(fixed_json, str):
            parsed_json = json.loads(fixed_json)
        else:
            parsed_json = fixed_json

        if isinstance(parsed_json, list) and parsed_json:
            parsed_json = parsed_json[0]

        if isinstance(parsed_json, dict):
            return parsed_json

    except Exception as e:
        logger.error(f"JSON提取失败: {e}, 原始文本: {text[:100]}...")

def _entity_extract(llm_req: LLMRequest, paragraph: str) -> List[str]:
    """对段落进行实体提取，返回提取出的实体列表（JSON格式）"""
    entity_extract_context = prompt_template.build_entity_extract_context(paragraph)
    response, (reasoning_content, model_name) = llm_req.generate_response_sync(entity_extract_context)

    entity_extract_result = _extract_json_from_text(response)
    # 尝试load JSON数据
    json.loads(entity_extract_result)
    entity_extract_result = [
        entity
        for entity in entity_extract_result
        if (entity is not None) and (entity != "") and (entity not in INVALID_ENTITY)
    ]

    if len(entity_extract_result) == 0:
        raise Exception("实体提取结果为空")

    return entity_extract_result


def _rdf_triple_extract(llm_req: LLMRequest, paragraph: str, entities: list) -> List[List[str]]:
    """对段落进行实体提取，返回提取出的实体列表（JSON格式）"""
    rdf_extract_context = prompt_template.build_rdf_triple_extract_context(
        paragraph, entities=json.dumps(entities, ensure_ascii=False)
    )
    response, (reasoning_content, model_name) = llm_req.generate_response_sync(rdf_extract_context)

    entity_extract_result = _extract_json_from_text(response)
    # 尝试load JSON数据
    json.loads(entity_extract_result)
    for triple in entity_extract_result:
        if len(triple) != 3 or (triple[0] is None or triple[1] is None or triple[2] is None) or "" in triple:
            raise Exception("RDF提取结果格式错误")

    return entity_extract_result


def info_extract_from_str(
    llm_client_for_ner: LLMRequest, llm_client_for_rdf: LLMRequest, paragraph: str
) -> Union[tuple[None, None], tuple[list[str], list[list[str]]]]:
    try_count = 0
    while True:
        try:
            entity_extract_result = _entity_extract(llm_client_for_ner, paragraph)
            break
        except Exception as e:
            logger.warning(f"实体提取失败，错误信息：{e}")
            try_count += 1
            if try_count < 3:
                logger.warning("将于5秒后重试")
                time.sleep(5)
            else:
                logger.error("实体提取失败，已达最大重试次数")
                return None, None

    try_count = 0
    while True:
        try:
            rdf_triple_extract_result = _rdf_triple_extract(llm_client_for_rdf, paragraph, entity_extract_result)
            break
        except Exception as e:
            logger.warning(f"实体提取失败，错误信息：{e}")
            try_count += 1
            if try_count < 3:
                logger.warning("将于5秒后重试")
                time.sleep(5)
            else:
                logger.error("实体提取失败，已达最大重试次数")
                return None, None

    return entity_extract_result, rdf_triple_extract_result

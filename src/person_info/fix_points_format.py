import os
import sys  
# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

from loguru import logger
import json
from src.common.database.database_model import PersonInfo

def fix_points_format():
    """修复数据库中的points和forgotten_points格式"""
    fixed_count = 0
    error_count = 0
    
    try:
        # 获取所有用户
        all_persons = PersonInfo.select()
        
        for person in all_persons:
            try:
                # 修复points
                if person.points:
                    try:
                        # 尝试解析JSON
                        points_data = json.loads(person.points)
                    except json.JSONDecodeError:
                        logger.error(f"无法解析points数据: {person.points}")
                        points_data = []
                    
                    # 确保数据是列表格式
                    if not isinstance(points_data, list):
                        points_data = []
                    
                    # 直接更新数据库
                    person.points = json.dumps(points_data, ensure_ascii=False)
                    person.save()
                    fixed_count += 1
                
                # 修复forgotten_points
                if person.forgotten_points:
                    try:
                        # 尝试解析JSON
                        forgotten_data = json.loads(person.forgotten_points)
                    except json.JSONDecodeError:
                        logger.error(f"无法解析forgotten_points数据: {person.forgotten_points}")
                        forgotten_data = []
                    
                    # 确保数据是列表格式
                    if not isinstance(forgotten_data, list):
                        forgotten_data = []
                    
                    # 直接更新数据库
                    person.forgotten_points = json.dumps(forgotten_data, ensure_ascii=False)
                    person.save()
                    fixed_count += 1
                    
            except Exception as e:
                logger.error(f"处理用户 {person.person_id} 时出错: {str(e)}")
                error_count += 1
                continue
        
        logger.info(f"修复完成！成功修复 {fixed_count} 条记录，失败 {error_count} 条记录")
        
    except Exception as e:
        logger.error(f"数据库操作出错: {str(e)}")

if __name__ == "__main__":
    fix_points_format() 
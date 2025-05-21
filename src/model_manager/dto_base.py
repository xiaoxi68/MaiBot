from abc import abstractmethod
from dataclasses import dataclass, field, fields
from typing import Optional, Type, TypeVar

from src.utils.bool_expression import AndExpr, BoolExpr, FieldExpr, FieldRule, NotExpr, OrExpr, compile_condition


class DTOValidationError(Exception):
    """DTO验证错误异常类"""

    pass


T = TypeVar("T", bound="DTOBase")


class ASTMap:
    MAP = {}


@dataclass
class DTOBase:
    """
    数据传输对象基类
    """

    __orm_create_rule__: Optional[FieldRule] = field(default=None, init=False, repr=False, compare=False)
    """ORM创建时需要的字段填充规则

    允许通过布尔表达式来指定ORM创建时的字段填充规则
    例如：__orm_create_field__ = "id | (field1 & !field2)"
    这将要求在创建对象时，必须提供 id 字段，或者提供 field1 字段的同时不能提供 field2 字段
    """

    __orm_create_rule_ast__: Optional[BoolExpr] = field(default=None, init=False, repr=False, compare=False)
    """ORM创建时需要的字段填充规则的AST"""

    __orm_select_rule__: Optional[FieldRule] = field(default=None, init=False, repr=False, compare=False)
    """ORM查询时需要的字段列表
    
    允许通过布尔表达式来指定ORM查询时的字段填充规则
    例如：__orm_select_field__ = "id | (field1 & !field2)"
    这将要求在查询对象时，必须提供 id 字段，或者提供 field1 字段的同时不能提供 field2 字段
    """

    __orm_select_rule_ast__: Optional[BoolExpr] = field(default=None, init=False, repr=False, compare=False)
    """ORM查询时需要的字段填充规则的AST"""

    __orm_update_rule__: Optional[FieldRule] = field(default=None, init=False, repr=False, compare=False)
    """ORM更新时需要的字段填充规则

    注：更新时，在检查该规则的约束前，还会检查查询时的约束（即 __orm_select_rule__）

    允许通过布尔表达式来指定ORM更新时的字段填充规则
    例如：__orm_update_field__ = "id | (field1 & !field2)"
    这将要求在更新对象时，必须提供 id 字段，或者提供 field1 字段的同时不能提供 field2 字段
    """

    __orm_delete_rule__: Optional[FieldRule] = field(default=None, init=False, repr=False, compare=False)
    """ORM删除时需要的字段填充规则
    
    注：删除时，在检查该规则的约束前，还会检查查询时的约束（即 __orm_select_rule__）
    再注：一般来说，删除时不需要提供任何字段，因此该规则一般为 None 不用修改

    允许通过布尔表达式来指定ORM删除时的字段填充规则
    例如：__orm_delete_field__ = "id | (field1 & !field2)"
    这将要求在删除对象时，必须提供 id 字段，或者提供 field1 字段的同时不能提供 field2 字段
    """

    __orm_delete_rule_ast__: Optional[BoolExpr] = field(default=None, init=False, repr=False, compare=False)
    """ORM删除时需要的字段填充规则的AST"""

    @classmethod
    @abstractmethod
    def from_orm(cls, entity):
        """从ORM对象创建DTO对象"""
        raise NotImplementedError("Subclass must implement 'from_orm' method")

    def __post_init__(self):
        """后初始化"""
        self._init_select_rule_ast()
        self._init_create_rule_ast()
        self._init_update_rule_ast()
        self._init_delete_rule_ast()

    def _init_select_rule_ast(self):
        if self.__orm_select_rule__ is not None:
            if self.__orm_select_rule__ in ASTMap.MAP:
                self.__orm_select_rule_ast__ = ASTMap.MAP[self.__orm_select_rule__]
            else:
                self.__orm_select_rule_ast__ = compile_condition(self.__orm_select_rule__, type(self))
                ASTMap.MAP[self.__orm_select_rule__] = self.__orm_select_rule_ast__

    def _init_create_rule_ast(self):
        if self.__orm_create_rule__ is not None:
            if self.__orm_create_rule__ in ASTMap.MAP:
                self.__orm_create_rule_ast__ = ASTMap.MAP[self.__orm_create_rule__]
            else:
                self.__orm_create_rule_ast__ = compile_condition(self.__orm_create_rule__, type(self))
                ASTMap.MAP[self.__orm_create_rule__] = self.__orm_create_rule_ast__

    def _init_update_rule_ast(self):
        if self.__orm_update_rule__ is not None:
            if self.__orm_update_rule__ in ASTMap.MAP:
                self.__orm_update_rule_ast__ = ASTMap.MAP[self.__orm_update_rule__]
            else:
                self.__orm_update_rule_ast__ = compile_condition(self.__orm_update_rule__, type(self))
                ASTMap.MAP[self.__orm_update_rule__] = self.__orm_update_rule_ast__

    def _init_delete_rule_ast(self):
        if self.__orm_delete_rule__ is not None:
            if self.__orm_delete_rule__ in ASTMap.MAP:
                self.__orm_delete_rule_ast__ = ASTMap.MAP[self.__orm_delete_rule__]
            else:
                self.__orm_delete_rule_ast__ = compile_condition(self.__orm_delete_rule__, type(self))
                ASTMap.MAP[self.__orm_delete_rule__] = self.__orm_delete_rule_ast__

    def _get_fill_map(self) -> dict[str, bool]:
        """获取字段填充映射

        该方法用于获取当前对象的字段填充映射
        字段名为键，字段值是否为 None 为值
        """
        fill_map = {}
        for field_ in fields(self):
            field_name = field_.name
            if field_name.startswith("_"):
                # 跳过以 _ 开头的字段
                continue

            fill_map[field_name] = getattr(self, field_name) is not None

        return fill_map

    def create_entity_check(self) -> bool:
        """创建实体字段检查"""

        if self.__orm_create_rule_ast__ is None:
            return True

        fill_map = self._get_fill_map()

        return self.validate_rule(self.__orm_create_rule_ast__, fill_map)

    def select_entity_check(self) -> bool:
        """查询实体字段检查"""

        if self.__orm_select_rule_ast__ is None:
            return True

        fill_map = self._get_fill_map()

        return self.validate_rule(self.__orm_select_rule_ast__, fill_map)

    def update_entity_check(self) -> bool:
        """更新实体字段检查"""

        if self.select_entity_check() is False:
            # 如果查询实体检查不通过，则返回 False
            return False

        # 如果查询实体检查通过，则继续检查更新实体
        if self.__orm_update_rule_ast__ is None:
            return True

        fill_map = self._get_fill_map()

        return self.validate_rule(self.__orm_update_rule_ast__, fill_map)

    def delete_entity_check(self) -> bool:
        """删除实体字段检查"""

        if self.select_entity_check() is False:
            # 如果查询实体检查不通过，则返回 False
            return False

        # 如果查询实体检查通过，则继续检查删除实体
        if self.__orm_delete_rule_ast__ is None:
            return True

        fill_map = self._get_fill_map()

        return self.validate_rule(self.__orm_delete_rule_ast__, fill_map)

    @classmethod
    def validate_rule(cls: Type[T], condition: BoolExpr, fill_map: dict[str, bool]) -> bool:
        """验证字段值是否符合规则

        condition 是一个字符串，
        例如："('field1' OR ('field2' AND NOT 'field3'))"
        该字符串表示一个布尔表达式，

        :param condition: 字段规则
        :param fill_map: 字段值填充映射
        """
        # 直接返回布尔值
        if condition == "True":
            return True
        elif condition == "False":
            return False

        # 处理布尔表达式
        if isinstance(condition, FieldExpr):
            # 字段名
            field_name = condition.field
            if field_name not in fill_map:
                raise DTOValidationError(f"Field '{field_name}' not found in fill_map")
            return fill_map[field_name]
        elif isinstance(condition, NotExpr):
            # 非表达式
            return not cls.validate_rule(condition.expr, fill_map)
        elif isinstance(condition, AndExpr):
            # 与表达式
            return cls.validate_rule(condition.left, fill_map) and cls.validate_rule(condition.right, fill_map)
        elif isinstance(condition, OrExpr):
            # 或表达式
            return cls.validate_rule(condition.left, fill_map) or cls.validate_rule(condition.right, fill_map)
        else:
            raise DTOValidationError(f"Unknown condition type: {type(condition).__name__}")

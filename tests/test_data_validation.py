from abc import abstractmethod
from dataclasses import dataclass, field, fields
from typing import Optional, Type, TypeVar
import re


class BoolExpr:
    """布尔表达式基类"""

    _str: str = field(default=None, init=False, repr=False, compare=False)
    """表达式字符串"""

    def __str__(self):
        """返回表达式字符串"""
        return self._str

    def __eq__(self, value):
        """比较表达式"""
        if isinstance(value, str):
            return self._str == value
        elif isinstance(value, BoolExpr):
            return self._str == value._str
        else:
            return False

    @abstractmethod
    def to_dict(self):
        """将表达式转换为字典"""
        pass


class FieldExpr(BoolExpr):
    """字段名"""

    def __init__(self, field: str):
        self.field = field
        self._str = field

    def to_dict(self):
        return {"field_name": self.field}


class NotExpr(BoolExpr):
    """非表达式"""

    def __init__(self, expr: BoolExpr):
        self.expr = expr
        self._str = f"!{str(expr)}"

    def set_expr(self, expr: BoolExpr):
        """设置表达式"""
        self.expr = expr
        self._str = f"!{str(expr)}"  # !expr

    def to_dict(self):
        return {"operator": "!", "expr": self.expr.to_dict()}


class AndExpr(BoolExpr):
    """与表达式"""

    def __init__(self, left: BoolExpr, right: BoolExpr):
        self.left = left
        self.right = right
        self._str = f"({left} & {right})"  # (expr1 & expr2)

    def set_expr(self, left: BoolExpr = None, right: BoolExpr = None):
        """设置表达式"""
        if left:
            self.left = left
        if right:
            self.right = right
        if left or right:
            self._str = f"({self.left} & {self.right})"

    def to_dict(self):
        return {"operator": "&", "left": self.left.to_dict(), "right": self.right.to_dict()}


class OrExpr(BoolExpr):
    """或表达式"""

    def __init__(self, left: BoolExpr, right: BoolExpr):
        self.left = left
        self.right = right
        self._str = f"({left} | {right})"  # (expr1 | expr2)

    def set_expr(self, left: BoolExpr = None, right: BoolExpr = None):
        """设置表达式"""
        if left:
            self.left = left
        if right:
            self.right = right
        if left or right:
            self._str = f"({self.left} | {self.right})"

    def to_dict(self):
        return {"operator": "|", "left": self.left.to_dict(), "right": self.right.to_dict()}


FieldRule = str
"""字段规则类型别名"""

Token = tuple[str, str | None]
"""词元类型别名"""

SPEC_TOKENS: list[tuple[str, str]] = [
    ("AND", r"&"),  # 与
    ("OR", r"\|"),  # 或
    ("NOT", r"!"),  # 非
    ("L_PAREN", r"\("),  # 左括号
    ("R_PAREN", r"\)"),  # 右括号
    ("IDENT", r"[a-zA-Z_][a-zA-Z0-9_]*"),  # 标识符
    ("SKIP", r"[ \t]+"),  # 跳过空格和制表符
    ("MISMATCH", r"."),  # 匹配其他字符
]
"""特殊标记元组集

（名称，正则表达式）
"""

OPERATORS: dict[str, tuple[int, bool]] = {
    "OR": (1, False),  # 或
    "AND": (2, False),  # 与
    "NOT": (3, True),  # 非
}
"""操作符属性字典

操作符名称: (优先级, 是否右结合)
"""


def _tokenize(condition: FieldRule):
    """将条件字符串分词为词元列表"""

    token_regex = "|".join(f"(?P<{name}>{pattern})" for name, pattern in SPEC_TOKENS)

    for match in re.finditer(token_regex, condition):
        token_type = match.lastgroup
        token_value = match.group(token_type)

        if token_type == "IDENT":
            yield "IDENT", token_value
        elif token_type == "AND":
            yield "AND", token_value
        elif token_type == "OR":
            yield "OR", token_value
        elif token_type == "NOT":
            yield "NOT", token_value
        elif token_type == "L_PAREN":
            yield "L_PAREN", token_value
        elif token_type == "R_PAREN":
            yield "R_PAREN", token_value
        elif token_type == "SKIP":
            continue
        else:
            raise SyntaxError(f"Unexpected character: {token_value}")


def compile_condition(condition: FieldRule, class_type: type = None) -> BoolExpr:
    """编译条件字符串为表达式树"""

    tokens = list(_tokenize(condition))

    if class_type:
        if not hasattr(class_type, "__dataclass_fields__"):
            raise TypeError(f"Expected a dataclass type, got {class_type.__name__}")
        class_fields = {field_.name for field_ in class_type.__dataclass_fields__.values()}
    else:
        class_fields = None

    output = []  # 表达式栈
    ops = []  # 操作符栈

    last_token_type = None

    def apply_operator():
        """应用栈顶操作符"""
        operator = ops.pop()
        match operator:
            case "AND":
                right = output.pop()
                left = output.pop()
                output.append(AndExpr(left, right))
            case "OR":
                right = output.pop()
                left = output.pop()
                output.append(OrExpr(left, right))
            case "NOT":
                right = output.pop()
                output.append(NotExpr(right))

    idx = 0

    while idx < len(tokens):
        token_type, token_value = tokens[idx]  # 解包词元类型和词元值

        if token_type == "IDENT":
            # 字段名
            if last_token_type == "IDENT":
                # 不应出现连续的标识符
                raise SyntaxError(f"Expected operator but found identifier '{token_value}' at token index {idx}")
            if class_fields and token_value not in class_fields:
                # 如果指定了类类型，则检查字段名是否在类字段中
                raise SyntaxError(f"Unknown field '{token_value}' at token index {idx}, expected one of {class_fields}")
            output.append(FieldExpr(token_value))
        elif token_type in OPERATORS:
            # 操作符

            if token_type != "NOT" and last_token_type in OPERATORS:
                # 除非当前操作符为NOT，否则不应出现连续的操作符
                raise SyntaxError(f"Unexpected operator '{token_value}' at token index {idx}")

            while (
                ops
                and ops[-1] in OPERATORS
                and (
                    (not OPERATORS[token_type][1] and OPERATORS[token_type][0] <= OPERATORS[ops[-1]][0])
                    or (OPERATORS[token_type][1] and OPERATORS[token_type][0] < OPERATORS[ops[-1]][0])
                )
            ):
                # 有其它操作符
                # 栈顶为操作符
                # 当前操作符左结合，且优先级不高于栈顶操作符
                # 当前操作符右结合，且优先级低于栈顶操作符
                # 则应用栈顶操作符
                apply_operator()
            ops.append(token_type)
        elif token_type == "L_PAREN":
            # 左括号
            ops.append("L_PAREN")
        elif token_type == "R_PAREN":
            # 右括号
            while ops and ops[-1] in OPERATORS:
                # 栈顶为操作符
                apply_operator()
            if not ops or ops[-1] != "L_PAREN":
                raise SyntaxError("Mismatched parentheses, missing '('")
            ops.pop()
        else:
            raise SyntaxError(f"Unexpected token: {token_value}")

        last_token_type = token_type

        idx += 1

    while ops:
        if ops[-1] == "L_PAREN":
            raise SyntaxError("Mismatched parentheses, missing ')'")
        apply_operator()

    if len(output) != 1:
        raise SyntaxError("Invalid expression, too many values")

    return _simplify(output[0])


def _simplify(expr: BoolExpr) -> BoolExpr:
    """简化表达式树"""

    if isinstance(expr, NotExpr):
        inner = _simplify(expr.expr)
        return inner.expr if isinstance(inner, NotExpr) else NotExpr(inner)
    if isinstance(expr, AndExpr):
        return _simplify_and_expr(expr)
    if isinstance(expr, OrExpr):
        return _simplify_or_expr(expr)
    if isinstance(expr, FieldExpr):
        return expr


def _simplify_and_expr(expr: AndExpr):
    left = _simplify(expr.left)
    right = _simplify(expr.right)

    # A AND A = A
    if left == right:
        return left

    # A AND True = A
    if left == "True":
        return right
    if right == "True":
        return left

    # A AND False = False
    if "False" in [left, right]:
        return FieldExpr("False")

    # A AND NOT A = False
    if isinstance(right, NotExpr) and left == right.expr:
        return FieldExpr("False")
    if isinstance(left, NotExpr) and right == left.expr:
        return FieldExpr("False")

    # A AND (A OR B) = A
    if isinstance(right, OrExpr) and left in [right.left, right.right]:
        return left
    if isinstance(left, OrExpr) and right in [left.left, left.right]:
        return right

    return AndExpr(left, right)


def _simplify_or_expr(expr):
    left = _simplify(expr.left)
    right = _simplify(expr.right)

    # A OR A = A
    if left == right:
        return left

    # A OR True = True
    if "True" in [left, right]:
        return FieldExpr("True")

    # A OR False = A
    if left == "False":
        return right
    if right == "False":
        return left

    # A OR NOT A = True
    if isinstance(right, NotExpr) and left == right.expr:
        return FieldExpr("True")
    if isinstance(left, NotExpr) and right == left.expr:
        return FieldExpr("True")

    # A OR (A AND B) = A
    if isinstance(right, AndExpr) and left in [right.left, right.right]:
        return left
    if isinstance(left, AndExpr) and right in [left.left, left.right]:
        return right

    return OrExpr(left, right)


class DTOValidationError(Exception):
    """DTO验证错误异常类"""

    pass


T = TypeVar("T", bound="DTOBase")


class ASTMap:
    MAP = {}


class DTOBase:
    """
    数据传输对象基类
    """

    __orm_select_field__: Optional[FieldRule] = field(default=None, init=False, repr=False, compare=False)
    """ORM查询时需要的字段列表
    
    允许通过填充该字段来指定ORM查询时需要的字段列表
    例如：__orm_select_field__ = "('id' OR ('field1' AND 'field2'))"
    """

    __orm_select_field_ast__: Optional[BoolExpr] = field(default=None, init=False, repr=False, compare=False)
    """ORM查询时需要的字段列表的AST"""

    def __post_init__(self):
        """后初始化"""
        if self.__orm_select_field__ is not None:
            if self.__orm_select_field__ in ASTMap.MAP:
                # 如果已经存在AST，则直接使用
                self.__orm_select_field_ast__ = ASTMap.MAP[self.__orm_select_field__]
            else:
                # 否则，解析字符串并创建AST
                self.__orm_select_field_ast__ = compile_condition(self.__orm_select_field__, type(self))
                ASTMap.MAP[self.__orm_select_field__] = self.__orm_select_field_ast__

    @classmethod
    @abstractmethod
    def from_orm(cls, entity):
        """从ORM对象创建DTO对象"""
        raise NotImplementedError("Subclass must implement 'from_orm' method")

    def select_entity_check(self) -> bool:
        """创建实体字段检查"""

        if self.__orm_select_field_ast__ is None:
            return True

        fill_map = {}
        for field_ in fields(self):
            field_name = field_.name
            if field_name.startswith("_"):
                # 跳过以 _ 开头的字段
                continue

            fill_map[field_name] = getattr(self, field_name) is not None

        return self.validate_field(self.__orm_select_field_ast__, fill_map)

    @classmethod
    def validate_field(cls: Type[T], condition: BoolExpr, fill_map: dict[str, bool]) -> bool:
        """验证字段值是否符合规则

        condition 是一个字符串，
        例如："('field1' OR ('field2' AND NOT 'field3'))"
        该字符串表示一个布尔表达式，

        :param condition: 字段规则
        :param fill_map: 字段值填充映射
        """
        if isinstance(condition, FieldExpr):
            # 字段名
            field_name = condition.field
            if field_name not in fill_map:
                raise DTOValidationError(f"Field '{field_name}' not found in fill_map")
            return fill_map[field_name]
        elif isinstance(condition, NotExpr):
            # 非表达式
            return not cls.validate_field(condition.expr, fill_map)
        elif isinstance(condition, AndExpr):
            # 与表达式
            return cls.validate_field(condition.left, fill_map) and cls.validate_field(condition.right, fill_map)
        elif isinstance(condition, OrExpr):
            # 或表达式
            return cls.validate_field(condition.left, fill_map) or cls.validate_field(condition.right, fill_map)
        else:
            raise DTOValidationError(f"Unknown condition type: {type(condition).__name__}")


@dataclass
class TmpDTO(DTOBase):
    """
    测试DTO
    """

    id: int = None
    """主键（由数据库创建，自动递增）"""

    created_at: str = None
    """创建时间戳"""

    platform: str = None
    """平台名称"""

    platform_group_id: str = None
    """平台群组 ID （如 QQ 群号）"""

    group_name: str = None
    """群组名称（可能为空）"""

    platform_spec_info: str = None
    """平台特定的信息（可能为空）"""

    __orm_select_field__ = "id | (platform & platform_group_id)"


if __name__ == "__main__":
    # 测试DTO
    dto = TmpDTO()
    print(dto.__orm_select_field__)
    print(dto.__orm_select_field_ast__)
    print(dto.__orm_select_field_ast__.to_dict())

    dto.platform = "1"
    dto.platform_group_id = "2"

    print(dto.select_entity_check())

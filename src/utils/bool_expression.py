from abc import abstractmethod
from dataclasses import field
import re
from typing import Optional


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


def _get_class_fields(class_type: Optional[type]) -> set[str]:
    """获取类的字段名集合"""
    if not class_type:
        return None
    if not hasattr(class_type, "__dataclass_fields__"):
        raise TypeError(f"Expected a dataclass type, got {class_type.__name__}")
    return {field_.name for field_ in class_type.__dataclass_fields__.values() if not field_.name.startswith("_")}


def compile_condition(condition: FieldRule, class_type: Optional[type] = None) -> BoolExpr:
    """编译条件字符串为表达式树"""

    tokens = list(_tokenize(condition))

    class_fields = _get_class_fields(class_type)  # 参考类的字段名集合

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

    # TODO: 更先进/智能的化简策略，如Q-M算法

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

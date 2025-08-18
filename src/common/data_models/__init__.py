from typing import Dict, Any


class AbstractClassFlag:
    pass


def temporarily_transform_class_to_dict(obj: Any) -> Any:
    """
    将对象或容器中的 AbstractClassFlag 子类（类对象）或 AbstractClassFlag 实例
    递归转换为普通 dict，不修改原对象。
    - 对于类对象（isinstance(value, type) 且 issubclass(..., AbstractClassFlag)），
      读取类的 __dict__ 中非 dunder 项并递归转换。
    - 对于实例（isinstance(value, AbstractClassFlag)），读取 vars(instance) 并递归转换。
    """

    def _transform(value: Any) -> Any:
        # 值是类对象且为 AbstractClassFlag 的子类
        if isinstance(value, type) and issubclass(value, AbstractClassFlag):
            return {k: _transform(v) for k, v in value.__dict__.items() if not k.startswith("__") and not callable(v)}

        # 值是 AbstractClassFlag 的实例
        if isinstance(value, AbstractClassFlag):
            return {k: _transform(v) for k, v in vars(value).items()}

        # 常见容器类型，递归处理
        if isinstance(value, dict):
            return {k: _transform(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_transform(v) for v in value]
        if isinstance(value, tuple):
            return tuple(_transform(v) for v in value)
        if isinstance(value, set):
            return {_transform(v) for v in value}
        # 基本类型，直接返回
        return value

    result = _transform(obj)

    def flatten(target_dict: dict):
        flat_dict = {}
        for k, v in target_dict.items():
            if isinstance(v, dict):
                # 递归扁平化子字典
                sub_flat = flatten(v)
                flat_dict.update(sub_flat)
            else:
                flat_dict[k] = v
        return flat_dict

    return flatten(result) if isinstance(result, dict) else result

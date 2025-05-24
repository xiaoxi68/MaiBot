import hashlib
import os


def calc_bytes_hash(data: bytes) -> str:
    """
    计算字节数据的SHA-256哈希值

    :param data: 字节数据
    :return: 哈希值字符串
    """
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.hexdigest()


def calc_file_hash(file_path: str) -> str:
    """
    计算文件的SHA-256哈希值

    :param file_path: 文件路径
    :return: 哈希值字符串
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    if not os.path.isfile(file_path):
        raise ValueError(f"Path is not a file: {file_path}")

    with open(file_path, "rb") as f:
        data = f.read()
    return calc_bytes_hash(data)

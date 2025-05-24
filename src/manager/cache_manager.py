"""
内存缓存层，依赖Dict实现
"""

import random
from datetime import datetime, timedelta
from typing import Any, Optional

from src.manager.async_task_manager import AsyncTask


class CacheItem:
    def __init__(self, value: Any, ttl: int):
        if ttl < 0:
            raise ValueError("TTL must be a non-negative integer.")

        now = datetime.now()

        self._value: Any = value
        """缓存值"""

        self._ttl: int = ttl
        """缓存存活时间（秒）
        None表示永久缓存
        """

        self._expiration_time: Optional[datetime] = (now + timedelta(seconds=ttl)) if ttl != int("inf") else None
        """缓存过期时间（在ttl不为inf时有效）
        None表示永久缓存
        """

        self.last_used_at: datetime = now
        """最后使用时间"""

        self.freq_counter: int = 0
        """频率计数器，越大越常用（LFU算法）"""

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """检查缓存是否过期

        :param now: 基准时间（可选），如果不提供，则使用当前时间
        :return: 布尔值 - True表示过期，False表示未过期
        """
        if self._expiration_time is None:
            return False
        return self._expiration_time < (now or datetime.now())

    def reset_expiration(self, ttl: Optional[int], now: Optional[datetime] = None):
        """重置缓存过期时间

        :param ttl: 缓存存活时间（可选），如果不提供，则使用原有的ttl
        :param now: 基准时间（可选），如果不提供，则使用当前时间
        """
        if ttl:
            # 提供了新的ttl
            if ttl < 0:  # 检查ttl是否为负数
                raise ValueError("TTL must be a non-negative integer.")

            self._ttl = ttl

        self._expiration_time = (now or datetime.now()) + timedelta(seconds=ttl) if ttl != int("inf") else None

    def get_value(self, now: Optional[datetime] = None) -> Any:
        """获取缓存值"""
        self.freq_counter += 1
        self.last_used_at = now or datetime.now()
        return self._value

    def decrease_freq_counter(self):
        """减少频率计数器
        空闲时间越长，衰减越快
        """
        if self.freq_counter > 0:
            idle_time = (datetime.now() - self.last_used_at).total_seconds()

            decay_factor = 0.05  # 衰减因子

            # 计算衰减后的频率计数器
            self.freq_counter = int(self.freq_counter - (1 + decay_factor * idle_time))


class CacheManager:
    EVICT_POOL_SIZE = 16
    """EVICT池大小（遵循Redis默认值为16，不宜过大）"""

    def __init__(self, max_cache_size: int = 200):
        self._cache: dict[str, CacheItem] = {}
        """缓存池"""

        self._evict_pool: dict[str, int] = {}
        """EVICT池"""

        self._max_cache_size = max_cache_size
        """最大缓存大小"""

        self._rand_select_freq = min(1, max(0, 100 / max_cache_size))
        """随机选择频率（0-1之间）"""

    def reset_max_cache_size(self, max_cache_size: int):
        """重置最大缓存大小

        :param max_cache_size: 最大缓存大小
        """
        if max_cache_size <= 0:
            raise ValueError("Max cache size must be a positive integer.")

        self._max_cache_size = max_cache_size
        self._rand_select_freq = min(1, max(0, 100 / max_cache_size))

    def __setitem__(self, args: str | tuple[str, int], value):
        """设置缓存项

        :param args: key / (key, ttl)
        """
        if isinstance(args, str):
            key, ttl = args, int("inf")
        elif isinstance(args, tuple) and len(args) == 2 and isinstance(args[1], str) and isinstance(args[1], int):
            key, ttl = args[0], args[1]
        else:
            raise TypeError("Key must be a string or a tuple of (key, ttl).")

        if key in self._cache:
            item = self._cache[key]
            item._value = value
            item.reset_expiration(ttl)
        else:
            if len(self._cache) >= self._max_cache_size:
                # 清理过期缓存项
                self.cleanup()

            # 如果仍然超过最大缓存大小，则随机LRU替换
            if len(self._cache) >= self._max_cache_size:
                self._eliminate_cache()

            # 添加新缓存项
            self._cache[key] = CacheItem(value, ttl)

    def __getitem__(self, key: str) -> Any:
        """获取缓存项

        :param key: 缓存键
        """
        if key not in self._cache:
            return None

        item = self._cache[key]
        now = datetime.now()

        if item.is_expired(now):
            del self._cache[key]
            if key in self._evict_pool:
                del self._evict_pool[key]
            return None

        return item.get_value(now)

    def __delitem__(self, key: str):
        """删除缓存项

        :param key: 缓存键
        """
        if key in self._cache:
            del self._cache[key]

        if key in self._evict_pool:
            del self._evict_pool[key]

    def __contains__(self, key: str) -> bool:
        """检查缓存项是否存在

        :param key: 缓存键
        """
        if key not in self._cache:
            return False

        item = self._cache[key]

        if item.is_expired():
            del self._cache[key]
            if key in self._evict_pool:
                del self._evict_pool[key]
            return False

        return True

    def cleanup(self):
        """清理过期缓存项"""
        now = datetime.now()
        expired_keys = [key for key, item in self._cache.items() if item.is_expired(now)]
        for key in expired_keys:
            del self._cache[key]

        # 清理EVICT池
        self._evict_pool = [(key, freq) for key, freq in self._cache.items() if key not in expired_keys]

    def _eliminate_cache(self):
        """淘汰缓存项

        仿效Redis使用近似LFU算法，删除使用频率最低的一个缓存项（在执行该操作前需要先执行cleanup）
        """

        self._update_evict_pool()

        if not self._evict_pool:
            return

        # 选择EVICT池中频率计数器最小的缓存项，删除
        min_freq_key = min(self._evict_pool.items(), key=lambda x: x[1])[0]
        del self._cache[min_freq_key]

    def _update_evict_pool(self):
        """更新EVICT池"""

        # 最小频率
        min_freq = min(self._evict_pool.values()) if self._evict_pool else int("inf")

        rand = random.Random()

        for key, item in self._cache.items():
            if rand.random() < self._rand_select_freq:
                # 添加条件（二选一）：
                # 1. EVICT池未满
                # 2. EVICT池中存在一个缓存项Item，使得Item的freq_counter > 当前项的freq_counter
                if len(self._evict_pool) < self.EVICT_POOL_SIZE:
                    self._evict_pool[key] = item.freq_counter
                elif item.freq_counter < min_freq:
                    # 替换EVICT池中频率计数器最大的缓存项
                    max_freq_key = max(self._evict_pool.items(), key=lambda x: x[1])[0]
                    del self._evict_pool[max_freq_key]
                    self._evict_pool[key] = item.freq_counter

    def clear(self):
        """Clear the entire cache."""
        self._cache.clear()
        self._evict_pool.clear()


class CacheCleanerTask(AsyncTask):
    CLEAN_INTERVAL = 60
    """清理间隔（秒）"""

    def __init__(self):
        super().__init__(
            task_name="Cache Cleaner", wait_before_start=self.CLEAN_INTERVAL, run_interval=self.CLEAN_INTERVAL
        )

    async def run(self):
        global_cache.cleanup()


global_cache = CacheManager()

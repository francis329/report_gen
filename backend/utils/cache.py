"""
报告规划缓存工具
使用内存缓存，支持 TTL 过期
"""
import hashlib
import json
from typing import Dict, Optional, Any
from datetime import datetime, timedelta


class ReportPlanCache:
    """报告规划缓存"""

    def __init__(self, ttl_seconds: int = 3600 * 24):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def _generate_key(self, user_request: str, data_schema: Dict) -> str:
        """生成缓存 key（基于用户请求和数据 schema 的 hash）"""
        schema_str = json.dumps(data_schema, sort_keys=True)
        key_content = f"{user_request}:{schema_str}"
        return hashlib.md5(key_content.encode()).hexdigest()

    def get(self, user_request: str, data_schema: Dict) -> Optional[Dict]:
        """获取缓存"""
        key = self._generate_key(user_request, data_schema)
        if key in self._cache:
            entry = self._cache[key]
            if datetime.now() < entry['expires_at']:
                return entry['data']
            del self._cache[key]
        return None

    def set(self, user_request: str, data_schema: Dict, plan_data: Dict) -> None:
        """设置缓存"""
        key = self._generate_key(user_request, data_schema)
        self._cache[key] = {
            'data': plan_data,
            'expires_at': datetime.now() + self._ttl
        }

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()


# 全局缓存实例
report_plan_cache = ReportPlanCache(ttl_seconds=3600 * 24)  # 24 小时过期

"""
性能日志工具
用于记录和追踪各环节耗时
"""
import time
import logging
from typing import Dict, Optional
from contextlib import contextmanager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('performance')


class PerformanceLogger:
    """性能日志记录器"""

    def __init__(self):
        self.timers: Dict[str, float] = {}
        self.results: Dict[str, float] = {}

    def start(self, name: str) -> None:
        """开始计时"""
        self.timers[name] = time.time()

    def end(self, name: str) -> float:
        """结束计时并返回耗时（秒）"""
        if name not in self.timers:
            raise ValueError(f"Timer '{name}' not started")

        elapsed = time.time() - self.timers[name]
        self.results[name] = elapsed
        del self.timers[name]

        logger.info(f"[PERF] {name}: {elapsed:.3f}s ({elapsed*1000:.1f}ms)")
        return elapsed

    def log(self, name: str, value: float) -> None:
        """直接记录一个值"""
        self.results[name] = value
        logger.info(f"[PERF] {name}: {value:.3f}s ({value*1000:.1f}ms)")

    def get_results(self) -> Dict[str, float]:
        """获取所有记录的结果"""
        return self.results.copy()

    def get_total(self) -> float:
        """获取总耗时"""
        return sum(self.results.values())

    def summary(self) -> str:
        """生成耗时摘要"""
        if not self.results:
            return "无性能数据"

        lines = ["=== 性能分析摘要 ==="]
        for name, elapsed in sorted(self.results.items(), key=lambda x: -x[1]):
            pct = (elapsed / self.get_total()) * 100 if self.get_total() > 0 else 0
            lines.append(f"  {name}: {elapsed:.3f}s ({pct:.1f}%)")
        lines.append(f"  总计：{self.get_total():.3f}s")
        return "\n".join(lines)

    def reset(self) -> None:
        """重置所有数据"""
        self.timers.clear()
        self.results.clear()


# 全局性能记录器实例
_perf_logger = PerformanceLogger()


def get_perf_logger() -> PerformanceLogger:
    """获取全局性能记录器"""
    return _perf_logger


@contextmanager
def track_performance(name: str, perf_logger: Optional[PerformanceLogger] = None):
    """上下文管理器，用于跟踪代码块执行时间"""
    logger = perf_logger or _perf_logger
    logger.start(name)
    try:
        yield
    finally:
        logger.end(name)

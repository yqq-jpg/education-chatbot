# monitoring/metrics.py

import logging
import time
from functools import wraps
import sys
import os

class ChatbotMonitor:
    def __init__(self):
        """初始化监控器"""
        self.response_times = []
        self.error_count = 0
        self.request_count = 0

        # 创建日志目录
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # 设置日志文件路径
        log_file = os.path.join(log_dir, 'chatbot.log')
        
        # 创建监控专用的日志记录器
        self.logger = logging.getLogger('chatbot.monitor')
        self.logger.setLevel(logging.INFO)
        
        # 创建文件处理器
        file_handler = logging.FileHandler('chatbot.log')
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        
        # 创建控制台处理器，但不影响主控制台输出
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)  # 只输出警告及以上级别
        console_formatter = logging.Formatter('Monitor: %(message)s')
        console_handler.setFormatter(console_formatter)
        
        # 添加处理器到日志记录器
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # 防止日志向上传播到根日志记录器
        self.logger.propagate = False
        
    def log_request(self):
        """请求日志装饰器"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                self.request_count += 1
                
                try:
                    # 执行原始函数并保存结果
                    result = func(*args, **kwargs)
                    
                    # 计算响应时间
                    response_time = time.time() - start_time
                    self.response_times.append(response_time)
                    
                    # 记录慢请求
                    if response_time > 5:  # 超过5秒视为慢请求
                        self.logger.warning(f"慢请求警告: 函数 {func.__name__} 执行时间为 {response_time:.2f} 秒")
                    
                    # 返回原始结果
                    return result
                    
                except Exception as e:
                    self.error_count += 1
                    error_msg = f"函数 {func.__name__} 执行出错: {str(e)}"
                    self.logger.error(error_msg)
                    raise
                    
            return wrapper
        return decorator
        
    def get_statistics(self):
        """获取监控统计信息"""
        if not self.response_times:
            return {
                "total_requests": self.request_count,
                "error_count": self.error_count,
                "average_response_time": 0,
                "error_rate": 0
            }
            
        stats = {
            "total_requests": self.request_count,
            "error_count": self.error_count,
            "average_response_time": sum(self.response_times) / len(self.response_times),
            "error_rate": (self.error_count / self.request_count) * 100 if self.request_count > 0 else 0
        }
        
        # 记录高错误率
        if stats["error_rate"] > 10:  # 错误率超过10%
            self.logger.warning(f"高错误率警告: 当前错误率为 {stats['error_rate']:.2f}%")
            
        return stats

# 创建监控器实例
monitor = ChatbotMonitor()
import time
import json
from typing import Dict, Optional
import db

class MemoryManager:
    def __init__(self):
        self.short_term_limit = 10
        self.importance_threshold = 0.7
        
    def calculate_importance(self, message: str, emotion_data: Optional[Dict] = None) -> float:
        score = 0.0
        
        # 长度评分
        if len(message) > 200:
            score += 0.3
        elif len(message) > 100:
            score += 0.2
        else:
            score += 0.1
            
        # 情感评分
        if emotion_data and emotion_data.get('confidence', 0) > 0.8:
            score += 0.3
            
        # 关键词评分
        keywords = ['需要', '问题', '如何', '为什么', 'how', 'why', 'need', 'problem']
        if any(kw in message.lower() for kw in keywords):
            score += 0.2
            
        return min(score, 1.0)
    
    def _save_memory(self, user_id: int, chat_history_id: int, 
                    importance_score: float, memory_type: str) -> int:
        db_connection = db.get_db()
        cursor = db_connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO conversation_memory 
                (user_id, chat_history_id, importance_score, memory_type)
                VALUES (%s, %s, %s, %s)
            """, (user_id, chat_history_id, importance_score, memory_type))
            memory_id = cursor.lastrowid
            db_connection.commit()
            return memory_id
        finally:
            cursor.close()
            
    def _manage_short_term_memory(self, user_id: int):
        db_connection = db.get_db()
        cursor = db_connection.cursor()
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM conversation_memory 
                WHERE user_id = %s AND memory_type = 'short_term'
            """, (user_id,))
            
            count = cursor.fetchone()[0]
            if count > self.short_term_limit:
                cursor.execute("""
                    DELETE FROM conversation_memory 
                    WHERE id IN (
                        SELECT id FROM (
                            SELECT id FROM conversation_memory 
                            WHERE user_id = %s AND memory_type = 'short_term'
                            ORDER BY created_at ASC 
                            LIMIT %s
                        ) as subquery
                    )
                """, (user_id, count - self.short_term_limit))
                db_connection.commit()
        finally:
            cursor.close()
    
    def process_message(self, user_id: int, chat_history_id: int, 
                       message: str, emotion_data: Optional[Dict] = None) -> int:
        # 计算重要性
        importance = self.calculate_importance(message, emotion_data)
        memory_type = 'long_term' if importance >= self.importance_threshold else 'short_term'
        
        # 保存记忆
        memory_id = self._save_memory(user_id, chat_history_id, importance, memory_type)
        
        # 管理短期记忆
        if memory_type == 'short_term':
            self._manage_short_term_memory(user_id)
            
        return memory_id
    
    def get_memory_stats(self, user_id: int) -> Dict:
        db_connection = db.get_db()
        cursor = db_connection.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT 
                    memory_type,
                    COUNT(*) as count,
                    AVG(importance_score) as avg_importance
                FROM conversation_memory
                WHERE user_id = %s
                GROUP BY memory_type
            """, (user_id,))
            return cursor.fetchall()
        finally:
            cursor.close()

    def get_monitoring_stats(self) -> Dict:
        db_connection = db.get_db()
        cursor = db_connection.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_memories,
                    COUNT(CASE WHEN memory_type = 'short_term' THEN 1 END) as short_term_count,
                    COUNT(CASE WHEN memory_type = 'long_term' THEN 1 END) as long_term_count,
                    AVG(importance_score) as avg_importance
                FROM conversation_memory
            """)
            return cursor.fetchone()
        finally:
            cursor.close()
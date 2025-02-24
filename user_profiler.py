from collections import defaultdict
import jieba
import json
import re
from datetime import datetime
import db

class UserProfiler:
    def __init__(self):
        """初始化用户画像系统"""
        self.interests_weight = defaultdict(float)
        
        # 兴趣主题和关键词映射（中英文）
        self.topic_keywords = {
            'technology': ['编程', '软件', '硬件', '代码', '电脑', '程序', '科技', '技术', '人工智能', 
                         'program', 'software', 'hardware', 'tech', 'computer', 'AI', 'coding', 'programming'],
            'science': ['科学', '物理', '化学', '生物', '研究', '实验', '数学', 
                       'science', 'physics', 'chemistry', 'biology', 'research', 'math', 'laboratory'],
            'entertainment': ['娱乐', '电影', '游戏', '音乐', '电视', '动漫', '综艺', 
                            'movie', 'game', 'music', 'entertainment', 'TV', 'anime', 'show'],
            'education': ['教育', '学习', '学校', '考试', '课程', '老师', '学生',
                         'education', 'study', 'school', 'exam', 'course', 'teacher', 'student'],
            'sports': ['运动', '体育', '足球', '篮球', '跑步', '健身', '游泳',
                      'sports', 'football', 'basketball', 'running', 'fitness', 'swimming'],
            'health': ['健康', '医疗', '养生', '保健', '营养', '饮食', '锻炼',
                      'health', 'medical', 'wellness', 'nutrition', 'diet', 'exercise'],
            'finance': ['金融', '投资', '理财', '股票', '基金', '经济', '财务',
                       'finance', 'investment', 'stock', 'fund', 'economy', 'money']
        }
        
        # 个人信息提取
        self.info_patterns = {
            'name': {
                'patterns': [
                    r'我叫([\u4e00-\u9fa5]{2,4})',
                    r'我是([\u4e00-\u9fa5]{2,4})',
                    r'我的名字是([\u4e00-\u9fa5]{2,4})',
                    r'你可以叫我([\u4e00-\u9fa5]{2,4})',
                    r'my name is ([a-zA-Z\s]+)',
                    r"i'm ([a-zA-Z\s]+)",
                    r"i am ([a-zA-Z\s]+)",
                    r"you can call me ([a-zA-Z\s]+)",
                    r"your name\s*(?:is|'s)?\s*([a-zA-Z\s]+)"
                ],
                'keywords': ['叫', '名字', '姓名', 'name', 'call']
            },
            'hobby': {
                'patterns': [
                    r'喜欢([\u4e00-\u9fa5]+)',
                    r'爱好是([\u4e00-\u9fa5]+)',
                    r'热爱([\u4e00-\u9fa5]+)',
                    r'enjoy ([a-zA-Z\s]+ing)',
                    r'like to ([a-zA-Z\s]+)',
                    r'love to ([a-zA-Z\s]+)',
                    r'hobby is ([a-zA-Z\s]+)',
                    r'interested in ([a-zA-Z\s]+)'
                ],
                'keywords': ['喜欢', '爱好', '兴趣', '热爱', 'hobby', 'like', 'enjoy', 'love', 'interest']
            },
            'skill': {
                'patterns': [
                    r'擅长([\u4e00-\u9fa5]+)',
                    r'特长是([\u4e00-\u9fa5]+)',
                    r'精通([\u4e00-\u9fa5]+)',
                    r'good at ([a-zA-Z\s]+ing)',
                    r'skilled in ([a-zA-Z\s]+)',
                    r'specialize in ([a-zA-Z\s]+)',
                    r'expert in ([a-zA-Z\s]+)'
                ],
                'keywords': ['擅长', '特长', '专长', '精通', 'good at', 'skilled', 'expert', 'specialize']
            },
            'occupation': {
                'patterns': [
                    r'我是[一个]*([\u4e00-\u9fa5]{2,6})[职工作者]',
                    r'在([\u4e00-\u9fa5]+)工作',
                    r'做([\u4e00-\u9fa5]+)工作',
                    r'work as (?:a|an)? ?([a-zA-Z\s]+)',
                    r"i'?m (?:a|an)? ?([a-zA-Z\s]+)",
                    r"my job is ([a-zA-Z\s]+)",
                    r"my profession is ([a-zA-Z\s]+)"
                ],
                'keywords': ['工作', '职业', '职务', '从事', 'job', 'work', 'profession', 'occupation']
            }
        }

    def analyze_message(self, user_id, message):
        """分析单条消息,更新用户画像"""
        # 分析兴趣
        self._analyze_interests(message)
        
        # 提取个人信息
        personal_info = self._extract_personal_info(message)
        
        # 保存分析结果
        self._save_profile(user_id, personal_info)
        
        return {
            'interests': dict(self.interests_weight),
            'personal_info': personal_info
        }

    def _analyze_interests(self, message):
        """分析消息中的兴趣相关内容"""
        # 分词处理
        message = message.lower()
        words = jieba.lcut(message) if any('\u4e00' <= char <= '\u9fff' for char in message) else message.split()
        
        # 匹配关键词与主题
        for topic, keywords in self.topic_keywords.items():
            # 对于每个词，检查是否是关键词的一部分
            weight = sum(1 for word in words if any(keyword.lower() in word.lower() for keyword in keywords))
            if weight > 0:
                self.interests_weight[topic] += weight

    def _extract_personal_info(self, message):
        """提取消息中的个人信息"""
        extracted_info = defaultdict(list)
        message = message.strip()
        
        for info_type, patterns in self.info_patterns.items():
            # 正则表达式匹配
            for pattern in patterns['patterns']:
                matches = re.findall(pattern, message, re.IGNORECASE)
                if matches:
                    for match in matches:
                        cleaned_info = match.strip()
                        if cleaned_info and len(cleaned_info) <= 50:
                            extracted_info[info_type].append(cleaned_info)
            
            # 关键词上下文分析
            if any(keyword.lower() in message.lower() for keyword in patterns['keywords']):
                words = jieba.lcut(message) if any('\u4e00' <= char <= '\u9fff' for char in message) else message.split()
                for i, word in enumerate(words):
                    if any(keyword.lower() in word.lower() for keyword in patterns['keywords']) and i + 1 < len(words):
                        context = ' '.join(words[i+1:i+4])
                        if context and len(context) <= 50:
                            extracted_info[info_type].append(context)
        
        return dict(extracted_info)

    def _save_profile(self, user_id, personal_info):
        """保存或更新用户画像"""
        db_connection = db.get_db()
        cursor = db_connection.cursor(dictionary=True)
        try:
            # 获取现有画像
            cursor.execute("""
                SELECT interests, personal_info 
                FROM user_profiles 
                WHERE user_id = %s
            """, (user_id,))
            result = cursor.fetchone()
            
            if result:
                # 更新兴趣权重
                existing_interests = json.loads(result['interests']) if result['interests'] else {}
                for topic, weight in self.interests_weight.items():
                    existing_interests[topic] = existing_interests.get(topic, 0) + weight
                
                # 更新个人信息
                existing_info = json.loads(result['personal_info']) if result['personal_info'] else {}
                for info_type, values in personal_info.items():
                    if info_type in existing_info:
                        # 合并新旧信息并去重
                        combined_values = existing_info[info_type] + values
                        existing_info[info_type] = list(dict.fromkeys(combined_values))  # 保持顺序的去重
                    else:
                        existing_info[info_type] = values
                
                updated_interests = existing_interests
                updated_info = existing_info
            else:
                updated_interests = dict(self.interests_weight)
                updated_info = personal_info
            
            # 保存更新后的画像
            cursor.execute("""
                INSERT INTO user_profiles (user_id, interests, personal_info, last_updated)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                interests = VALUES(interests),
                personal_info = VALUES(personal_info),
                last_updated = VALUES(last_updated)
            """, (user_id, json.dumps(updated_interests), json.dumps(updated_info), datetime.now()))
            
            db_connection.commit()
            
        finally:
            cursor.close()

    def get_profile(self, user_id):
        """获取用户画像"""
        db_connection = db.get_db()
        cursor = db_connection.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT interests, personal_info 
                FROM user_profiles 
                WHERE user_id = %s
            """, (user_id,))
            result = cursor.fetchone()
            
            if result:
                return {
                    'interests': json.loads(result['interests']) if result['interests'] else {},
                    'personal_info': json.loads(result['personal_info']) if result['personal_info'] else {}
                }
            return {'interests': {}, 'personal_info': {}}
            
        finally:
            cursor.close()

    def generate_personalized_response(self, user_id, base_response):
        """生成个性化回复"""
        profile = self.get_profile(user_id)
        prefix = ""
        
        # 添加称呼
        if 'name' in profile['personal_info'] and profile['personal_info']['name']:
            name = profile['personal_info']['name'][0]
            prefix += f"{name}，"
            
        # 添加身份标识
        if 'occupation' in profile['personal_info'] and profile['personal_info']['occupation']:
            occupation = profile['personal_info']['occupation'][0]
            prefix += f"you are{occupation}，"
            
        # 添加兴趣相关
        if profile['interests']:
            top_interest = max(profile['interests'].items(), key=lambda x: x[1])[0]
            interest_prefix = {
                'technology': "",
                'science': "",
                'entertainment': "",
                'education': "",
                'sports': "",
                'health': "",
                'finance': "",
                'news': ""
            }.get(top_interest, "")
            prefix += interest_prefix
            
        return prefix + base_response if prefix else base_response
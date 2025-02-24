from transformers import pipeline
import numpy as np
from typing import Dict, Optional, Tuple
from functools import lru_cache

class EmotionAnalyzer:
    def __init__(self):
        # 初始化情感分析模型
        self.classifier = pipeline(
            "sentiment-analysis",
            model="nlptown/bert-base-multilingual-uncased-sentiment",
            framework="pt"
        )
        # 初始化缓存
        self.cache = {}
        
        # 定义情感响应模板
        self.response_templates = {
            'POSITIVE': [
                "可以"
            ],
            'NEGATIVE': [
                "好吧。"
            ],
            'NEUTRAL': [
                "我明白了。",
                "好的，我懂了。"
            ]
        }

        self.en_response_templates = {
            'POSITIVE': [
                "sounds good",
                "That's wonderful!",
                "This is great news!"
            ],
            'NEGATIVE': [
                "Alright",
            ],
            'NEUTRAL': [
                "I see.",
                "Hmm."
            ]
        }

    @lru_cache(maxsize=1000)  # 缓存最近的1000个结果
    def analyze_emotion(self, text: str, lang: str = 'zh') -> Tuple[str, float]:
        """
        分析文本情感并返回情感标签和置信度，使用缓存加速重复查询
        """
        try:
            # 如果文本太长，只分析前512个字符
            truncated_text = text[:512]
            
            # 检查缓存
            cache_key = f"{truncated_text}_{lang}"
            if cache_key in self.cache:
                return self.cache[cache_key]
            
            result = self.classifier(truncated_text)[0]
            score = int(result['label'].split()[0])
            
            if score >= 4:
                emotion = 'POSITIVE'
                confidence = result['score']
            elif score <= 2:
                emotion = 'NEGATIVE'
                confidence = result['score']
            else:
                emotion = 'NEUTRAL'
                confidence = result['score']
            
            # 保存到缓存
            self.cache[cache_key] = (emotion, confidence)
            
            # 打印分析结果
            print(f"""Emotion analysis results:
                  text: {truncated_text[:100]}...
                  emotion: {emotion}   
                  Confidence level: {confidence}""")            
            return emotion, confidence
            
        except Exception as e:
            print(f"Emotion analysis error: {str(e)}")
            return 'NEUTRAL', 0.0

    def get_emotional_response(self, emotion: str, confidence: float, lang: str = 'zh') -> Optional[str]:
        try:
            templates = self.response_templates if lang == 'zh' else self.en_response_templates
            if emotion in templates:
                # 根据置信度决定是否添加情感回复
                if confidence > 0.5:
                    return np.random.choice(templates[emotion])
            return None
        except Exception as e:
            print(f"Error generating emotional response: {str(e)}")
            return None

    def analyze_and_respond(self, text: str, lang: str = 'zh') -> Dict:
        """
        分析文本情感并生成回复，添加详细日志
        """
        emotion, confidence = self.analyze_emotion(text, lang)
        response = self.get_emotional_response(emotion, confidence, lang)
        
        # 添加详细日志
        print(f"""Emotion analysis results:
              - inputtext: {text[:100]}...
              - emotion: {emotion}
              - Confidence level: {confidence}
              - Generate reply: {response}""")
        return {
            'emotion': emotion,
            'confidence': confidence,
            'response': response
        }
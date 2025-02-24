from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
import datetime
import os
import torch
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import json
import threading
import db
from monitoring.metrics import monitor
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

app = Flask(__name__)
app.secret_key = os.urandom(24)
is_processing = threading.Lock()

from emotion import EmotionAnalyzer
from memory_manager import MemoryManager

emotion_analyzer = EmotionAnalyzer()
memory_manager = MemoryManager()

# 初始化文本向量化模型
device = 'cuda' if torch.cuda.is_available() else 'cpu'
model = SentenceTransformer('intfloat/multilingual-e5-large', device=device)

def vectorization_text(texts):
    # 文本向量化并去除多于字符
    standar = [text for text in texts if isinstance(text, str) and text]
    return model.encode(standar)

def Retrieve_historical_records(user_message, user_id, maxitems=5, similar=0.6):
    # 从数据库中获取所有历史记录
    db_connection = db.get_db()
    cursor = db_connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT role, content, tokenized_content, timestamp 
        FROM chat_history
        WHERE user_id = %s AND timestamp < NOW()
        ORDER BY timestamp ASC
    """, (user_id,))
    rows = cursor.fetchall()
    cursor.close()

    if not rows:
        return []

    # 格式化历史记录
    history = [
        {
            "role": "user" if row["role"] == "user" else "assistant",
            "content": row["content"],
            "timestamp": row["timestamp"].isoformat() if isinstance(row["timestamp"], datetime.datetime) else row["timestamp"]
        }
        for row in rows
    ]

    # 获取最近的两轮消息（用户和助手）
    recent_history = []
    temp_user_message = None

    for item in history[::-1]:  # 从最新的记录开始处理
        if item["role"] == "user":
            temp_user_message = item
        elif item["role"] == "assistant" and temp_user_message:
            recent_history.append(temp_user_message)
            recent_history.append(item)
            temp_user_message = None
        if len(recent_history) >= 4:  # 最近的n轮，（用户+助手）
            break

    # 反转让最近最先显示
    recent_history.reverse()

    # 将所有历史记录内容向量化
    history_texts = [item["content"] for item in history]
    history_vectors = vectorization_text(history_texts)

    query_vector = vectorization_text([user_message])[0]

    similarities = cosine_similarity([query_vector], history_vectors)[0]

    relevant_indices = [idx for idx, sim in enumerate(similarities) if sim >= similar]

    print(f"向量化查询到的符合用户输入的历史记录数量: {len(relevant_indices)}")# 测试

    relevant_history = [(history[idx], similarities[idx]) for idx in relevant_indices]
    relevant_history.sort(key=lambda x: x[1], reverse=True)
    relevant_history = [item[0] for item in relevant_history[:maxitems]]

    final_results = []
    seen_content = set()

    # 添加历史记录
    for item in recent_history:
        content = item["content"]
        if content not in seen_content:
            final_results.append(item)
            seen_content.add(content)

    for item in relevant_history:
        content = item["content"]
        if content not in seen_content:
            final_results.append(item)
            seen_content.add(content)

    return final_results

@app.route("/")
def home():
    if "user_id" in session:
        return render_template("index.html")
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return "Username and password cannot be empty", 400

        hashed_password = generate_password_hash(password)

        db_connection = db.get_db()
        cursor = db_connection.cursor()
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, hashed_password))
        db_connection.commit()
        cursor.close()

        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

        db_connection = db.get_db()
        cursor = db_connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            return redirect(url_for("home"))

        flash("登录失败。用户不存在或密码错误。")
        return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop('user_id', None)
    return redirect(url_for("login"))

# 添加了用户画像
from user_profiler import UserProfiler
user_profiler = UserProfiler()

@app.route("/api/chat", methods=["POST"])
@monitor.log_request()
def api_chat():
    if "user_id" not in session:
        return jsonify({"error": "User not logged in"}), 401

    if is_processing.locked():
        return jsonify({"response": "Thinking about it, please try again later"}), 429

    data = request.json
    user_message = data.get("message")
    user_id = session['user_id']

    if not user_message:
        return jsonify({"error": "Message cannot be empty"}), 400

    with is_processing:
        try:
            db_connection = db.get_db()
            cursor = db_connection.cursor()

            # 保存用户消息
            tokenized_content = db.tokenize_chinese(user_message) if db.is_chinese(user_message) else user_message
            timestamp = datetime.datetime.now().isoformat()
            
            cursor.execute("""
                INSERT INTO chat_history 
                (user_id, role, content, tokenized_content, timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, "user", user_message, tokenized_content, timestamp))
            
            chat_history_id = cursor.lastrowid

            # 情感分析
            lang = 'en' if not db.is_chinese(user_message) else 'zh'
            emotion_result = emotion_analyzer.analyze_and_respond(user_message, lang)

            # 处理记忆
            memory_id = memory_manager.process_message(
                user_id, 
                chat_history_id, 
                user_message, 
                emotion_result
            )

            cursor.execute("""
                UPDATE chat_history 
                SET memory_id = %s 
                WHERE id = %s
            """, (memory_id, chat_history_id))

            # 获取相关历史记录
            relevant_history = Retrieve_historical_records(user_message, user_id)

            # 分析用户消息,更新用户画像
            profile_analysis = user_profiler.analyze_message(user_id, user_message)
            
            # 获取ai响应
            ai_response = chat_with_baidu_ai(
                relevant_history + [{"role": "user", "content": user_message}]
            )

            # 确保ai_response是字典类型并且包含必要的键
            if isinstance(ai_response, str):
                ai_response = {"content": ai_response, "reasoning_content": None}

            # 添加情感回应和个性化内容
            response_content = ai_response["content"]
            base_response = f"{emotion_result['response']} {response_content}" if emotion_result.get('response') else response_content
            final_response = user_profiler.generate_personalized_response(user_id, base_response)

            # 将推理内容和最终回复组合在一起
            combined_response = {
                "content": final_response,
                "reasoning_content": ai_response.get("reasoning_content")
            }

            # 保存助手回复
            cursor.execute("""
                INSERT INTO chat_history 
                (user_id, role, content, timestamp)
                VALUES (%s, %s, %s, %s)
            """, (user_id, "assistant", final_response, datetime.datetime.now().isoformat()))
            
            assistant_history_id = cursor.lastrowid
            
            # 处理助手回复的记忆
            assistant_memory_id = memory_manager.process_message(
                user_id, 
                assistant_history_id, 
                final_response
            )
            # 确定字段
            cursor.execute("""
                UPDATE chat_history 
                SET memory_id = %s 
                WHERE id = %s
            """, (assistant_memory_id, assistant_history_id))

            db_connection.commit()
            return jsonify({"response": combined_response})

        except Exception as e:
            print(f"Error in api_chat: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            cursor.close()

# API_KEY = 'bce-v3/ALTAK-eASYWhGg41I2SP1kg1hPu/6ff0405e82db2c1f198b8bbfc9f226798eb1acc3'
# 使用本地Ollama模型的聊天接口
def chat_with_baidu_ai(history):
    try:
        url = "http://localhost:11434/api/chat"
        
        current_question = history[-1]["content"]
        
        system_message = f"""Here are the relevant historical dialogue records and current issues. Please pay special attention:
        - The current issue is:{current_question}
        - The historical records are for reference only and mainly answer the current question
        """
        
        messages = []
        messages.append({"role": "system", "content": system_message})
        
        for i, item in enumerate(history[:-1]):
            messages.append({
                "role": item["role"],
                "content": f"[historical records {i+1}] {item['content']}"
            })
        
        messages.append({
            "role": "user",
            "content": current_question
        })
        
        payload = {
            "model": "deepseek-r1:1.5b",
            "messages": messages,
            "stream": False,
        }
        
        print("Request payload:", json.dumps(payload, ensure_ascii=False, indent=4))
        
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        print("Response body:", response.text)
        
        response_data = response.json()
        
        # 返回格式化的响应字典
        if "message" in response_data:
            return {
                "content": response_data["message"]["content"],
                "reasoning_content": None
            }
        else:
            return {
                "content": "未收到有效回复",
                "reasoning_content": None
            }
            
    except requests.RequestException as e:
        print(f"网络请求错误: {e}")
        return {"content": f"网络请求错误: {e}", "reasoning_content": None}
    except json.JSONDecodeError:
        print("响应解析失败")
        return {"content": "响应解析失败", "reasoning_content": None}
    except Exception as e:
        print(f"未知错误: {e}")
        return {"content": f"发生错误: {e}", "reasoning_content": None}

@app.route("/api/history", methods=["GET"])
def get_history():
    # 确保登录状态
    if "user_id" not in session:
        return jsonify({"error": "User not logged in"}), 401

    try:
        user_id = session["user_id"]
        db_connection = db.get_db()
        cursor = db_connection.cursor()

        # 获取用户的聊天历史记录
        cursor.execute("""
            SELECT role, content FROM chat_history
            WHERE user_id = %s
            ORDER BY timestamp ASC
        """, (user_id,))
        rows = cursor.fetchall()
        cursor.close()

        # 格式化为前端需要的格式
        history = [{"role": "user" if row[0] == "user" else "assistant", "content": row[1]} for row in rows]

        return jsonify({"history": history})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

#添加搜索功能
from googlesearch import search
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import List, Dict, Tuple
import time

class SearchResult:
    def __init__(self, url: str, title: str = "", abstract: str = ""):
        self.url = url
        self.title = title
        self.abstract = abstract

    def to_dict(self) -> Dict:
        return {
            "url": self.url,
            "title": self.title,
            "abstract": self.abstract
        }

class SearchEngine:
    def __init__(self):
        self._request_lock = threading.Lock()

    # 特殊处理中文乱码
    def _decode_url(self, url: str) -> str:
        try:
            from urllib.parse import unquote
            return unquote(url, encoding='utf-8')
        except Exception as e:
            print(f"URL decode error: {str(e)}")
            return url

    # 执行搜索查看结果
    def search(self, query: str, num_results: int = 5) -> List[Dict]:
        results = []
        tries = 0
        max_tries = 3

        while tries < max_tries and len(results) < num_results:
            try:
                search_query = query
                print(f"Searching with query: {search_query}")
                
                with self._request_lock:
                    search_results = list(search(search_query, num_results=num_results * 2))
                    print(f"Found raw results: {len(search_results)}")
                    time.sleep(2)
                
                for url in search_results:
                    if len(results) >= num_results:
                        break
                    
                    # 解码
                    decoded_url = self._decode_url(url)
                    if not self._is_valid_url(decoded_url):
                        continue
                    
                    title, abstract = self._fetch_page_content(decoded_url)
                    if title and abstract:
                        results.append({
                            "url": decoded_url,
                            "title": title,
                            "abstract": abstract
                        })
                        print(f"Added result: {title[:50]}...")
                
                if results:
                    break
                
            except Exception as e:
                print(f"Search error (attempt {tries + 1}): {str(e)}")
                tries += 1
                time.sleep(2)
            
        return results

    # 获取页面内内容
    def _fetch_page_content(self, url: str) -> Tuple[str, str]:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Connection': 'keep-alive'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            # 检测网页编码
            if response.encoding.lower() == 'iso-8859-1':
                encoding = response.apparent_encoding
                response.encoding = encoding
            
            response.raise_for_status()
            content = response.text
            soup = BeautifulSoup(content, 'html.parser')
            title = soup.title.string if soup.title else ""
            main_content = []
            for tag in soup.find_all(['p', 'article'], class_=lambda x: x and ('content' in x.lower() or 'article' in x.lower())):
                text = tag.get_text().strip()
                if len(text) > 50:
                    main_content.append(text)
            
            if not main_content:
                for p in soup.find_all('p'):
                    text = p.get_text().strip()
                    if len(text) > 50:
                        main_content.append(text)
            
            abstract = ' '.join(main_content[:2])
            if len(abstract) > 500:
                abstract = abstract[:497] + "..."
            
            return title.strip(), abstract.strip()
            
        except Exception as e:
            print(f"Error fetching {url}: {str(e)}")
            return "", ""
            
    def _is_valid_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            blocked_domains = {
                'youtube.com', 'facebook.com', 'twitter.com',
                'instagram.com', 'pinterest.com', 'reddit.com'
            }
            return parsed.netloc not in blocked_domains and len(url) < 500
        except:
            return False

@app.route("/api/search", methods=["GET"])
def api_search():
    if "user_id" not in session:
        return jsonify({"error": "User not logged in"}), 401

    query = request.args.get("q", "")
    if not query:
        return jsonify({"error": "Query cannot be empty"}), 400

    print(f"Received search query: {query}")

    try:
        search_engine = SearchEngine()
        search_results = search_engine.search(query)
        
        if not search_results:
            return jsonify({
                "search_results": [],
                "llm_response": "No relevant results found."
            })
        
        # 构建提示词区分搜索内容和用户提问
        prompt = f"""[User Question]            
                {query}
                [Search Results]"""

        for i, result in enumerate(search_results, 1):
            # 确保UTF-8 的编码格式
            title = result['title'].encode('utf-8', errors='ignore').decode('utf-8')
            abstract = result['abstract'].encode('utf-8', errors='ignore').decode('utf-8')
            url = result['url'].encode('utf-8', errors='ignore').decode('utf-8')
            
            prompt += f"""
            Result {i}:
            - Title: {title}
            - Content: {abstract}
            - URL: {url}"""

        prompt += """
        [System Instruction]
        Please provide answers to the user's questions based on the above search results.
        You can decide the appropriate language for the response based on the user's question."""

        # 调用ai进行总结
        summary = chat_with_baidu_ai([
            {"role": "user", "content": prompt}
        ])

        # 保存到历史记录
        db_connection = db.get_db()
        cursor = db_connection.cursor()
        user_id = session['user_id']
        timestamp = datetime.datetime.now().isoformat()
        
        # 标记历史记录
        search_record = f"[Search Request] {query}"
        response_record = f"[Search Response] {summary}"
        
        cursor.execute(
            "INSERT INTO chat_history (user_id, role, content, timestamp) VALUES (%s, 'user', %s, %s), (%s, 'assistant', %s, %s)",
            (user_id, search_record, timestamp, user_id, response_record, timestamp)
        )
        
        db_connection.commit()
        cursor.close()

        return jsonify({
            "search_results": search_results,
            "llm_response": summary
        })

    except Exception as e:
        print(f"Search API error: {str(e)}")
        return jsonify({"error": f"Search error: {str(e)}"}), 500

# 新闻推送功能
import feedparser
import random

def get_feed_with_retry(url, backup_url=None, max_retries=3):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/xml,application/rss+xml,text/xml,application/atom+xml'
    }
    
    urls_to_try = [url]
    if backup_url:
        urls_to_try.append(backup_url)
        
    for current_url in urls_to_try:
        for i in range(max_retries):
            try:
                response = requests.get(current_url, headers=headers, timeout=15)
                response.encoding = 'utf-8'
                
                if response.status_code == 200:
                    feed = feedparser.parse(response.content)
                    if feed.entries:
                        return feed

            except Exception as e:
                print(f"Attempt {i+1} failed for {current_url}: {str(e)}")
                if i < max_retries - 1:
                    time.sleep(1)
                    
    return None

def get_article_content(url, max_retries=2):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    
    for i in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = response.apparent_encoding or 'utf-8'
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 移除不需要的元素
                for tag in soup(['script', 'style', 'nav', 'header', 'footer']):
                    tag.decompose()
                
                # 获取主要内容
                content = ""
                main_content = soup.find(['article', 'main']) or soup.find(class_=lambda x: x and ('content' in x.lower() or 'article' in x.lower()))
                
                if main_content:
                    paragraphs = main_content.find_all('p')
                else:
                    paragraphs = soup.find_all('p')
                
                for p in paragraphs:
                    text = p.get_text().strip()
                    if len(text) > 50:
                        content += text + "\n"
                
                return content[:1500]  # 限制内容长度
                
        except Exception as e:
            print(f"Attempt {i+1} failed to get article content: {str(e)}")
            if i < max_retries - 1:
                time.sleep(1)
                
    return None

# ai请求处理
def safe_ai_request(prompt, max_retries=2):
    for i in range(max_retries):
        try:
            response = chat_with_baidu_ai([
                {"role": "user", "content": prompt}
            ])
            
            # 检查响应的类型
            if isinstance(response, dict):
                content = response.get('content', '')
                if content and isinstance(content, str):
                    return content
                
            elif isinstance(response, str):
                return response
                
            # 如果响应格式不符合预期，返回一个默认消息
            return "请点击链接查看详细内容"
            
        except Exception as e:
            print(f"AI request attempt {i+1} failed: {str(e)}")
            if i < max_retries - 1:
                time.sleep(1)
                
    return "Unable to generate summary"

@app.route("/api/push-news", methods=["GET"])
def push_news():
    if "user_id" not in session:
        return jsonify({"error": "User not logged in"}), 401
        
    try:
        news_sources = {
            "bbc": {
                "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
                "backup_url": "http://feeds.bbci.co.uk/news/rss.xml",
                "language": "en"
            },
            "europa": {
                "url": "https://european-union.europa.eu/news-feed.xml",
                "backup_url": "https://ec.europa.eu/commission/presscorner/api/rss",
                "language": "en"
            },
            "people": {
                "url": "http://www.people.com.cn/rss/world.xml",
                "backup_url": "http://politics.people.com.cn/rss/politics.xml",
                "language": "zh"
            }
        }
        
        news_items = []
        
        for source, info in news_sources.items():
            try:
                feed = get_feed_with_retry(info["url"], info["backup_url"])
                
                if feed and feed.entries:

                    entry = random.choice(feed.entries[:5])
                    # 获取详细内容
                    full_content = get_article_content(entry.link) or entry.get('description', '')
                    # 准备新闻内容给AI
                    content = f"""Title: {entry.title}
                        Content: {full_content}"""
                    
                    # 区分中英双语
                    if info["language"] == "zh":
                        prompt = f"""请对这篇新闻进行简要分析：
                        1. 用1-2句话总结主要内容
                        2. 指出重要信息点

                        新闻内容：
                        {content}
                        """
                    else:
                        prompt = f"""Please analyze this news briefly:
                        1. Summarize the main content in 1-2 sentences
                        2. Point out key information

                        News content:
                        {content}
                        """                    
                    # 调用AI进行分析
                    summary = safe_ai_request(prompt)
                    # 确保所有必需字段都有值
                    news_items.append({
                        "source": source,
                        "title": entry.title or "无标题",
                        "summary": summary if isinstance(summary, str) else "请点击链接查看详细内容",
                        "url": entry.link or "#",
                        "language": info["language"],
                        "timestamp": datetime.datetime.now().isoformat()
                    })
                    
            except Exception as e:
                print(f"Error processing {source} news: {str(e)}")
                continue
        
        if not news_items:
            return jsonify({"error": "No news items could be fetched"}), 500
            
        # 保存到聊天历史
        db_connection = db.get_db()
        cursor = db_connection.cursor()
        user_id = session['user_id']
        timestamp = datetime.datetime.now().isoformat()
        
        # 将推送的新闻保存为一条系统信息
        news_content = "Pushed News:\n" + "\n".join([
            f"{item['source'].upper()}: {item['title']}" for item in news_items
        ])
        
        cursor.execute(
            "INSERT INTO chat_history (user_id, role, content, timestamp) VALUES (%s, 'assistant', %s, %s)",
            (user_id, news_content, timestamp)
        )
        
        db_connection.commit()
        cursor.close()
        
        return jsonify({"news_items": news_items})
        
    except Exception as e:
        print(f"Push news error: {str(e)}")
        return jsonify({"error": str(e)}), 500

# 用户画像端点
@app.route("/api/user/profile", methods=["GET"])
def get_user_profile():
    if "user_id" not in session:
        return jsonify({"error": "用户未登录"}), 401

    try:
        user_id = session['user_id']
        profile = user_profiler.get_profile(user_id)
        
        response_data = {
            "profile": profile,
            "top_interests": sorted(
                profile['interests'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:3] if profile['interests'] else [],
            "personal_info_fields": list(profile['personal_info'].keys()) if profile['personal_info'] else []
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"获取用户画像时出错: {e}")
        return jsonify({"error": str(e)}), 500

# 文本文件识别
from file_handler import FileHandler
from werkzeug.utils import secure_filename

# 添加配置可处理扩展名
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'pptx', 'csv', 'xlsx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'user_id' not in session:
        return jsonify({"error": "User not logged in"}), 401
        
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400
        
    try:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        # 处理文件
        file_handler = FileHandler()
        result = file_handler.process_file(file_path)
        # 处理后删除文件
        os.remove(file_path)
        
        if result['status'] == 'success':
            # 存储到聊天历史
            db_connection = db.get_db()
            cursor = db_connection.cursor()
            
            # 保存操作
            cursor.execute("""
                INSERT INTO chat_history 
                (user_id, role, content, timestamp)
                VALUES (%s, %s, %s, %s)
            """, (
                session['user_id'],
                "user",
                f"[Uploaded file: {filename}]",
                datetime.datetime.now().isoformat()
            ))

            cursor.execute("""
                INSERT INTO chat_history 
                (user_id, role, content, timestamp)
                VALUES (%s, %s, %s, %s)
            """, (
                session['user_id'],
                "assistant",
                f"File content extracted:\n\n{result['content'][:1000]}..." if len(result['content']) > 1000 else result['content'],
                datetime.datetime.now().isoformat()
            ))
            
            db_connection.commit()
            cursor.close()
            
            return jsonify({
                "status": "success",
                "content": result['content'],
                "metadata": result['metadata']
            })
        else:
            return jsonify({
                "status": "error",
                "message": result.get('message', 'Unknown error occurred')
            }), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 图片识别
from image_handler import HuggingFaceImageHandler

image_handler = HuggingFaceImageHandler()

@app.route('/api/image/upload', methods=['POST'])
def upload_image():
    if 'user_id' not in session:
        return jsonify({"error": "用户未登录"}), 401
        
    if 'file' not in request.files:
        return jsonify({"error": "未收到文件"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "未选择文件"}), 400
        
    file_format = file.filename.rsplit('.', 1)[1].lower()
    if file_format not in image_handler.supported_formats:
        return jsonify({"error": "Unsupported image format"}), 400
        
    try:
        image_data = file.read()
        result = image_handler.process_image(image_data, file_format)
        
        if result['status'] == 'success':
            # 保存到历史记录
            db_connection = db.get_db()
            cursor = db_connection.cursor()
            
            # 保存用户的图片上传动作
            cursor.execute(
                "INSERT INTO chat_history (user_id, role, content, timestamp) VALUES (%s, %s, %s, %s)",
                (session['user_id'], "user", f"[上传图片: {file.filename}]", datetime.datetime.now().isoformat())
            )
            
            # 保存识别结果
            cursor.execute(
                "INSERT INTO chat_history (user_id, role, content, timestamp) VALUES (%s, %s, %s, %s)",
                (session['user_id'], "assistant", result['description'], datetime.datetime.now().isoformat())
            )
            
            db_connection.commit()
            cursor.close()
            
            return jsonify(result)
        else:
            return jsonify(result), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    db.init_app(app)
    with app.app_context():
        db.update_tokenized_content()
    app.run(debug=True)
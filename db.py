import mysql.connector
from flask import g
import jieba

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "123456",
    "database": "chatbot_project",
}

def get_db():
    if "db" not in g:
        g.db = mysql.connector.connect(**DB_CONFIG)
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_app(app):
    app.teardown_appcontext(close_db)

# 为聊天记录表添加 FULLTEXT 索引
def add_fulltext_index():

    db_connection = get_db()
    cursor = db_connection.cursor()
    cursor.execute("ALTER TABLE chat_history ADD FULLTEXT(content);")
    db_connection.commit()
    cursor.close()

# 全文检索
def search_fulltext(query):

    db_connection = get_db()
    cursor = db_connection.cursor(dictionary=True)
    try:

        cursor.execute("""
            SELECT role, content, timestamp 
            FROM chat_history
            WHERE MATCH(content) AGAINST (%s IN BOOLEAN MODE)
            ORDER BY 
                (MATCH(content) AGAINST (%s IN BOOLEAN MODE)) DESC,
                timestamp DESC
            LIMIT 50  # 扩大返回结果数
        """, (f"+\"{query}\"*", f"+\"{query}\"*"))
        return cursor.fetchall()
    finally:
        cursor.close()

# 模糊匹配
def fuzzy_search(query, threshold=60):
    db_connection = get_db()
    cursor = db_connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT role, content, timestamp 
            FROM chat_history
            ORDER BY timestamp DESC
            LIMIT 150
        """)
        rows = cursor.fetchall()
        from rapidfuzz import process, fuzz
        matched_rows = []
        for row in rows:
            score = fuzz.token_sort_ratio(query, row["content"])
            if score >= threshold:
                matched_rows.append(row)
        return matched_rows
    finally:
        cursor.close()

# 处理中文
def tokenize_chinese(text):
    return " ".join(jieba.cut(text))

def is_chinese(text):
    return any('\u4e00' <= char <= '\u9fff' for char in text)

def update_tokenized_content():
    """
    更新数据库中`tokenized_content`字段为NULL的记录。
    对中文内容进行分词，并将分词结果存储到`tokenized_content`字段中。
    """
    db_connection = get_db()
    cursor = db_connection.cursor()

    # 获取所有`tokenized_content`为NULL的记录
    cursor.execute("SELECT id, content FROM chat_history WHERE tokenized_content IS NULL")
    rows = cursor.fetchall()

    # 更新`tokenized_content`字段
    for row in rows:
        record_id, content = row
        tokenized_content = tokenize_text(content)
        cursor.execute("UPDATE chat_history SET tokenized_content = %s WHERE id = %s", (tokenized_content, record_id))

    db_connection.commit()
    cursor.close()

def tokenize_text(text):
    """根据语言类型进行分词"""
    if is_chinese(text):
        return " ".join(jieba.cut(text))
    else:
        return text
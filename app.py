import os
import hmac
import hashlib
import base64
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# =============================================
# 🔧 設定區（請填入你的 LINE 資訊）
# =============================================
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "你的Channel_Secret")

# =============================================
# 資料庫初始化
# =============================================
def init_db():
    conn = sqlite3.connect("blocked_users.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS blocked_users (
            user_id TEXT PRIMARY KEY,
            blocked_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS follow_users (
            user_id TEXT PRIMARY KEY,
            followed_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# =============================================
# 驗證 LINE 簽章（安全性）
# =============================================
def verify_signature(body: bytes, signature: str) -> bool:
    secret = LINE_CHANNEL_SECRET.encode("utf-8")
    hash_digest = hmac.new(secret, body, hashlib.sha256).digest()
    expected = base64.b64encode(hash_digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)

# =============================================
# Webhook 接收端點
# =============================================
@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")

    # 驗證簽章
    if not verify_signature(body, signature):
        return jsonify({"error": "Invalid signature"}), 403

    data = json.loads(body)
    events = data.get("events", [])

    conn = sqlite3.connect("blocked_users.db")
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for event in events:
        event_type = event.get("type")
        source = event.get("source", {})
        user_id = source.get("userId")

        if not user_id:
            continue

        if event_type == "follow":
            # 用戶加入 → 記錄為追蹤中，並從黑名單移除
            c.execute("INSERT OR IGNORE INTO follow_users (user_id, followed_at) VALUES (?, ?)", (user_id, now))
            c.execute("DELETE FROM blocked_users WHERE user_id = ?", (user_id,))

        elif event_type == "unfollow":
            # 用戶封鎖/取消追蹤 → 加入黑名單
            c.execute("INSERT OR REPLACE INTO blocked_users (user_id, blocked_at) VALUES (?, ?)", (user_id, now))
            c.execute("DELETE FROM follow_users WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"}), 200

# =============================================
# 管理後台（查看黑名單）
# =============================================
@app.route("/admin", methods=["GET"])
def admin():
    conn = sqlite3.connect("blocked_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id, blocked_at FROM blocked_users ORDER BY blocked_at DESC")
    blocked = c.fetchall()
    c.execute("SELECT COUNT(*) FROM follow_users")
    follow_count = c.fetchone()[0]
    conn.close()

    html = """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>LINE 黑名單管理後台</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: 'Segoe UI', sans-serif; background: #f0f4f8; color: #333; }
            .header {
                background: linear-gradient(135deg, #06C755, #039B42);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 { font-size: 24px; margin-bottom: 5px; }
            .header p { opacity: 0.85; font-size: 14px; }
            .stats {
                display: flex;
                gap: 20px;
                padding: 20px;
                justify-content: center;
                flex-wrap: wrap;
            }
            .stat-card {
                background: white;
                border-radius: 12px;
                padding: 20px 30px;
                text-align: center;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                min-width: 160px;
            }
            .stat-card .num { font-size: 36px; font-weight: bold; }
            .stat-card .num.red { color: #e53e3e; }
            .stat-card .num.green { color: #06C755; }
            .stat-card .label { font-size: 13px; color: #666; margin-top: 5px; }
            .container { padding: 0 20px 30px; max-width: 900px; margin: 0 auto; }
            .section-title {
                font-size: 16px;
                font-weight: bold;
                margin: 20px 0 10px;
                color: #444;
            }
            table { width: 100%; border-collapse: collapse; background: white;
                    border-radius: 12px; overflow: hidden;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
            th { background: #f7fafc; padding: 12px 16px; text-align: left;
                 font-size: 13px; color: #555; border-bottom: 1px solid #e2e8f0; }
            td { padding: 12px 16px; font-size: 13px; border-bottom: 1px solid #f0f0f0; }
            tr:last-child td { border-bottom: none; }
            .badge {
                background: #fee2e2; color: #c53030;
                padding: 3px 10px; border-radius: 20px; font-size: 12px;
            }
            .empty { text-align: center; padding: 30px; color: #aaa; font-size: 14px; }
            .note {
                background: #fffbeb; border-left: 4px solid #f59e0b;
                padding: 12px 16px; border-radius: 6px; font-size: 13px;
                margin-top: 20px; color: #78350f;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🚫 LINE 黑名單管理後台</h1>
            <p>自動追蹤封鎖或取消追蹤的用戶，節省推播費用</p>
        </div>
        <div class="stats">
            <div class="stat-card">
                <div class="num red">{{ blocked_count }}</div>
                <div class="label">封鎖/取消追蹤人數</div>
            </div>
            <div class="stat-card">
                <div class="num green">{{ follow_count }}</div>
                <div class="label">目前追蹤中人數</div>
            </div>
        </div>
        <div class="container">
            <div class="section-title">封鎖用戶清單</div>
            {% if blocked %}
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>用戶 ID</th>
                        <th>封鎖時間</th>
                        <th>狀態</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in blocked %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        <td style="font-family:monospace; font-size:12px;">{{ row[0] }}</td>
                        <td>{{ row[1] }}</td>
                        <td><span class="badge">已封鎖</span></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty">🎉 目前沒有封鎖用戶記錄</div>
            {% endif %}
            <div class="note">
                ⚠️ 注意：此系統只能記錄「部署後」發生的封鎖事件，無法追溯過去的封鎖紀錄。
            </div>
        </div>
    </body>
    </html>
    """.replace("{{ blocked_count }}", str(len(blocked))) \
       .replace("{{ follow_count }}", str(follow_count))

    # 簡單替換表格內容
    rows_html = ""
    for i, row in enumerate(blocked, 1):
        rows_html += f"""
        <tr>
            <td>{i}</td>
            <td style="font-family:monospace; font-size:12px;">{row[0]}</td>
            <td>{row[1]}</td>
            <td><span class="badge">已封鎖</span></td>
        </tr>"""

    if blocked:
        table_html = f"""
        <table>
            <thead><tr><th>#</th><th>用戶 ID</th><th>封鎖時間</th><th>狀態</th></tr></thead>
            <tbody>{rows_html}</tbody>
        </table>"""
    else:
        table_html = '<div class="empty">🎉 目前沒有封鎖用戶記錄</div>'

    html = html.replace("{% if blocked %}", "").replace("{% else %}", "").replace("{% endif %}", "")
    html = html.replace("""            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>用戶 ID</th>
                        <th>封鎖時間</th>
                        <th>狀態</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in blocked %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        <td style="font-family:monospace; font-size:12px;">{{ row[0] }}</td>
                        <td>{{ row[1] }}</td>
                        <td><span class="badge">已封鎖</span></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>""", table_html)
    html = html.replace('<div class="empty">🎉 目前沒有封鎖用戶記錄</div>', "")

    return html

# =============================================
# 匯出黑名單 JSON（方便整合其他系統）
# =============================================
@app.route("/export/blocked", methods=["GET"])
def export_blocked():
    conn = sqlite3.connect("blocked_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id, blocked_at FROM blocked_users")
    rows = c.fetchall()
    conn.close()
    result = [{"user_id": r[0], "blocked_at": r[1]} for r in rows]
    return jsonify({"count": len(result), "blocked_users": result})

# =============================================
# 健康檢查
# =============================================
@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "running", "message": "LINE Unfollow Tracker is active ✅"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

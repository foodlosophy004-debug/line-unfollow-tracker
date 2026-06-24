import os
import hmac
import hashlib
import base64
import json
import sqlite3
import requests
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_ADMIN_USER_ID = os.environ.get("LINE_ADMIN_USER_ID", "")

KEYWORDS = {
    "介面": "",  # 空字串 = 靜默，不回覆也不通知
    "外送": "",  # 給Line@ 外送介面回覆。
    "菜單": "",  # 給Line@ 菜單介面回覆
    "營業時間": "本店營業時間為每日10:30～13:30 與 16:30~19:30，歡迎提前使用預訂,減少等待時間^^。https://lihi.cc/l3k0v",
    "公休": "目前僅週日公休^^",
    "地址": "食見生活彰化民族分店位於彰化市民族路292-1號，歡迎您來品嚐健康美食！",
    "停車": "本店目前尚無特約停車場，敬請見諒。",
    "素食": "本店有提供方便素 餐點選擇，歡迎您來店詢問當日素食菜單。04-7280821",
    "熱量": "本店餐點皆有提供熱量資訊，方便您做飲食管理與計算。",
    "預訂": "可以！歡迎您提前透過此LINE帳號告知，我們會為您準備好餐點。",
    "外帶": "當然可以！本店提供外帶服務，方便您帶回家享用。",
    "內用": "本店提供內用座位，歡迎您在舒適的環境享用健康餐點。",
    "優惠": "本店不定期推出優惠活動，歡迎持續關注我們的LINE公告！",
    "電話": "您可以透過此LINE官方帳號與我們聯繫，我們很樂意為您服務。04-7280821",
    "你好": "您好！歡迎來到食見生活彰化民族分店，請問有什麼可以為您服務的嗎？",
    "謝謝": "感謝您的支持！食見生活彰化民族分店期待您的光臨，祝您用餐愉快😊",
}

def init_db():
    conn = sqlite3.connect("blocked_users.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS blocked_users (user_id TEXT PRIMARY KEY, blocked_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS follow_users (user_id TEXT PRIMARY KEY, followed_at TEXT)""")
    conn.commit()
    conn.close()

init_db()

def verify_signature(body, signature):
    secret = LINE_CHANNEL_SECRET.encode("utf-8")
    hash_digest = hmac.new(secret, body, hashlib.sha256).digest()
    expected = base64.b64encode(hash_digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)

def reply_message(reply_token, text):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=payload)

def push_message_to_admin(text):
    if not LINE_ADMIN_USER_ID:
        return
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    payload = {"to": LINE_ADMIN_USER_ID, "messages": [{"type": "text", "text": text}]}
    requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)

def find_keyword_reply(text):
    for keyword, reply in KEYWORDS.items():
        if keyword in text:
            if reply == "":
                return "SKIP"  # 靜默，不回覆也不通知
            return reply
    return None

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")
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
            c.execute("INSERT OR IGNORE INTO follow_users (user_id, followed_at) VALUES (?, ?)", (user_id, now))
            c.execute("DELETE FROM blocked_users WHERE user_id = ?", (user_id,))

        elif event_type == "unfollow":
            c.execute("INSERT OR REPLACE INTO blocked_users (user_id, blocked_at) VALUES (?, ?)", (user_id, now))
            c.execute("DELETE FROM follow_users WHERE user_id = ?", (user_id,))

        elif event_type == "message":
            msg = event.get("message", {})
            if msg.get("type") != "text":
                continue
            user_text = msg.get("text", "").strip()
            reply_token = event.get("replyToken")
            auto_reply = find_keyword_reply(user_text)

            if auto_reply == "SKIP":
                pass  # 靜默，不回覆也不通知
            elif auto_reply:
                reply_message(reply_token, auto_reply)
            else:
                reply_message(reply_token, "感謝您的訊息！我們已收到您的問題，將盡快為您回覆🙏")
                push_message_to_admin(
                    f"⚠️ 有客人需要人工回覆！\n\n"
                    f"用戶ID：{user_id}\n"
                    f"訊息內容：{user_text}\n\n"
                    f"請前往 LINE Official Account Manager 回覆。"
                )

    conn.commit()
    conn.close()
    return jsonify({"status": "ok"}), 200

@app.route("/admin", methods=["GET"])
def admin():
    conn = sqlite3.connect("blocked_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id, blocked_at FROM blocked_users ORDER BY blocked_at DESC")
    blocked = c.fetchall()
    c.execute("SELECT COUNT(*) FROM follow_users")
    follow_count = c.fetchone()[0]
    conn.close()
    rows_html = "".join(f"<tr><td>{i}</td><td style='font-family:monospace;font-size:12px'>{r[0]}</td><td>{r[1]}</td><td><span style='background:#fee2e2;color:#c53030;padding:3px 10px;border-radius:20px;font-size:12px'>已封鎖</span></td></tr>" for i, r in enumerate(blocked, 1))
    table = f"<table width='100%' cellpadding='12' style='border-collapse:collapse;background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.08)'><thead><tr style='background:#f7fafc'><th align='left'>#</th><th align='left'>用戶ID</th><th align='left'>封鎖時間</th><th align='left'>狀態</th></tr></thead><tbody>{rows_html}</tbody></table>" if blocked else "<div style='text-align:center;padding:30px;color:#aaa'>🎉 目前沒有封鎖用戶記錄</div>"
    return f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8"><title>LINE 後台</title></head>
    <body style="font-family:sans-serif;background:#f0f4f8;margin:0">
    <div style="background:linear-gradient(135deg,#06C755,#039B42);color:white;padding:30px;text-align:center">
    <h1 style="margin:0 0 5px">🚫 LINE 黑名單管理後台</h1>
    <p style="margin:0;opacity:.85;font-size:14px">食見生活彰化民族分店</p></div>
    <div style="display:flex;gap:20px;padding:20px;justify-content:center">
    <div style="background:white;border-radius:12px;padding:20px 30px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.08)">
    <div style="font-size:36px;font-weight:bold;color:#e53e3e">{len(blocked)}</div>
    <div style="font-size:13px;color:#666;margin-top:5px">封鎖人數</div></div>
    <div style="background:white;border-radius:12px;padding:20px 30px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.08)">
    <div style="font-size:36px;font-weight:bold;color:#06C755">{follow_count}</div>
    <div style="font-size:13px;color:#666;margin-top:5px">追蹤中人數</div></div></div>
    <div style="padding:0 20px 30px;max-width:900px;margin:0 auto">{table}</div>
    </body></html>"""

@app.route("/export/blocked", methods=["GET"])
def export_blocked():
    conn = sqlite3.connect("blocked_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id, blocked_at FROM blocked_users")
    rows = c.fetchall()
    conn.close()
    return jsonify({"count": len(rows), "blocked_users": [{"user_id": r[0], "blocked_at": r[1]} for r in rows]})

@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "running", "message": "LINE Tracker is active ✅"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

import os
import hmac
import hashlib
import base64
import json
import ssl
import urllib.parse
import pg8000
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
 
app = Flask(__name__)
CORS(app)
 
# ── 環境變數 ──
LINE_CHANNEL_SECRET       = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_ADMIN_USER_ID        = os.environ.get("LINE_ADMIN_USER_ID", "")
DATABASE_URL              = os.environ.get("DATABASE_URL", "")
 
# ── 智慧客服關鍵字 ──
KEYWORDS = {
    "「 會員介面 」": "",
    "「 點數兌換🎉 」": "",
    "「 菜單介面 」": "",
    "「 外送介面 」": "",
    "「 其他介面 」": "",
    "營業時間": "🕙 本店營業時間\n\n午餐｜10:30 - 13:30\n晚餐｜16:30 - 19:30\n\n歡迎提前預訂，減少等待時間😊\n https://lihi.cc/l3k0v",
    "公休": "目前僅週日公休^^",
    "地址": "食見生活彰化民族分店位於彰化市民族路292-1號，歡迎您來品嚐健康美食！",
    "位置": "食見生活彰化民族分店位於彰化市民族路292-1號，歡迎您來品嚐健康美食！",
    "停車": "本店目前尚無特約停車場，敬請見諒。",
    "支付": "您好，本店已支援多管道支付。\n付款方式如下：\n1.✅ 現金\n2.✅ LINE Pay\n3.❌ 街口支付\n4.❌ 全支付",
    "付費": "您好，本店已支援多管道支付。\n付款方式如下：\n1.✅ 現金\n2.✅ LINE Pay\n3.❌ 街口支付\n4.❌ 全支付",
    "刷卡": "您好，本店已支援多管道支付。\n付款方式如下：\n1.✅ 現金\n2.✅ LINE Pay\n3.❌ 街口支付\n4.❌ 全支付",
    "LINE Pay": "您好，本店已支援多管道支付。\n付款方式如下：\n1.✅ 現金\n2.✅ LINE Pay\n3.❌ 街口支付\n4.❌ 全支付",
    "街口": "您好，本店已支援多管道支付。\n付款方式如下：\n1.✅ 現金\n2.✅ LINE Pay\n3.❌ 街口支付\n4.❌ 全支付",
    "全支付": "您好，本店已支援多管道支付。\n付款方式如下：\n1.✅ 現金\n2.✅ LINE Pay\n3.❌ 街口支付\n4.❌ 全支付",
    "素食": "本店有提供方便素餐點選擇，歡迎您來店詢問當日素食菜單。\n04-7280821",
    "全素": "本店有提供方便素餐點選擇，歡迎您來店詢問當日素食菜單。\n04-7280821",
    "熱量": "本店餐點皆有提供熱量資訊，方便您做飲食管理與計算。",
    "預訂": "本店有提供線上點餐系統，歡迎多加利用^^\n https://lihi.cc/l3k0v \n如有即時訂單問題，歡迎致電04-7280821",
    "外帶": "當然可以！本店提供外帶服務，方便您帶回家享用。",
    "內用": "本店提供內用座位，歡迎您在舒適的環境享用健康餐點。",
    "優惠": "本店不定期推出優惠活動，歡迎持續關注我們的LINE公告！",
    "電話": "您可以透過此LINE官方帳號與我們聯繫，我們很樂意為您服務。\n04-7280821",
    "你好": "您好！歡迎來到食見生活彰化民族分店，請問有什麼可以為您服務的嗎？",
    "謝謝": "感謝您的支持！食見生活彰化民族分店期待您的光臨，祝您用餐愉快😊",
}
 
# ══════════════════════════════════════
# 工具函數
# ══════════════════════════════════════
 
def tw_today() -> str:
    """取得台灣時間（UTC+8）的今日日期字串 YYYY-MM-DD"""
    return datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
 
def tw_now() -> str:
    """取得台灣時間的當下時間字串"""
    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
 
def get_db():
    """建立 PostgreSQL 連線（pg8000）"""
    r = urllib.parse.urlparse(DATABASE_URL)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return pg8000.connect(
        host=r.hostname,
        port=r.port or 5432,
        database=r.path[1:],
        user=r.username,
        password=r.password,
        ssl_context=ctx
    )
 
def init_db():
    """建立所有資料表（若不存在）"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS blocked_users (
        user_id TEXT PRIMARY KEY, blocked_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS follow_users (
        user_id TEXT PRIMARY KEY, followed_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS pending_messages (
        id SERIAL PRIMARY KEY,
        user_id TEXT, user_name TEXT, message TEXT,
        created_at TEXT, status TEXT DEFAULT 'pending')""")
    c.execute("""CREATE TABLE IF NOT EXISTS slot_records (
        id SERIAL PRIMARY KEY,
        user_id TEXT, play_date TEXT, prize_id INTEGER,
        prize_name TEXT, prize_desc TEXT, played_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS coupons (
        id SERIAL PRIMARY KEY,
        user_id TEXT, prize_id INTEGER, prize_rank TEXT,
        prize_desc TEXT, prize_note TEXT, moon TEXT,
        won_at TEXT, expire_at TEXT,
        used INTEGER DEFAULT 0, used_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS share_records (
        id SERIAL PRIMARY KEY,
        user_id TEXT, share_date TEXT, extra_tries INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS ref_records (
        id SERIAL PRIMARY KEY,
        ref_user_id TEXT, new_user_id TEXT, ref_date TEXT,
        UNIQUE(ref_user_id, new_user_id))""")
    conn.commit()
    conn.close()
 
init_db()
 
# ══════════════════════════════════════
# LINE API 工具
# ══════════════════════════════════════
 
def verify_signature(body: bytes, signature: str) -> bool:
    secret = LINE_CHANNEL_SECRET.encode("utf-8")
    digest = hmac.new(secret, body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)
 
def get_user_profile(user_id: str) -> str:
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    try:
        res = requests.get(f"https://api.line.me/v2/bot/profile/{user_id}", headers=headers, timeout=5)
        if res.status_code == 200:
            return res.json().get("displayName", "貴賓")
    except Exception:
        pass
    return "貴賓"
 
def reply_message(reply_token: str, text: str):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    requests.post("https://api.line.me/v2/bot/message/reply", headers=headers,
                  json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}, timeout=5)
 
def push_message(to: str, messages: list):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    res = requests.post("https://api.line.me/v2/bot/message/push", headers=headers,
                        json={"to": to, "messages": messages}, timeout=5)
    print(f"PUSH RESULT: {res.status_code} {res.text}")
 
def find_keyword_reply(text: str):
    for keyword, reply in KEYWORDS.items():
        if keyword in text:
            return "SKIP" if reply == "" else reply
    return None
 
# ══════════════════════════════════════
# LINE Push 訊息模板
# ══════════════════════════════════════
 
LIFF_URL = "https://liff.line.me/2010668792-5uCuOlz3"
 
def push_win_flex(user_id: str, prize_desc: str, prize_note: str, expire_at: str):
    """中獎時推播優惠券通知"""
    expire_display = expire_at[:10].replace("-", "/")
    note_content = []
    if prize_note:
        note_content = [{"type": "text", "text": prize_note, "size": "xs",
                         "color": "#a39480", "wrap": True, "margin": "md"}]
    msg = {
        "type": "flex",
        "altText": f"🎉 恭喜您抽到「{prize_desc}」！請於 {expire_display} 前使用。",
        "contents": {
            "type": "bubble", "size": "kilo",
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "食見好食運", "color": "#a67c2e", "size": "xs", "weight": "bold"},
                    {"type": "text", "text": "恭喜抽到好運 🎉", "color": "#2c2418", "size": "lg", "weight": "bold", "margin": "sm"}
                ],
                "backgroundColor": "#fdf6e8", "paddingAll": "16px"
            },
            "body": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {
                        "type": "box", "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "獎項", "size": "xs", "color": "#a39480"},
                            {"type": "text", "text": prize_desc, "size": "xl", "weight": "bold",
                             "color": "#2c2418", "margin": "sm", "wrap": True}
                        ] + note_content,
                        "paddingAll": "16px", "backgroundColor": "#fcfaf7", "cornerRadius": "10px"
                    },
                    {"type": "separator", "margin": "lg", "color": "#e8d6a7"},
                    {
                        "type": "box", "layout": "horizontal", "margin": "lg",
                        "contents": [
                            {"type": "text", "text": "有效期限", "size": "xs", "color": "#a39480", "flex": 3},
                            {"type": "text", "text": f"{expire_display} 前", "size": "xs",
                             "color": "#b8923a", "weight": "bold", "flex": 5, "align": "end"}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "margin": "md",
                        "contents": [
                            {"type": "text", "text": "使用方式", "size": "xs", "color": "#a39480", "flex": 3},
                            {"type": "text", "text": "出示優惠券請店員核銷", "size": "xs",
                             "color": "#6b5f4e", "flex": 5, "align": "end", "wrap": True}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "margin": "md",
                        "contents": [
                            {"type": "text", "text": "地點", "size": "xs", "color": "#a39480", "flex": 3},
                            {"type": "text", "text": "食見生活 彰化民族分店", "size": "xs",
                             "color": "#6b5f4e", "flex": 5, "align": "end"}
                        ]
                    }
                ], "paddingAll": "16px"
            },
            "footer": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "⏰ 請於 3 天內使用，逾期失效",
                               "size": "xs", "color": "#b8923a", "align": "center"}],
                "paddingAll": "12px", "backgroundColor": "#fdf6e8"
            },
            "styles": {"footer": {"separator": True, "separatorColor": "#e8d6a7"}}
        }
    }
    push_message(user_id, [msg])
 
def push_no_prize_flex(user_id: str):
    """末吉時推播邀請分享訊息"""
    msg = {
        "type": "flex",
        "altText": "今日籤運未到，邀請好友一起來抽籤！",
        "contents": {
            "type": "bubble", "size": "kilo",
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "食見好食運", "color": "#a67c2e", "size": "xs", "weight": "bold"},
                    {"type": "text", "text": "末吉 · 緣慳一面", "color": "#2c2418", "size": "lg", "weight": "bold", "margin": "sm"}
                ],
                "backgroundColor": "#fdf6e8", "paddingAll": "16px"
            },
            "body": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "今日籤運尚未到來", "size": "sm", "color": "#6b5f4e", "align": "center"},
                    {"type": "text", "text": "邀請好友來抽籤", "size": "sm", "color": "#6b5f4e", "align": "center", "margin": "sm"},
                    {"type": "text", "text": "好友點擊即可獲得加抽機會！", "size": "xs", "color": "#a39480", "align": "center", "margin": "sm"}
                ], "paddingAll": "16px"
            },
            "footer": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "button", "action": {"type": "uri", "label": "邀請好友一起來抽籤", "uri": LIFF_URL},
                               "style": "primary", "color": "#b8923a"}],
                "paddingAll": "12px", "backgroundColor": "#fdf6e8"
            }
        }
    }
    push_message(user_id, [msg])
 
def push_ref_notify(ref_user_id: str):
    """好友點擊分享連結後，通知推薦人加抽機會到帳"""
    msg = {
        "type": "flex",
        "altText": "🎉 有好友點開您的抽籤連結！加抽機會已到帳！",
        "contents": {
            "type": "bubble", "size": "kilo",
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "食見好食運", "color": "#a67c2e", "size": "xs", "weight": "bold"},
                    {"type": "text", "text": "好友已點擊 🎉", "color": "#2c2418", "size": "lg", "weight": "bold", "margin": "sm"}
                ],
                "backgroundColor": "#fdf6e8", "paddingAll": "16px"
            },
            "body": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {
                        "type": "box", "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "您的好友已點開分享連結", "size": "sm", "color": "#6b5f4e", "align": "center"},
                            {"type": "text", "text": "加抽機會已到帳", "size": "xl", "weight": "bold",
                             "color": "#b8923a", "align": "center", "margin": "md"},
                            {"type": "text", "text": "快去抽籤祈取好運吧！", "size": "sm",
                             "color": "#a39480", "align": "center", "margin": "sm"}
                        ],
                        "paddingAll": "16px", "backgroundColor": "#fcfaf7", "cornerRadius": "10px"
                    }
                ], "paddingAll": "16px"
            },
            "footer": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "button", "action": {"type": "uri", "label": "立即前往抽籤", "uri": LIFF_URL},
                               "style": "primary", "color": "#b8923a"}],
                "paddingAll": "12px", "backgroundColor": "#fdf6e8"
            },
            "styles": {"footer": {"separator": True, "separatorColor": "#e8d6a7"}}
        }
    }
    push_message(ref_user_id, [msg])
 
def push_flex_notification(user_name: str, user_text: str, pending_id):
    """客服訊息通知管理員"""
    if not LINE_ADMIN_USER_ID:
        return
    msg = {
        "type": "flex",
        "altText": f"⚠️ 有客人需要人工回覆！{user_name}：{user_text}",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "⚠️ 有客人需要人工回覆！",
                               "weight": "bold", "color": "#ffffff", "size": "md"}],
                "backgroundColor": "#E53E3E", "paddingAll": "15px"
            },
            "body": {
                "type": "box", "layout": "vertical", "paddingAll": "15px",
                "contents": [
                    {"type": "box", "layout": "horizontal", "margin": "md",
                     "contents": [
                         {"type": "text", "text": "👤 客人", "size": "sm", "color": "#888888", "flex": 2},
                         {"type": "text", "text": user_name, "size": "sm", "weight": "bold", "flex": 5}
                     ]},
                    {"type": "box", "layout": "horizontal", "margin": "md",
                     "contents": [
                         {"type": "text", "text": "💬 訊息", "size": "sm", "color": "#888888", "flex": 2},
                         {"type": "text", "text": user_text, "size": "sm", "weight": "bold", "flex": 5, "wrap": True}
                     ]},
                    {"type": "box", "layout": "horizontal", "margin": "md",
                     "contents": [
                         {"type": "text", "text": "🔢 單號", "size": "sm", "color": "#888888", "flex": 2},
                         {"type": "text", "text": f"#{pending_id}", "size": "sm", "flex": 5}
                     ]}
                ]
            },
            "footer": {
                "type": "box", "layout": "horizontal", "paddingAll": "10px",
                "contents": [
                    {"type": "button", "style": "secondary", "height": "sm", "flex": 1,
                     "action": {"type": "postback", "label": "⏳ 未處理",
                                "data": f"pending_{pending_id}", "displayText": "⏳ 標記為未處理"}},
                    {"type": "button", "style": "primary", "color": "#06C755", "height": "sm", "flex": 1, "margin": "sm",
                     "action": {"type": "postback", "label": "✅ 已處理",
                                "data": f"done_{pending_id}", "displayText": "✅ 標記為已處理"}}
                ]
            }
        }
    }
    push_message(LINE_ADMIN_USER_ID, [msg])
 
# ══════════════════════════════════════
# 抽籤 API
# ══════════════════════════════════════
 
# ⚙️ 不重複抽獎的獎項順序對照表
# 若要改為「可重複抽」，將 /slot/today 回傳 {"drawn": []} 即可
PRIZE_ORDER = [
    '買一送一', '餐點半價', '20% OFF',
    'UP 蒜香金油炊飯', 'UP 匠心雞白湯', 'UP 美味烘蛋',
    '緣慳一面', '緣慳一面', '緣慳一面'
]
 
@app.route("/slot")
def slot_page():
    return send_file("slot.html")
 
@app.route("/slot/check")
def slot_check():
    """查詢今日剩餘抽籤次數"""
    user_id = request.args.get("userId", "")
    today   = tw_today()
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(extra_tries),0) FROM share_records WHERE user_id=%s AND share_date=%s", (user_id, today))
    extra = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM slot_records WHERE user_id=%s AND play_date=%s", (user_id, today))
    played = c.fetchone()[0]
    conn.close()
    # ⚙️ 每日基本次數：1 次 + 好友推薦最多 +2
    total = 1 + int(extra)
    return jsonify({"played": played >= total, "tries": max(0, total - played), "total": total})
 
@app.route("/slot/today")
def slot_today():
    """回傳今日已抽的獎項 index（供前端不重複抽取使用）
    
    ⚙️ 若要改為「可重複抽」：直接 return jsonify({"drawn": []})
    """
    user_id = request.args.get("userId", "")
    today   = tw_today()
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT prize_name FROM slot_records WHERE user_id=%s AND play_date=%s ORDER BY played_at",
              (user_id, today))
    rows = c.fetchall(); conn.close()
 
    drawn = []; no_count = 0
    for r in rows:
        name = r[0]
        if name == '緣慳一面':
            drawn.append(6 + min(no_count, 2))
            no_count += 1
        else:
            try:
                drawn.append(PRIZE_ORDER.index(name))
            except ValueError:
                pass
   # return jsonify({"drawn": drawn})  # 獎勵池 不重複 但測試階段如果超過9次會直接卡住...
    return jsonify({"drawn": []})      # 獎勵池 會重複 每次都是全新的獎勵池 
 
@app.route("/slot/play", methods=["POST"])
def slot_play():
    """記錄抽籤結果，發放優惠券或推播訊息"""
    data       = request.json or {}
    user_id    = data.get("userId", "")
    prize_id   = data.get("prizeId", 0)
    prize_name = data.get("prizeName", "")
    prize_desc = data.get("prizeDesc", "")
    prize_note = data.get("prizeNote", "")
    today      = tw_today()
    now        = tw_now()
    expire_at  = (datetime.now(ZoneInfo("Asia/Taipei")).date() + timedelta(days=3)).strftime("%Y-%m-%d")
 
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(extra_tries),0) FROM share_records WHERE user_id=%s AND share_date=%s", (user_id, today))
    extra = c.fetchone()[0] or 0
    total = 1 + int(extra)
    c.execute("SELECT COUNT(*) FROM slot_records WHERE user_id=%s AND play_date=%s", (user_id, today))
    played = c.fetchone()[0]
 
    if played >= total:
        conn.close()
        return jsonify({"success": False, "message": "今日次數已用完"})
 
    c.execute("INSERT INTO slot_records (user_id, play_date, prize_id, prize_name, prize_desc, played_at) VALUES (%s,%s,%s,%s,%s,%s)",
              (user_id, today, prize_id, prize_name, prize_desc, now))
 
    if prize_id > 0:
        c.execute("INSERT INTO coupons (user_id, prize_id, prize_rank, prize_desc, prize_note, moon, won_at, expire_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                  (user_id, prize_id, prize_name, prize_desc, prize_note, "🎁", now, expire_at))
        conn.commit(); conn.close()
        push_win_flex(user_id, prize_desc, prize_note, expire_at)
    else:
        conn.commit(); conn.close()
        push_no_prize_flex(user_id)
 
    return jsonify({"success": True})
 
@app.route("/slot/ref", methods=["POST"])
def slot_ref():
    """好友點擊推薦連結，給推薦人加抽次數"""
    data        = request.json or {}
    ref_user_id = data.get("refUserId", "")
    new_user_id = data.get("newUserId", "")
    today       = tw_today()
 
    if not ref_user_id or not new_user_id or ref_user_id == new_user_id:
        return jsonify({"success": False, "message": "無效的推薦"})
 
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO ref_records (ref_user_id, new_user_id, ref_date) VALUES (%s,%s,%s)",
                  (ref_user_id, new_user_id, today))
    except Exception as e:
        conn.rollback(); conn.close()
        return jsonify({"success": False, "message": "已推薦過"})
 
    c.execute("SELECT COUNT(*) FROM share_records WHERE user_id=%s AND share_date=%s", (ref_user_id, today))
    ref_count = c.fetchone()[0]
 
    if ref_count < 2:  # ⚙️ 每日最多從好友推薦獲得 2 次加抽
        c.execute("INSERT INTO share_records (user_id, share_date) VALUES (%s,%s)", (ref_user_id, today))
        conn.commit(); conn.close()
        push_ref_notify(ref_user_id)
    else:
        conn.commit(); conn.close()
 
    return jsonify({"success": True})
 
@app.route("/slot/coupons")
def get_coupons():
    """讀取優惠券列表，並自動清理 14 天前的舊資料"""
    user_id = request.args.get("userId", "")
    status  = request.args.get("status", "active")
    today   = tw_today()
    cutoff  = (datetime.now(ZoneInfo("Asia/Taipei")).date() - timedelta(days=14)).isoformat()
 
    conn = get_db(); c = conn.cursor()
    # 自動清理 14 天前已使用/已過期資料
    c.execute("DELETE FROM coupons WHERE (used=1 OR expire_at < %s) AND won_at < %s", (today, cutoff))
 
    if status == "active":
        c.execute("""SELECT id, prize_id, prize_rank, prize_desc, prize_note, moon, won_at, expire_at, used, used_at
                     FROM coupons WHERE user_id=%s AND used=0 AND expire_at >= %s
                     ORDER BY won_at DESC""", (user_id, today))
    else:
        c.execute("""SELECT id, prize_id, prize_rank, prize_desc, prize_note, moon, won_at, expire_at, used, used_at
                     FROM coupons WHERE user_id=%s AND (used=1 OR expire_at < %s)
                     ORDER BY won_at DESC""", (user_id, today))
 
    rows = c.fetchall(); conn.commit(); conn.close()
    return jsonify([{
        "id": r[0], "prizeId": r[1], "rank": r[2], "desc": r[3],
        "note": r[4] or "", "moon": r[5],
        "wonAt": str(r[6])[:10], "expireAt": str(r[7]),
        "used": bool(r[8]), "usedAt": r[9],
        "expired": str(r[7]) < today and not bool(r[8])
    } for r in rows])
 
@app.route("/slot/redeem", methods=["POST"])
def redeem_coupon():
    """核銷優惠券"""
    data      = request.json or {}
    coupon_id = data.get("couponId")
    code      = data.get("code", "")
 
    if code != "700718":  # ⚙️ 核銷碼可在此修改
        return jsonify({"success": False, "message": "核銷碼錯誤"})
 
    today = tw_today()
    now   = tw_now()
    conn  = get_db(); c = conn.cursor()
    c.execute("SELECT used, expire_at FROM coupons WHERE id=%s", (coupon_id,))
    row = c.fetchone()
 
    if not row:
        conn.close(); return jsonify({"success": False, "message": "優惠券不存在"})
    if row[0]:
        conn.close(); return jsonify({"success": False, "message": "此優惠券已使用"})
    if str(row[1]) < today:
        conn.close(); return jsonify({"success": False, "message": "此優惠券已過期"})
 
    c.execute("UPDATE coupons SET used=1, used_at=%s WHERE id=%s", (now, coupon_id))
    conn.commit(); conn.close()
    return jsonify({"success": True})
 
# ══════════════════════════════════════
# LINE Webhook
# ══════════════════════════════════════
 
@app.route("/webhook", methods=["POST"])
def webhook():
    body      = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_signature(body, signature):
        return jsonify({"error": "Invalid signature"}), 403
 
    events = json.loads(body).get("events", [])
    conn   = get_db(); c = conn.cursor()
    now    = tw_now()
 
    for event in events:
        event_type = event.get("type")
        user_id    = event.get("source", {}).get("userId")
        if not user_id:
            continue
 
        if event_type == "follow":
            c.execute("INSERT INTO follow_users (user_id, followed_at) VALUES (%s,%s) ON CONFLICT (user_id) DO NOTHING", (user_id, now))
            c.execute("DELETE FROM blocked_users WHERE user_id=%s", (user_id,))
 
        elif event_type == "unfollow":
            c.execute("INSERT INTO blocked_users (user_id, blocked_at) VALUES (%s,%s) ON CONFLICT (user_id) DO UPDATE SET blocked_at=%s", (user_id, now, now))
            c.execute("DELETE FROM follow_users WHERE user_id=%s", (user_id,))
 
        elif event_type == "postback":
            pd          = event.get("postback", {}).get("data", "")
            reply_token = event.get("replyToken")
            if pd.startswith("done_"):
                pid = pd.replace("done_", "")
                c.execute("UPDATE pending_messages SET status='done' WHERE id=%s", (pid,))
                reply_message(reply_token, f"✅ 單號 #{pid} 已標記為處理完成！")
            elif pd.startswith("pending_"):
                pid = pd.replace("pending_", "")
                c.execute("UPDATE pending_messages SET status='pending' WHERE id=%s", (pid,))
                reply_message(reply_token, f"⏳ 單號 #{pid} 已標記為未處理！")
 
        elif event_type == "message":
            msg = event.get("message", {})
            if msg.get("type") != "text":
                continue
            user_text   = msg.get("text", "").strip()
            reply_token = event.get("replyToken")
            auto_reply  = find_keyword_reply(user_text)
            if auto_reply == "SKIP":
                pass
            elif auto_reply:
                reply_message(reply_token, auto_reply)
            else:
                user_name = get_user_profile(user_id)
                c.execute("INSERT INTO pending_messages (user_id, user_name, message, created_at) VALUES (%s,%s,%s,%s)",
                          (user_id, user_name, user_text, now))
                c.execute("SELECT lastval()")
                pending_id = c.fetchone()[0]
                reply_message(reply_token, "感謝您的訊息！我們已收到您的問題，將盡快為您回覆🙏")
                push_flex_notification(user_name, user_text, pending_id)
 
    conn.commit(); conn.close()
    return jsonify({"status": "ok"}), 200
 
# ══════════════════════════════════════
# 管理後台
# ══════════════════════════════════════
 
@app.route("/admin")
def admin():
    conn = get_db(); c = conn.cursor()
    today = tw_today()
    c.execute("SELECT user_id, blocked_at FROM blocked_users ORDER BY blocked_at DESC")
    blocked = c.fetchall()
    c.execute("SELECT COUNT(*) FROM follow_users")
    follow_count = c.fetchone()[0]
    c.execute("SELECT id, user_name, message, created_at, status FROM pending_messages ORDER BY created_at DESC LIMIT 50")
    pending = c.fetchall()
    c.execute("SELECT COUNT(*) FROM slot_records WHERE play_date=%s", (today,))
    slot_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM coupons WHERE used=0")
    unused = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM coupons WHERE used=1")
    used = c.fetchone()[0]
    conn.close()
 
    def badge(text, bg, color):
        return f"<span style='background:{bg};color:{color};padding:3px 10px;border-radius:20px;font-size:12px'>{text}</span>"
 
    pending_rows = "".join(
        f"<tr><td>#{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td>"
        f"<td>{badge('✅ 已處理','#d1fae5','#065f46') if r[4]=='done' else badge('⏳ 待處理','#fef3c7','#92400e')}</td></tr>"
        for r in pending)
    blocked_rows = "".join(
        f"<tr><td>{i}</td><td style='font-family:monospace;font-size:12px'>{r[0]}</td>"
        f"<td>{r[1]}</td><td>{badge('已封鎖','#fee2e2','#c53030')}</td></tr>"
        for i, r in enumerate(blocked, 1))
 
    card = lambda n, label, color: f"<div style='background:white;border-radius:12px;padding:20px 30px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.08)'><div style='font-size:36px;font-weight:bold;color:{color}'>{n}</div><div style='font-size:13px;color:#666;margin-top:5px'>{label}</div></div>"
    table = lambda rows, headers: f"<table width='100%' cellpadding='12' style='border-collapse:collapse;background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.08)'><thead><tr style='background:#f7fafc'>{''.join(f'<th align=left>{h}</th>' for h in headers)}</tr></thead><tbody>{rows}</tbody></table>"
 
    return f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8"><title>LINE 後台</title></head>
<body style="font-family:sans-serif;background:#f0f4f8;margin:0">
<div style="background:linear-gradient(135deg,#06C755,#039B42);color:white;padding:30px;text-align:center">
  <h1 style="margin:0 0 5px">食見生活 LINE 管理後台</h1>
  <p style="margin:0;opacity:.85;font-size:14px">彰化民族分店</p>
</div>
<div style="display:flex;gap:20px;padding:20px;justify-content:center;flex-wrap:wrap">
  {card(sum(1 for r in pending if r[4]=='pending'), '待處理訊息', '#f59e0b')}
  {card(len(blocked), '封鎖人數', '#e53e3e')}
  {card(follow_count, '追蹤中人數', '#06C755')}
  {card(slot_count, '今日抽籤次數', '#8b5cf6')}
  {card(unused, '未使用優惠券', '#f59e0b')}
  {card(used, '已使用優惠券', '#aaa')}
</div>
<div style="padding:0 20px 30px;max-width:1000px;margin:0 auto">
  <div style="font-size:16px;font-weight:bold;margin:20px 0 10px;color:#444">⏳ 客服訊息記錄</div>
  {table(pending_rows, ['單號','客人','訊息','時間','狀態']) if pending else "<div style='text-align:center;padding:30px;color:#aaa'>目前沒有訊息記錄</div>"}
  <div style="font-size:16px;font-weight:bold;margin:30px 0 10px;color:#444">🚫 封鎖用戶清單</div>
  {table(blocked_rows, ['#','用戶ID','封鎖時間','狀態']) if blocked else "<div style='text-align:center;padding:30px;color:#aaa'>🎉 目前沒有封鎖用戶記錄</div>"}
</div>
</body></html>"""
 
@app.route("/export/blocked")
def export_blocked():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT user_id, blocked_at FROM blocked_users")
    rows = c.fetchall(); conn.close()
    return jsonify({"count": len(rows), "blocked_users": [{"user_id": r[0], "blocked_at": r[1]} for r in rows]})
 
@app.route("/")
def index():
    return jsonify({"status": "running", "message": "LINE Tracker is active ✅"})
 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
 

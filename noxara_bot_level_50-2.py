from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters
import re
import os
import sqlite3
from datetime import date, timedelta

# ==================================================
# ⚠️ PUT YOUR BOT TOKEN HERE
# ==================================================
TOKEN = os.getenv("BOT_TOKEN")
DATABASE = "noxara.db"

INITIAL_ADMIN_IDS = {5747356891}

DEFAULT_GAMES = {
    "Minesweeper": 1,
    "Dose": 2,
    "Spy": 3,
    "Othello": 4,
    "Mafia": 5
}

# ==================================================
# 👑 LEVEL SYSTEM — LEVEL 1 TO 50
# ==================================================
# XP required to START each level.
# Level 50 is intentionally difficult and prestigious.
LEVEL_TITLES = {
    1: "Newcomer", 2: "Rookie", 3: "Player", 4: "Rising Player",
    5: "Lucky Hand", 6: "Card Shark", 7: "Risk Taker", 8: "Night Player",
    9: "Casino Regular", 10: "Noxara Member", 11: "Street Gambler",
    12: "High Roller", 13: "Lucky Devil", 14: "Black Card",
    15: "The Gambler", 16: "Rising Ace", 17: "Silver Ace",
    18: "Golden Ace", 19: "Royal Player", 20: "Casino Elite",
    21: "Dark Horse", 22: "Shadow Player", 23: "Underground Ace",
    24: "The Collector", 25: "Crime Partner", 26: "Black Dealer",
    27: "Red Joker", 28: "The Outlaw", 29: "Midnight Boss",
    30: "Noxara Elite", 31: "Underboss", 32: "The Strategist",
    33: "The Fixer", 34: "The Dealer", 35: "Black King",
    36: "The Consigliere", 37: "Casino Master", 38: "Shadow Boss",
    39: "The Godfather", 40: "Noxara Legend", 41: "Crimson King",
    42: "Phantom Ace", 43: "The Don", 44: "Royal Shadow",
    45: "The Mastermind", 46: "Noxara Royalty",
    47: "The Untouchable", 48: "King of Noxara",
    49: "Noxara Overlord", 50: "👑 The Noxara"
}

# Hard / competitive curve.
LEVEL_XP = {1: 0}
for level in range(2, 51):
    # Each level becomes progressively harder.
    previous = LEVEL_XP[level - 1]
    requirement = 12 + (level - 2) * 7 + ((level - 2) ** 2) * 2
    LEVEL_XP[level] = previous + requirement

DEFAULT_ACHIEVEMENTS = {
    "first_win": ("First Blood", "اولین برد خودت را ثبت کردی.", "🩸"),
    "wins_5": ("Rising Player", "به 5 برد رسیدی.", "⚡️"),
    "wins_10": ("Regular", "به 10 برد رسیدی.", "🎮"),
    "wins_25": ("Veteran", "به 25 برد رسیدی.", "🔥"),
    "wins_50": ("Elite Player", "به 50 برد رسیدی.", "👑"),
    "level_5": ("Level 5", "به Level 5 رسیدی.", "⭐️"),
    "level_10": ("Noxara Member", "به Level 10 رسیدی.", "🖤"),
    "level_20": ("Casino Elite", "به Level 20 رسیدی.", "🎰"),
    "level_30": ("Noxara Elite", "به Level 30 رسیدی.", "🔥"),
    "level_40": ("Noxara Legend", "به Level 40 رسیدی.", "👑"),
    "level_50": ("The Noxara", "به بالاترین Level ناکسارا رسیدی.", "🏆")
}

WEEKLY_MIN_XP = 100


# ==================================================
# 🗄️ DATABASE
# ==================================================
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS players (
        user_id INTEGER PRIMARY KEY,
        name TEXT DEFAULT '',
        username TEXT DEFAULT '',
        xp INTEGER DEFAULT 0,
        weekly_xp INTEGER DEFAULT 0,
        minesweeper_wins INTEGER DEFAULT 0,
        dose_wins INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS processed_results (
        chat_id INTEGER,
        message_id INTEGER,
        PRIMARY KEY (chat_id, message_id)
    )""")

    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")

    c.execute("""CREATE TABLE IF NOT EXISTS games (
        game_name TEXT PRIMARY KEY,
        xp INTEGER DEFAULT 1,
        bonus_multiplier REAL DEFAULT 1
    )""")

    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT DEFAULT '')")

    c.execute("""CREATE TABLE IF NOT EXISTS player_game_stats (
        user_id INTEGER,
        game_name TEXT,
        wins INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, game_name)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS achievements (
        achievement_id TEXT PRIMARY KEY,
        title TEXT,
        description TEXT,
        emoji TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS player_achievements (
        user_id INTEGER,
        achievement_id TEXT,
        unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, achievement_id)
    )""")

    for game, xp in DEFAULT_GAMES.items():
        c.execute("INSERT OR IGNORE INTO games (game_name,xp,bonus_multiplier) VALUES (?,?,1)", (game, xp))

    for admin_id in INITIAL_ADMIN_IDS:
        c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (admin_id,))

    for aid, data in DEFAULT_ACHIEVEMENTS.items():
        c.execute("""INSERT OR IGNORE INTO achievements
        (achievement_id,title,description,emoji) VALUES (?,?,?,?)""",
                  (aid, data[0], data[1], data[2]))

    conn.commit()
    conn.close()
    ensure_weekly_reset()


# ==================================================
# 🗓️ WEEKLY SYSTEM
# ==================================================
def get_week_start(target_date=None):
    if target_date is None:
        target_date = date.today()
    days_since_saturday = (target_date.weekday() - 5) % 7
    return target_date - timedelta(days=days_since_saturday)


def get_current_week_key():
    return get_week_start().isoformat()


def ensure_weekly_reset():
    current_week = get_current_week_key()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='weekly_start'")
    row = c.fetchone()

    if not row:
        c.execute("INSERT INTO settings (key,value) VALUES ('weekly_start',?)", (current_week,))
    elif row["value"] != current_week:
        c.execute("UPDATE players SET weekly_xp=0")
        c.execute("UPDATE settings SET value=? WHERE key='weekly_start'", (current_week,))

    conn.commit()
    conn.close()


def add_weekly_xp(user_id, amount):
    if amount <= 0:
        return
    ensure_weekly_reset()
    conn = get_db()
    conn.execute("UPDATE players SET weekly_xp=weekly_xp+? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()


# ==================================================
# 👤 PLAYERS
# ==================================================
def register_user(user):
    if not user:
        return

    ensure_weekly_reset()
    conn = get_db()
    c = conn.cursor()
    name = user.first_name or "Unknown"
    username = user.username or ""

    c.execute("SELECT user_id FROM players WHERE user_id=?", (user.id,))
    if c.fetchone():
        c.execute("UPDATE players SET name=?,username=? WHERE user_id=?", (name, username, user.id))
    else:
        c.execute("""INSERT INTO players
        (user_id,name,username,xp,weekly_xp,minesweeper_wins,dose_wins)
        VALUES (?,?,?,?,?,?,?)""", (user.id, name, username, 0, 0, 0, 0))

    conn.commit()
    conn.close()


def get_player(user):
    register_user(user)
    return get_player_by_id(user.id)


def get_player_by_id(user_id):
    conn = get_db()
    player = conn.execute("SELECT * FROM players WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return player


def normalize_name(text):
    if not text:
        return ""
    for char in ["\u200b","\u200c","\u200d","\u200e","\u200f","\u2060","\u2061","\u2062","\u2063","\u2064","\ufeff","\u3164"]:
        text = text.replace(char, "")
    return re.sub(r"\s+", " ", text).strip().casefold()


def find_player(identifier):
    if not identifier:
        return None
    identifier = identifier.strip()

    if identifier.isdigit():
        return get_player_by_id(int(identifier))

    normalized = normalize_name(identifier).lstrip("@")
    conn = get_db()
    players = conn.execute("SELECT * FROM players").fetchall()
    conn.close()

    for p in players:
        if normalize_name(p["name"]) == normalized:
            return p
    for p in players:
        if p["username"] and normalize_name(p["username"]).lstrip("@") == normalized:
            return p
    return None


def player_display(player):
    if player["username"]:
        return "@" + player["username"]
    return player["name"]


# ==================================================
# 👑 ADMIN
# ==================================================
def is_admin(user_id):
    conn = get_db()
    result = conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return result is not None


def add_admin(user_id):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()


def remove_admin(user_id):
    conn = get_db()
    conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


# ==================================================
# 🎮 GAMES
# ==================================================
def get_game(game_name):
    conn = get_db()
    game = conn.execute("SELECT * FROM games WHERE LOWER(game_name)=LOWER(?)", (game_name,)).fetchone()
    conn.close()
    return game


def get_game_xp(game_name):
    game = get_game(game_name)
    return int(game["xp"] * game["bonus_multiplier"]) if game else 0


def set_game_xp(game_name, xp):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE games SET xp=? WHERE LOWER(game_name)=LOWER(?)", (xp, game_name))
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def set_bonus(game_name, multiplier):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE games SET bonus_multiplier=? WHERE LOWER(game_name)=LOWER(?)", (multiplier, game_name))
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    return changed


# ==================================================
# ⭐ LEVEL HELPERS
# ==================================================
def get_level(xp):
    level = 1
    for lv in range(1, 51):
        if xp >= LEVEL_XP[lv]:
            level = lv
        else:
            break
    return level


def get_title(level):
    return LEVEL_TITLES.get(level, "The Noxara")


def get_level_progress(xp):
    level = get_level(xp)

    if level >= 50:
        return level, xp, None, 100.0

    current_start = LEVEL_XP[level]
    next_start = LEVEL_XP[level + 1]
    needed = next_start - current_start
    current = xp - current_start
    percent = min(100, (current / needed) * 100) if needed else 100
    return level, current, needed, percent


# ==================================================
# 🏅 ACHIEVEMENTS
# ==================================================
def unlock_achievement(user_id, achievement_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO player_achievements
    (user_id,achievement_id) VALUES (?,?)""", (user_id, achievement_id))
    unlocked = c.rowcount > 0
    conn.commit()
    conn.close()
    return unlocked


def get_achievement(aid):
    conn = get_db()
    row = conn.execute("SELECT * FROM achievements WHERE achievement_id=?", (aid,)).fetchone()
    conn.close()
    return row


def get_player_achievements(user_id):
    conn = get_db()
    rows = conn.execute("""SELECT a.*,pa.unlocked_at FROM player_achievements pa
    JOIN achievements a ON pa.achievement_id=a.achievement_id
    WHERE pa.user_id=? ORDER BY pa.unlocked_at""", (user_id,)).fetchall()
    conn.close()
    return rows


def get_game_wins(user_id, game_name):
    conn = get_db()
    row = conn.execute("""SELECT wins FROM player_game_stats
    WHERE user_id=? AND LOWER(game_name)=LOWER(?)""", (user_id, game_name)).fetchone()
    conn.close()
    return row["wins"] if row else 0


def total_wins(player):
    uid = player["user_id"]
    return (player["minesweeper_wins"] + player["dose_wins"] +
            get_game_wins(uid, "Spy") + get_game_wins(uid, "Othello") +
            get_game_wins(uid, "Mafia"))


def check_achievements(user_id):
    player = get_player_by_id(user_id)
    if not player:
        return []

    wins = total_wins(player)
    level = get_level(player["xp"])
    unlocked = []

    conditions = [
        ("first_win", wins >= 1), ("wins_5", wins >= 5),
        ("wins_10", wins >= 10), ("wins_25", wins >= 25),
        ("wins_50", wins >= 50), ("level_5", level >= 5),
        ("level_10", level >= 10), ("level_20", level >= 20),
        ("level_30", level >= 30), ("level_40", level >= 40),
        ("level_50", level >= 50)
    ]

    for aid, condition in conditions:
        if condition and unlock_achievement(user_id, aid):
            unlocked.append(aid)
    return unlocked


# ==================================================
# 🎮 GAME STATS / XP
# ==================================================
def add_game_win_stat(user_id, game_name):
    conn = get_db()
    conn.execute("""INSERT INTO player_game_stats (user_id,game_name,wins)
    VALUES (?,?,1)
    ON CONFLICT(user_id,game_name) DO UPDATE SET wins=wins+1""",
                 (user_id, game_name))
    conn.commit()
    conn.close()


def add_win_to_player(user_id, game):
    xp_gain = get_game_xp(game)
    if xp_gain <= 0:
        return 0

    conn = get_db()
    c = conn.cursor()

    if game == "Minesweeper":
        c.execute("""UPDATE players SET xp=xp+?,
        minesweeper_wins=minesweeper_wins+1 WHERE user_id=?""", (xp_gain, user_id))
    elif game == "Dose":
        c.execute("""UPDATE players SET xp=xp+?,
        dose_wins=dose_wins+1 WHERE user_id=?""", (xp_gain, user_id))
    else:
        c.execute("UPDATE players SET xp=xp+? WHERE user_id=?", (xp_gain, user_id))

    conn.commit()
    conn.close()

    add_game_win_stat(user_id, game)
    add_weekly_xp(user_id, xp_gain)
    return xp_gain


# ==================================================
# 🔍 GAME RESULT DETECTOR
# ==================================================
def check_game_result(text):
    if not text:
        return None

    winner = None
    game = None

    patterns = [
        ("Dose", r"🎉\s*بازیکن\s+(.+?)\s+برنده\s+شد"),
        ("Minesweeper", r"🏆\s*برنده\s+مسابقه\s*:\s*(.+)"),
        ("Minesweeper", r"🏆\s*Winner\s*:\s*(.+)"),
        ("Othello", r"برنده\s+مسابقه\s*:\s*(?:⚪️|⚫️)\s*(.+)"),
        ("Spy", r"😈\s*(.+?)\s+در\s+نقش\s+جاسوس\s+برنده\s+بازی\s+شد")
    ]

    for game_name, pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            winner = match.group(1).strip()
            game = game_name
            break

    if not winner:
        for line in text.splitlines():
            line = line.strip()
            if "برنده" not in line or line.startswith("بازیکن های زنده"):
                continue
            match = re.match(r"(.+?)\s*:\s*.+?\s+برنده\s*$", line)
            if match:
                winner = match.group(1).strip()
                game = "Mafia"
                break

    if not winner:
        return None

    return {"game": game, "winner": winner}


# ==================================================
# 🛡️ DUPLICATE PROTECTION
# ==================================================
def result_already_processed(chat_id, message_id):
    conn = get_db()
    row = conn.execute("""SELECT 1 FROM processed_results
    WHERE chat_id=? AND message_id=?""", (chat_id, message_id)).fetchone()
    conn.close()
    return row is not None


def mark_result_processed(chat_id, message_id):
    conn = get_db()
    conn.execute("""INSERT OR IGNORE INTO processed_results
    (chat_id,message_id) VALUES (?,?)""", (chat_id, message_id))
    conn.commit()
    conn.close()


# ==================================================
# 📊 PROFILE TEXT
# ==================================================
def build_profile(player):
    xp = player["xp"]
    level = get_level(xp)
    title = get_title(level)
    _, current, needed, percent = get_level_progress(xp)

    next_text = "👑 MAX LEVEL" if needed is None else f"{current} / {needed} XP ({percent:.0f}%)"
    username = "@" + player["username"] if player["username"] else "—"
    uid = player["user_id"]

    return f"""────┄ׅ ⊹ ┄────
ㅤㅤ𝓝𝗈𝗑𝖺𝗋𝖺 𝓟𝗋𝗈𝖿𝗂𝗅𝖾
────┄ׅ ⊹ ┄────

👤 NAME : {player["name"]}
🆔 ID : {uid}
🔗 USERNAME : {username}

⚡️ XP : {xp}
🔥 LEVEL : {level} / 50
👑 TITLE : {title}
📊 PROGRESS : {next_text}
🏆 WEEKLY XP : {player["weekly_xp"]}

─┄ׅ ⊹ ┄─

🎮 GAMES

💣 Minesweeper : {player["minesweeper_wins"]}
🎯 Dose : {player["dose_wins"]}
😈 Spy : {get_game_wins(uid,"Spy")}
⚪️⚫️ Othello : {get_game_wins(uid,"Othello")}
🔪 Mafia : {get_game_wins(uid,"Mafia")}

🏆 TOTAL WINS : {total_wins(player)}

────┄ׅ ⊹ ┄────
🎰 Noxara XP System
"""


# ==================================================
# 📩 GAME REWARD MESSAGE
# ==================================================
async def send_reward_message(message, player, game, xp_gain, old_level, new_achievements):
    updated = get_player_by_id(player["user_id"])
    new_level = get_level(updated["xp"])
    name = player_display(updated)

    text = f"""🎉 𝗡𝗢𝗫𝗔𝗥𝗔 𝗥𝗘𝗪𝗔𝗥𝗗

🏆 تبریک {name}!
🎮 برنده‌ی {game} شدی.

⚡️ +{xp_gain} XP دریافت کردی!
💰 Total XP : {updated["xp"]}
🔥 Level : {new_level} / 50
👑 Title : {get_title(new_level)}
🏆 Weekly XP : {updated["weekly_xp"]}"""

    if new_level > old_level:
        text += f"""

━━━━━━━━━━━━━━
🆙 𝗟𝗘𝗩𝗘𝗟 𝗨𝗣!

🎉 {name} به Level {new_level} رسید!
👑 New Title : {get_title(new_level)}
━━━━━━━━━━━━━━"""

    if new_achievements:
        text += "\n\n🏅 NEW ACHIEVEMENT:"
        for aid in new_achievements:
            achievement = get_achievement(aid)
            if achievement:
                text += f"\n{achievement['emoji']} {achievement['title']}"

    await message.reply_text(text)


# ==================================================
# 🎮 PROCESS RESULT
# ==================================================
async def process_game_result(update, text):
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    if result_already_processed(chat.id, message.message_id):
        return

    result = check_game_result(text)
    if not result:
        return

    winner_player = find_player(result["winner"])
    if not winner_player:
        print(f"⚠️ WINNER NOT FOUND: {result['winner']}")
        return

    old_level = get_level(winner_player["xp"])
    xp_gain = add_win_to_player(winner_player["user_id"], result["game"])
    if xp_gain <= 0:
        return

    mark_result_processed(chat.id, message.message_id)
    newly_unlocked = check_achievements(winner_player["user_id"])

    await send_reward_message(
        message,
        winner_player,
        result["game"],
        xp_gain,
        old_level,
        newly_unlocked
    )

    print(f"🏆 {result['game']} | {result['winner']} | +{xp_gain} XP")


# ==================================================
# 👤 COMMANDS
# ==================================================
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    register_user(user)

    if context.args:
        if not is_admin(user.id):
            await update.message.reply_text("🔒 فقط Adminها می‌توانند پروفایل دیگران را ببینند.")
            return
        player = find_player(context.args[0])
        if not player:
            await update.message.reply_text("❌ بازیکن پیدا نشد.")
            return
    else:
        player = get_player(user)

    await update.message.reply_text(build_profile(player))


async def xp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    register_user(user)

    if context.args:
        if not is_admin(user.id):
            await update.message.reply_text("🔒 فقط Adminها می‌توانند XP دیگران را ببینند.")
            return
        player = find_player(context.args[0])
    else:
        player = get_player(user)

    if not player:
        await update.message.reply_text("❌ بازیکن پیدا نشد.")
        return

    level, current, needed, percent = get_level_progress(player["xp"])
    progress = "MAX LEVEL 👑" if needed is None else f"{current}/{needed} XP ({percent:.0f}%)"

    await update.message.reply_text(
        f"⚡️ NOXARA XP\n\n"
        f"👤 {player_display(player)}\n"
        f"⚡️ XP : {player['xp']}\n"
        f"🔥 Level : {level}/50\n"
        f"👑 Title : {get_title(level)}\n"
        f"📊 Progress : {progress}\n"
        f"🏆 Weekly XP : {player['weekly_xp']}"
    )


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    players = conn.execute("""SELECT * FROM players WHERE xp>0
    ORDER BY xp DESC,user_id ASC LIMIT 10""").fetchall()
    conn.close()

    if not players:
        await update.message.reply_text("🏆 هنوز کسی XP ندارد.")
        return

    medals = {1:"🥇",2:"🥈",3:"🥉"}
    text = "────┄ׅ ⊹ ┄────\n🏆 𝓝𝗈𝗑𝖺𝗋𝖺 𝓛𝖾𝖺𝖽𝖾𝗋𝖻𝗈𝖺𝗋𝖽\n────┄ׅ ⊹ ┄────\n"

    for rank, p in enumerate(players, 1):
        text += (f"\n{medals.get(rank,str(rank)+'.')} {player_display(p)}\n"
                 f"   ⚡️ XP: {p['xp']}\n"
                 f"   🔥 Level: {get_level(p['xp'])}/50\n"
                 f"   👑 {get_title(get_level(p['xp']))}\n")

    await update.message.reply_text(text)


async def weekly_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_weekly_reset()
    conn = get_db()
    players = conn.execute("""SELECT * FROM players WHERE weekly_xp>=?
    ORDER BY weekly_xp DESC,user_id ASC LIMIT 10""", (WEEKLY_MIN_XP,)).fetchall()
    conn.close()

    start = get_week_start()
    end = start + timedelta(days=6)

    text = f"""────┄ׅ ⊹ ┄────
🏆 𝓝𝗈𝗑𝖺𝗋𝖺 Weekly Chart
────┄ׅ ⊹ ┄────

📅 {start.strftime("%Y/%m/%d")} تا {end.strftime("%Y/%m/%d")}
⚡️ حداقل ورود: {WEEKLY_MIN_XP} XP

"""

    if not players:
        text += "🔒 هنوز کسی به حداقل XP لازم نرسیده."
    else:
        medals = {1:"🥇",2:"🥈",3:"🥉"}
        for rank, p in enumerate(players, 1):
            vip = " 👑 VIP CANDIDATE" if rank <= 2 else ""
            text += f"{medals.get(rank,str(rank)+'.')} {player_display(p)}{vip}\n   ⚡️ {p['weekly_xp']} Weekly XP\n"

    await update.message.reply_text(text)


async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    register_user(user)
    rows = get_player_achievements(user.id)

    text = "🏅 NOXARA ACHIEVEMENTS\n\n"
    if not rows:
        text += "🔒 هنوز Achievementی باز نشده."
    else:
        for a in rows:
            text += f"{a['emoji']} {a['title']}\n└─ {a['description']}\n\n"

    await update.message.reply_text(text)


# ==================================================
# 🛠️ ADMIN XP COMMANDS
# ==================================================
async def require_admin(update):
    user = update.effective_user
    return bool(user and is_admin(user.id))


async def add_xp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        await update.message.reply_text("🔒 این دستور فقط برای Adminهاست.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("استفاده:\n/addxp @username amount")
        return

    player = find_player(context.args[0])
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ مقدار XP باید عدد باشد.")
        return

    if not player or amount <= 0:
        await update.message.reply_text("❌ بازیکن یا مقدار XP نامعتبر است.")
        return

    old_level = get_level(player["xp"])
    conn = get_db()
    conn.execute("""UPDATE players SET xp=xp+?,weekly_xp=weekly_xp+?
    WHERE user_id=?""", (amount, amount, player["user_id"]))
    conn.commit()
    conn.close()

    updated = get_player_by_id(player["user_id"])
    check_achievements(updated["user_id"])

    text = (f"✅ {player_display(updated)}\n➕ +{amount} XP\n"
            f"⚡️ Total XP: {updated['xp']}\n"
            f"🔥 Level: {get_level(updated['xp'])}/50\n"
            f"👑 Title: {get_title(get_level(updated['xp']))}")

    if get_level(updated["xp"]) > old_level:
        text += "\n\n🆙 LEVEL UP!"

    await update.message.reply_text(text)


async def remove_xp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        await update.message.reply_text("🔒 این دستور فقط برای Adminهاست.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("استفاده:\n/removexp @username amount")
        return

    player = find_player(context.args[0])
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ مقدار XP باید عدد باشد.")
        return

    if not player or amount <= 0:
        await update.message.reply_text("❌ بازیکن یا مقدار نامعتبر است.")
        return

    new_xp = max(0, player["xp"] - amount)
    new_weekly = max(0, player["weekly_xp"] - amount)

    conn = get_db()
    conn.execute("UPDATE players SET xp=?,weekly_xp=? WHERE user_id=?",
                 (new_xp, new_weekly, player["user_id"]))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"➖ {player_display(player)}\n"
        f"⚡️ Total XP: {new_xp}\n"
        f"🔥 Level: {get_level(new_xp)}/50\n"
        f"👑 Title: {get_title(get_level(new_xp))}"
    )


async def set_xp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        await update.message.reply_text("🔒 این دستور فقط برای Adminهاست.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("استفاده:\n/setxp @username amount")
        return

    player = find_player(context.args[0])
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ XP باید عدد باشد.")
        return

    if not player or amount < 0:
        await update.message.reply_text("❌ بازیکن یا مقدار نامعتبر است.")
        return

    conn = get_db()
    conn.execute("UPDATE players SET xp=? WHERE user_id=?", (amount, player["user_id"]))
    conn.commit()
    conn.close()
    check_achievements(player["user_id"])

    await update.message.reply_text(
        f"🎯 {player_display(player)}\n"
        f"⚡️ XP: {amount}\n"
        f"🔥 Level: {get_level(amount)}/50\n"
        f"👑 Title: {get_title(get_level(amount))}"
    )


async def set_game_xp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        await update.message.reply_text("🔒 این دستور فقط برای Adminهاست.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("استفاده:\n/setgamexp Game amount")
        return

    game = get_game(context.args[0])
    try:
        amount = int(context.args[1])
    except ValueError:
        amount = 0

    if not game or amount <= 0:
        await update.message.reply_text("❌ بازی یا مقدار XP نامعتبر است.")
        return

    set_game_xp(game["game_name"], amount)
    await update.message.reply_text(f"🎮 {game['game_name']}\n⚡️ XP per win: {get_game_xp(game['game_name'])}")


async def bonus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        await update.message.reply_text("🔒 این دستور فقط برای Adminهاست.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("استفاده:\n/bonus Dose 2x\n/bonus Dose off")
        return

    game = get_game(context.args[0])
    if not game:
        await update.message.reply_text("❌ این بازی ثبت نشده.")
        return

    value = context.args[1].lower()
    if value == "off":
        set_bonus(game["game_name"], 1)
        await update.message.reply_text("🎁 Bonus خاموش شد.")
        return

    match = re.match(r"^(\d+(?:\.\d+)?)x$", value)
    if not match or float(match.group(1)) <= 0:
        await update.message.reply_text("❌ مثال: /bonus Dose 2x")
        return

    multiplier = float(match.group(1))
    set_bonus(game["game_name"], multiplier)
    await update.message.reply_text(
        f"🎁 BONUS ACTIVATED\n🎮 {game['game_name']}\n"
        f"🔥 {multiplier:g}x\n⚡️ XP: {get_game_xp(game['game_name'])}"
    )


async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        await update.message.reply_text("🔒 فقط Adminها.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("استفاده:\n/addadmin USER_ID")
        return
    add_admin(int(context.args[0]))
    await update.message.reply_text("👑 Admin اضافه شد.")


async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        await update.message.reply_text("🔒 فقط Adminها.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("استفاده:\n/removeadmin USER_ID")
        return

    conn = get_db()
    count = conn.execute("SELECT COUNT(*) AS count FROM admins").fetchone()["count"]
    conn.close()

    if count <= 1:
        await update.message.reply_text("❌ نمی‌توان آخرین Admin را حذف کرد.")
        return

    remove_admin(int(context.args[0]))
    await update.message.reply_text("🗑 Admin حذف شد.")


async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        await update.message.reply_text("🔒 فقط Adminها.")
        return
    conn = get_db()
    admins = conn.execute("SELECT user_id FROM admins ORDER BY user_id").fetchall()
    conn.close()
    await update.message.reply_text("👑 NOXARA ADMINS\n\n" + "\n".join(f"🆔 {a['user_id']}" for a in admins))


async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    games = conn.execute("SELECT * FROM games ORDER BY xp ASC,game_name ASC").fetchall()
    conn.close()

    text = "🎮 NOXARA GAMES\n\n"
    for game in games:
        text += (f"🎮 {game['game_name']}\n"
                 f"⭐ Base XP: {game['xp']}\n"
                 f"🎁 Bonus: {game['bonus_multiplier']:g}x\n"
                 f"⚡️ Current XP: {get_game_xp(game['game_name'])}\n\n")
    await update.message.reply_text(text)


# ==================================================
# 📩 MESSAGE HANDLERS
# ==================================================
async def new_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    if update.effective_user:
        register_user(update.effective_user)

    await process_game_result(update, message.text)


async def edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.edited_message
    if not message or not message.text:
        return
    await process_game_result(update, message.text)


# ==================================================
# 🚀 START
# ==================================================
init_database()

app = Application.builder().token(TOKEN).build()

commands = [
    ("profile", profile),
    ("xp", xp_command),
    ("leaderboard", leaderboard_command),
    ("weekly", weekly_command),
    ("achievements", achievements_command),
    ("addxp", add_xp_command),
    ("removexp", remove_xp_command),
    ("setxp", set_xp_command),
    ("setgamexp", set_game_xp_command),
    ("bonus", bonus_command),
    ("addadmin", add_admin_command),
    ("removeadmin", remove_admin_command),
    ("admins", admins_command),
    ("games", games_command),
]

for command, handler in commands:
    app.add_handler(CommandHandler(command, handler))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, new_message))
app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, edited_message))

print("====================================")
print("       🖤 NOXARA XP SYSTEM")
print("====================================")
print("🔥 Level System: 1 → 50")
print("👑 Final Title: The Noxara")
print("🎮 Auto reward messages: ON")
print("🛡️ Duplicate protection: ON")
print("====================================")

app.run_polling()

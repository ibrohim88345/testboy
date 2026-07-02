import os, json, re, io
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER

BOT_TOKEN     = "8950300608:AAGKzpg2uIyKlijdgO7JhdMZLpo2nYIuHzo"
CHANNEL_USER  = "@huquqologiyauz"
CHANNEL_LINK  = "https://t.me/huquqologiyauz"
DATA_DIR      = "/data" if os.path.exists("/data") else "."
DATA_FILE     = os.path.join(DATA_DIR, "data.json")
UZT           = timezone(timedelta(hours=5))

# ── Vaqt ──────────────────────────────────────────────
def now_uzt():
    return datetime.now(UZT)

def fmt(iso):
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UZT)
        return dt.astimezone(UZT).strftime("%d.%m.%Y %H:%M:%S")
    except:
        return iso

# ── Ma'lumotlar ────────────────────────────────────────
def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tests": {}, "results": {}}

def save(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

# ── Kanal ─────────────────────────────────────────────
async def subscribed(uid, bot):
    try:
        m = await bot.get_chat_member(CHANNEL_USER, uid)
        return m.status in ("member", "administrator", "creator")
    except Exception as e:
        print(f"kanal xato: {e}")
        return True   # Agar bot admin bo'lmasa o'tkazib yuboramiz

def sub_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Kanalga a'zo bo'lish", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ A'zo bo'ldim, tekshir", callback_data="check_sub")]
    ])

async def need_sub(update, bot):
    uid = update.effective_user.id
    ok = await subscribed(uid, bot)
    if not ok:
        msg = update.message or update.callback_query.message
        await msg.reply_text(
            f"⚠️ Botdan foydalanish uchun kanalga a'zo bo'ling!\n\n{CHANNEL_LINK}",
            reply_markup=sub_kb()
        )
    return ok

# ── Javob parse ────────────────────────────────────────
def parse_ans(text):
    text = text.strip().lower().replace(" ", "")
    bad = re.findall(r'\d+[a-e]{2,}', text)
    if bad:
        return None, f"❌ Xato: `{'  '.join(bad)}` — har savolga faqat 1 ta harf"
    pairs = re.findall(r'(\d+)([a-e])', text)
    if not pairs:
        return None, "❌ Format noto'g'ri. Misol: `1a2b3c4d5e`"
    ans, seen = {}, set()
    for ns, l in pairs:
        n = int(ns)
        if n in seen:
            return None, f"❌ {n}-savol uchun bir nechta javob kiritildi!"
        ans[n] = l; seen.add(n)
    return ans, None

def score(correct, user):
    total = len(correct)
    right, wrong, miss = 0, [], []
    for k, v in correct.items():
        k = int(k)
        if k in user:
            if user[k] == v: right += 1
            else: wrong.append((k, user[k], v))
        else: miss.append(k)
    return {"total": total, "right": right, "wrong": wrong, "miss": miss,
            "pct": round(right/total*100, 1) if total else 0}

# ── State tizimi ───────────────────────────────────────
STATES = {}
def gs(uid): return STATES.get(uid, {})
def ss(uid, state, **kw): STATES[uid] = {"s": state, **kw}
def cs(uid): STATES.pop(uid, None)

# ── Klaviatura ─────────────────────────────────────────
def main_kb(uid, d):
    has_mine = any(t.get("owner_id") == uid for t in d["tests"].values())
    has_res  = any(any(r["user_id"] == uid for r in d["results"].get(tid, []))
                   for tid in d["tests"])
    rows = [
        [KeyboardButton("📝 Testga javob berish")],
        [KeyboardButton("➕ Test qo'shish")],
    ]
    if has_mine: rows.append([KeyboardButton("📋 Mening testlarim")])
    if has_res:  rows.append([KeyboardButton("🔍 Natijalarim")])
    rows.append([KeyboardButton("ℹ️ Yordam")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def test_kb(tid, active):
    rows = []
    if active:
        rows.append([InlineKeyboardButton("🏁 Yakunlash", callback_data=f"end|{tid}")])
    rows.append([
        InlineKeyboardButton("📊 PDF", callback_data=f"pdf|{tid}"),
        InlineKeyboardButton("📝 Matn", callback_data=f"txt|{tid}")
    ])
    rows.append([InlineKeyboardButton("🗑 O'chirish", callback_data=f"del|{tid}")])
    rows.append([InlineKeyboardButton("◀️ Ro'yxatga qaytish", callback_data="my_tests")])
    return InlineKeyboardMarkup(rows)

def my_tests_kb(uid, d):
    my = {k: v for k, v in d["tests"].items() if v.get("owner_id") == uid}
    if not my: return None
    rows = []
    for tid, t in my.items():
        st  = "🟢" if t.get("active") else "🔴"
        cnt = len(d["results"].get(tid, []))
        rows.append([InlineKeyboardButton(f"{st} {t['name']} ({cnt} javob)", callback_data=f"ti|{tid}")])
    return InlineKeyboardMarkup(rows)

# ── /start ─────────────────────────────────────────────
async def cmd_start(update, ctx):
    uid = update.effective_user.id
    cs(uid)
    if not await need_sub(update, ctx.bot): return
    d = load()
    await update.message.reply_text(
        f"👋 Salom, {update.effective_user.first_name}!\n\n🤖 *Test Bot*ga xush kelibsiz!\nQuyidagi tugmalardan foydalaning 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_kb(uid, d)
    )

async def cmd_cancel(update, ctx):
    uid = update.effective_user.id; cs(uid); d = load()
    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=main_kb(uid, d))

# ── Kanal callback ─────────────────────────────────────
async def cb_check_sub(update, ctx):
    q = update.callback_query; await q.answer()
    ok = await subscribed(q.from_user.id, ctx.bot)
    if not ok:
        await q.edit_message_text(f"❌ Hali a'zo bo'lmadingiz!\n\n{CHANNEL_LINK}", reply_markup=sub_kb())
        return
    d = load()
    await q.edit_message_text("✅ Kanalga a'zo bo'lgansiz!")
    await ctx.bot.send_message(q.message.chat_id, "Quyidagi tugmalardan foydalaning 👇",
                               reply_markup=main_kb(q.from_user.id, d))

# ── TEST QO'SHISH ──────────────────────────────────────
async def start_add(update, ctx):
    uid = update.effective_user.id
    if not await need_sub(update, ctx.bot): return
    ss(uid, "add_name")
    await update.message.reply_text(
        "➕ *Yangi test qo'shish*\n\n1️⃣ Test nomini yuboring:\n_(Misol: Jinoyat huquqi — 1-variant)_\n\n/cancel — bekor qilish",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )

async def h_add_name(update, ctx):
    uid = update.effective_user.id
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("❌ Nom juda qisqa. Qayta yuboring:"); return
    ss(uid, "add_id", name=name)
    await update.message.reply_text(
        f"✅ Nom: *{name}*\n\n2️⃣ Test IDsini kiriting (lotin harf/raqam/_):\n_(Misol: huquq1, test2)_",
        parse_mode=ParseMode.MARKDOWN
    )

async def h_add_id(update, ctx):
    uid = update.effective_user.id; st = gs(uid); d = load()
    tid = update.message.text.strip().lower().replace(" ", "_")
    if not re.match(r'^[a-z0-9_]+$', tid):
        await update.message.reply_text("❌ Faqat lotin harf, raqam, _ kiriting:"); return
    if tid in d["tests"]:
        await update.message.reply_text(f"⚠️ `{tid}` ID allaqachon bor. Boshqasini kiriting:", parse_mode=ParseMode.MARKDOWN); return
    ss(uid, "add_ans", name=st["name"], tid=tid)
    await update.message.reply_text(
        f"✅ ID: `{tid}`\n\n3️⃣ To'g'ri javoblarni yuboring:\n📌 Format: `1a2b3c4d5e...`\n_(Har savolga faqat 1 harf: a b c d e)_",
        parse_mode=ParseMode.MARKDOWN
    )

async def h_add_ans(update, ctx):
    uid = update.effective_user.id; st = gs(uid); d = load()
    ans, err = parse_ans(update.message.text)
    if err:
        await update.message.reply_text(err + "\n\nQayta yuboring:", parse_mode=ParseMode.MARKDOWN); return
    tid = st["tid"]
    d["tests"][tid] = {
        "name": st["name"], "answers": {str(k): v for k, v in ans.items()},
        "created_at": now_uzt().isoformat(), "active": True, "owner_id": uid
    }
    d["results"][tid] = []
    save(d); cs(uid)
    await update.message.reply_text(
        f"✅ *Test qo'shildi!*\n\n📋 Nom: *{st['name']}*\n🔑 ID: `{tid}`\n📊 Savollar: *{len(ans)}* ta\n🟢 Holat: Faol\n\nKanalda ID: `{tid}` deb e'lon qiling.",
        parse_mode=ParseMode.MARKDOWN, reply_markup=main_kb(uid, d)
    )

# ── JAVOB BERISH ───────────────────────────────────────
async def start_sub(update, ctx):
    uid = update.effective_user.id
    if not await need_sub(update, ctx.bot): return
    d = load()
    active = {k: v for k, v in d["tests"].items() if v.get("active")}
    if not active:
        await update.message.reply_text("📭 Hozirda faol test yo'q.", reply_markup=main_kb(uid, d)); return
    ss(uid, "sub_fn")
    await update.message.reply_text(
        "✍️ *Javob berish*\n\n1️⃣ Ism va familiyangizni yuboring:\n_(Misol: Usmonov Ibrohim)_\n\n/cancel — bekor qilish",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )

async def h_sub_fn(update, ctx):
    uid = update.effective_user.id; d = load()
    fn = update.message.text.strip()
    if len(fn) < 3:
        await update.message.reply_text("❌ Ism familiya juda qisqa. Qayta yuboring:"); return
    active = {k: v for k, v in d["tests"].items() if v.get("active")}
    tlist = "\n".join([f"🔹 *{t['name']}* — `{tid}`" for tid, t in active.items()])
    ss(uid, "sub_tid", fn=fn)
    await update.message.reply_text(
        f"👤 Siz: *{fn}*\n\n2️⃣ Test IDsini yuboring:\n\n*Faol testlar:*\n{tlist}",
        parse_mode=ParseMode.MARKDOWN
    )

async def h_sub_tid(update, ctx):
    uid = update.effective_user.id; st = gs(uid); d = load()
    tid = update.message.text.strip().lower()
    if tid not in d["tests"]:
        await update.message.reply_text(f"❌ `{tid}` topilmadi. To'g'ri ID kiriting:", parse_mode=ParseMode.MARKDOWN); return
    if not d["tests"][tid].get("active"):
        await update.message.reply_text(f"⚠️ `{tid}` testi yakunlangan.", parse_mode=ParseMode.MARKDOWN); return
    # Bir marta tekshiruvi
    existing = next((r for r in d["results"].get(tid, []) if r["user_id"] == uid), None)
    if existing:
        cs(uid); tq = len(d["tests"][tid]["answers"])
        pct = round(existing["score"]/tq*100, 1) if tq else 0
        await update.message.reply_text(
            f"⛔️ *Siz bu testga allaqachon javob yuborgansiz!*\n\n👤 {existing.get('fullname','')}\n"
            f"✅ Natija: *{existing['score']}/{tq}* ({pct}%)\n🕐 {fmt(existing['date'])}\n\n"
            f"⚠️ Har bir test uchun faqat 1 marta javob yuborish mumkin.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=main_kb(uid, d)
        ); return
    t = d["tests"][tid]
    ss(uid, "sub_ans", fn=st["fn"], tid=tid)
    await update.message.reply_text(
        f"✅ Test: *{t['name']}*\n📊 Savollar: *{len(t['answers'])}* ta\n\n"
        f"3️⃣ Javoblaringizni yuboring:\n📌 `1a2b3c4d5e...`\n\n⚠️ *Faqat 1 marta yuborish mumkin!*",
        parse_mode=ParseMode.MARKDOWN
    )

async def h_sub_ans(update, ctx):
    uid = update.effective_user.id; st = gs(uid); d = load()
    tid = st["tid"]; fn = st["fn"]
    t = d["tests"].get(tid)
    if not t:
        await update.message.reply_text("❌ Test topilmadi. /start bosing."); cs(uid); return
    if next((r for r in d["results"].get(tid, []) if r["user_id"] == uid), None):
        await update.message.reply_text("⛔️ Allaqachon javob yuborgansiz.", reply_markup=main_kb(uid, d)); cs(uid); return
    ans, err = parse_ans(update.message.text)
    if err:
        await update.message.reply_text(err + "\n\nQayta yuboring:", parse_mode=ParseMode.MARKDOWN); return
    correct = {int(k): v for k, v in t["answers"].items()}
    res = score(correct, ans)
    now = now_uzt().isoformat()
    entry = {"user_id": uid, "username": update.effective_user.username or "",
             "fullname": fn, "answers": {str(k): v for k, v in ans.items()},
             "score": res["right"], "date": now}
    d["results"].setdefault(tid, []).append(entry)
    save(d); cs(uid)
    pct = res["pct"]
    em = "🏆" if pct>=80 else ("👍" if pct>=60 else ("📚" if pct>=40 else "💪"))
    gr = "A'lo" if pct>=80 else ("Yaxshi" if pct>=60 else ("Qoniqarli" if pct>=40 else "Qayta o'qing"))
    await update.message.reply_text(
        f"✅ *Javobingiz qabul qilindi!*\n\n👤 {fn}\n📋 *{t['name']}*\n"
        f"📊 Natija: *{res['right']}/{res['total']}* to'g'ri\n📈 Foiz: *{pct}%*\n{em} Baho: *{gr}*\n\n"
        f"🏁 Test yakunlangach xatolaringizni ko'rishingiz mumkin!",
        parse_mode=ParseMode.MARKDOWN, reply_markup=main_kb(uid, d)
    )
    # Egaga bildiruv
    owner = t.get("owner_id")
    if owner:
        try:
            detail = []
            for num in sorted(correct.keys()):
                c = correct[num]; u = ans.get(num)
                if u is None: detail.append(f"⚪️ {num}: javob yo'q (to'g'ri: {c.upper()})")
                elif u == c:  detail.append(f"✅ {num}: {u.upper()}")
                else:         detail.append(f"❌ {num}: {u.upper()} → {c.upper()}")
            detail_txt = "\n".join(detail)
            if len(detail_txt) > 3000:
                wrongs = [l for l in detail if l.startswith("❌") or l.startswith("⚪️")]
                detail_txt = "\n".join(wrongs) + f"\n\n_✅ {res['right']} ta to'g'ri_"
            await ctx.bot.send_message(owner,
                f"🔔 *Yangi javob!*\n\n👤 *{fn}*\n📋 *{t['name']}* (`{tid}`)\n"
                f"📊 *{res['right']}/{res['total']}* ({pct}%)\n🕐 {fmt(now)}\n\n"
                f"*Tahlil:*\n{detail_txt}", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            print(f"Bildiruv xato: {e}")

# ── MENING TESTLARIM ───────────────────────────────────
async def show_my_tests(update, ctx):
    uid = update.effective_user.id
    if not await need_sub(update, ctx.bot): return
    d = load()
    kb = my_tests_kb(uid, d)
    if not kb:
        await update.message.reply_text("📭 Sizda hech qanday test yo'q.\n➕ Test qo'shish tugmasini bosing!",
                                        reply_markup=main_kb(uid, d)); return
    await update.message.reply_text("📋 *Mening testlarim:*\n\nBoshqarish uchun tanlang 👇",
                                    parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def cb_my_tests(update, ctx):
    q = update.callback_query; await q.answer()
    d = load(); kb = my_tests_kb(q.from_user.id, d)
    if not kb:
        await q.edit_message_text("📭 Sizda test yo'q."); return
    await q.edit_message_text("📋 *Mening testlarim:*\n\nBoshqarish uchun tanlang 👇",
                              parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def cb_test_info(update, ctx):
    q = update.callback_query; await q.answer()
    _, tid = q.data.split("|", 1)
    d = load(); t = d["tests"].get(tid)
    if not t:
        await q.edit_message_text("❌ Test topilmadi."); return
    if t.get("owner_id") != q.from_user.id:
        await q.edit_message_text("❌ Bu test sizniki emas."); return
    cnt = len(d["results"].get(tid, []))
    st = "🟢 Faol" if t.get("active") else "🔴 Yakunlangan"
    await q.edit_message_text(
        f"📋 *{t['name']}*\n\n🔑 ID: `{tid}`\n📊 Savollar: *{len(t['answers'])}* ta\n"
        f"👥 Javoblar: *{cnt}* ta\n📍 Holat: {st}\n📅 Yaratilgan: {t['created_at'][:10]}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=test_kb(tid, t.get("active", False))
    )

async def cb_action(update, ctx):
    q = update.callback_query; await q.answer()
    action, tid = q.data.split("|", 1)
    d = load(); t = d["tests"].get(tid)
    if not t:
        await q.edit_message_text("❌ Test topilmadi."); return
    if t.get("owner_id") != q.from_user.id:
        await q.edit_message_text("❌ Ruxsat yo'q."); return
    results = d["results"].get(tid, [])
    correct = {int(k): v for k, v in t["answers"].items()}

    if action == "end":
        d["tests"][tid]["active"] = False; save(d)
        await q.edit_message_text(
            f"✅ *{t['name']}* yakunlandi!\n\n👥 {len(results)} ta ishtirokchi\n📍 Holat: 🔴 Yakunlangan",
            parse_mode=ParseMode.MARKDOWN, reply_markup=test_kb(tid, False)
        )

    elif action == "pdf":
        if not results:
            await q.edit_message_text("📭 Natijalar yo'q."); return
        await q.edit_message_text("⏳ PDF tayyorlanmoqda...")
        pdf = make_pdf(t["name"], results, correct)
        fname = f"stat_{tid}_{now_uzt().strftime('%Y%m%d_%H%M')}.pdf"
        await ctx.bot.send_document(q.message.chat_id, io.BytesIO(pdf), filename=fname,
            caption=f"📊 *{t['name']}*\n👥 {len(results)} ta ishtirokchi", parse_mode=ParseMode.MARKDOWN)
        await q.delete_message()

    elif action == "txt":
        if not results:
            await q.edit_message_text("📭 Natijalar yo'q."); return
        tq = len(correct)
        srt = sorted(results, key=lambda x: (-x["score"], x.get("date","")))
        scores = [r["score"] for r in results]
        txt = (f"📊 *{t['name']}*\n📅 {now_uzt().strftime('%d.%m.%Y %H:%M:%S')}\n"
               f"─────────────────────\n"
               f"👥 Ishtirokchi: *{len(results)}*\n"
               f"📈 O'rtacha: *{round(sum(scores)/len(scores),1)}/{tq}*\n"
               f"🏆 Yuqori: *{max(scores)}/{tq}*\n📉 Past: *{min(scores)}/{tq}*\n"
               f"─────────────────────\n\n")
        for i, r in enumerate(srt, 1):
            med = {1:"🥇",2:"🥈",3:"🥉"}.get(i, f"{i}.")
            pct = round(r["score"]/tq*100, 1) if tq else 0
            txt += f"{med} *{r.get('fullname','?')}* — {r['score']}/{tq} ({pct}%) | {fmt(r.get('date',''))}\n"
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN)

    elif action == "del":
        await q.edit_message_text(
            f"⚠️ *{t['name']}* testini o'chirishni tasdiqlaysizmi?\nBu amal qaytarilmaydi!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Ha, o'chir", callback_data=f"delok|{tid}")],
                [InlineKeyboardButton("❌ Yo'q", callback_data=f"ti|{tid}")]
            ])
        )

async def cb_delok(update, ctx):
    q = update.callback_query; await q.answer()
    _, tid = q.data.split("|", 1); d = load()
    t = d["tests"].get(tid)
    if not t or t.get("owner_id") != q.from_user.id:
        await q.edit_message_text("❌ Ruxsat yo'q."); return
    name = t["name"]
    del d["tests"][tid]; d["results"].pop(tid, None); save(d)
    await q.edit_message_text(f"✅ *{name}* o'chirildi.", parse_mode=ParseMode.MARKDOWN)

# ── NATIJALARIM ────────────────────────────────────────
async def show_results(update, ctx):
    uid = update.effective_user.id
    if not await need_sub(update, ctx.bot): return
    d = load()
    part = [(tid, t) for tid, t in d["tests"].items()
            if any(r["user_id"] == uid for r in d["results"].get(tid, []))]
    if not part:
        await update.message.reply_text("📭 Siz hali hech qanday testga javob bermadingiz.",
                                        reply_markup=main_kb(uid, d)); return
    rows = []
    for tid, t in part:
        st = "🟢" if t.get("active") else "🔴"
        rows.append([InlineKeyboardButton(f"{st} {t['name']}", callback_data=f"myres|{tid}")])
    await update.message.reply_text("🔍 Qaysi testdagi natijangizni ko'rmoqchisiz?",
                                    reply_markup=InlineKeyboardMarkup(rows))

async def cb_my_result(update, ctx):
    q = update.callback_query; await q.answer()
    _, tid = q.data.split("|", 1); d = load()
    t = d["tests"].get(tid); uid = q.from_user.id
    entry = next((r for r in d["results"].get(tid, []) if r["user_id"] == uid), None)
    if not entry:
        await q.edit_message_text("❌ Siz bu testda qatnashmadingiz."); return
    tq = len(t["answers"])
    pct = round(entry["score"]/tq*100, 1) if tq else 0

    if t.get("active"):
        await q.edit_message_text(
            f"📊 *{t['name']}*\n\n👤 {entry.get('fullname','')}\n"
            f"✅ Natija: *{entry['score']}/{tq}* ({pct}%)\n🕐 {fmt(entry['date'])}\n\n"
            f"⏳ Test hali faol — xatolar test yakunlangach ko'rinadi.",
            parse_mode=ParseMode.MARKDOWN); return

    correct = {int(k): v for k, v in t["answers"].items()}
    user_ans = {int(k): v for k, v in entry["answers"].items()}
    res = score(correct, user_ans)
    lines = []
    for num in sorted(correct.keys()):
        c = correct[num]; u = user_ans.get(num)
        if u is None: lines.append(f"⚪️ {num}: javob yo'q (to'g'ri: *{c.upper()}*)")
        elif u == c:  lines.append(f"✅ {num}: *{u.upper()}*")
        else:         lines.append(f"❌ {num}: *{u.upper()}* → to'g'ri: *{c.upper()}*")
    header = (f"📊 *{t['name']}* — Natijangiz\n\n"
              f"👤 {entry.get('fullname','')}\n"
              f"✅ To'g'ri: *{res['right']}/{res['total']}* ({res['pct']}%)\n"
              f"🕐 {fmt(entry['date'])}\n\n*Tahlil:*\n")
    body = "\n".join(lines)
    msg = header + body
    if len(msg) > 4000:
        bad = [l for l in lines if l.startswith("❌") or l.startswith("⚪️")]
        msg = header + ("\n".join(bad) if bad else "🎉 Barcha javoblar to'g'ri!")
    if not res["wrong"] and not res["miss"]:
        msg = header + "🎉 Barcha javoblar to'g'ri edi!"
    await q.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)

# ── YORDAM ─────────────────────────────────────────────
async def show_help(update, ctx):
    uid = update.effective_user.id; d = load()
    await update.message.reply_text(
        "ℹ️ *Yordam*\n\n"
        "📝 *Javob berish:* Ism → Test ID → Javoblar\n"
        "➕ *Test qo'shish:* Nom → ID → `1a2b3c...`\n"
        "📋 *Testlarim:* Boshqarish, statistika, yakunlash\n"
        "🔍 *Natijalarim:* Natija va xatolarni ko'rish\n\n"
        "📌 Javob formati: `1a2b3c4d5e`\n_(raqam + 1 harf)_\n\n"
        f"📢 Kanal: {CHANNEL_LINK}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=main_kb(uid, d)
    )

# ── PDF ────────────────────────────────────────────────
def make_pdf(test_name, results, correct):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
          rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=2*cm, bottomMargin=1.5*cm)
    PRI=colors.HexColor('#1a237e'); SEC=colors.HexColor('#283593')
    ACC=colors.HexColor('#e8eaf6'); GRN=colors.HexColor('#2e7d32')
    RED=colors.HexColor('#c62828'); GLD=colors.HexColor('#f57f17')
    LGT=colors.HexColor('#f5f5f5'); WHT=colors.white
    ts_=ParagraphStyle('T',fontSize=18,textColor=WHT,alignment=TA_CENTER,fontName='Helvetica-Bold')
    ss_=ParagraphStyle('S',fontSize=9,textColor=colors.HexColor('#c5cae9'),alignment=TA_CENTER,fontName='Helvetica')
    hs_=ParagraphStyle('H',fontSize=12,textColor=PRI,fontName='Helvetica-Bold',spaceAfter=5)
    story=[]
    hdr=Table([[Paragraph(f"📊 {test_name}",ts_)],[Paragraph(now_uzt().strftime('%d.%m.%Y %H:%M'),ss_)]],colWidths=[18*cm])
    hdr.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PRI),('TOPPADDING',(0,0),(-1,-1),14),('BOTTOMPADDING',(0,0),(-1,-1),14),('LEFTPADDING',(0,0),(-1,-1),20)]))
    story+=[hdr,Spacer(1,.4*cm)]
    if results:
        sc_=[r['score'] for r in results]; tq=len(correct)
        s=Table([['👥 Ishtirokchi','📝 Savol',"📈 O'rtacha",'🏆 Yuqori','📉 Past'],
                 [str(len(results)),str(tq),f"{round(sum(sc_)/len(sc_),1)}/{tq}",f"{max(sc_)}/{tq}",f"{min(sc_)}/{tq}"]],colWidths=[3.4*cm]*5)
        s.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),SEC),('TEXTCOLOR',(0,0),(-1,0),WHT),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,0),8),('BACKGROUND',(0,1),(-1,1),ACC),('TEXTCOLOR',(0,1),(-1,1),PRI),('FONTNAME',(0,1),(-1,1),'Helvetica-Bold'),('FONTSIZE',(0,1),(-1,1),13),('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#9fa8da'))]))
        story+=[s,Spacer(1,.4*cm)]
    story.append(Paragraph("🏅 Natijalar",hs_))
    tq=len(correct); srt=sorted(results,key=lambda x:(-x['score'],x.get('date','')))
    td=[['#',"Ism Familiya","To'g'ri","Xato","Ball","%","Vaqt"]]
    for i,r in enumerate(srt,1):
        med={1:'🥇',2:'🥈',3:'🥉'}.get(i,str(i))
        pct=round(r['score']/tq*100,1) if tq else 0
        td.append([med,r.get('fullname','?')[:24],str(r['score']),str(tq-r['score']),f"{r['score']}/{tq}",f"{pct}%",fmt(r.get('date',''))[:16]])
    rt=Table(td,colWidths=[1*cm,5.5*cm,1.8*cm,1.8*cm,1.8*cm,1.8*cm,2.3*cm])
    rts=[('BACKGROUND',(0,0),(-1,0),PRI),('TEXTCOLOR',(0,0),(-1,0),WHT),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,0),8),('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('FONTSIZE',(0,1),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#c5cae9'))]
    for i in range(1,len(td)):
        rts.append(('BACKGROUND',(0,i),(-1,i),WHT if i%2==0 else LGT))
        try:
            p=srt[i-1]['score']/tq*100 if tq else 0
            c=GRN if p>=80 else(GLD if p>=50 else RED)
            rts+=[('TEXTCOLOR',(4,i),(5,i),c),('FONTNAME',(4,i),(5,i),'Helvetica-Bold')]
        except: pass
    rt.setStyle(TableStyle(rts)); story+=[rt,Spacer(1,.4*cm)]
    story.append(Paragraph("✅ To'g'ri javoblar",hs_))
    ait=sorted(correct.items(),key=lambda x:int(x[0])); rpr=10; rows=[]
    for i in range(0,len(ait),rpr):
        chunk=ait[i:i+rpr]; hr=[f"#{n}" for n,_ in chunk]; ar=[a.upper() for _,a in chunk]
        while len(hr)<rpr: hr.append(''); ar.append('')
        rows+=[hr,ar]
    if rows:
        at=Table(rows,colWidths=[1.7*cm]*rpr); ats=[]
        for i in range(0,len(rows),2):
            ats+=[('BACKGROUND',(0,i),(-1,i),SEC),('TEXTCOLOR',(0,i),(-1,i),WHT),('FONTNAME',(0,i),(-1,i),'Helvetica-Bold'),('FONTSIZE',(0,i),(-1,i),7),('BACKGROUND',(0,i+1),(-1,i+1),ACC),('TEXTCOLOR',(0,i+1),(-1,i+1),PRI),('FONTNAME',(0,i+1),(-1,i+1),'Helvetica-Bold'),('FONTSIZE',(0,i+1),(-1,i+1),10)]
        ats+=[('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#9fa8da'))]
        at.setStyle(TableStyle(ats)); story.append(at)
    story.append(Spacer(1,.4*cm))
    ft=Table([[f"© {now_uzt().year} | {CHANNEL_USER} | {now_uzt().strftime('%d.%m.%Y %H:%M')}"]],colWidths=[18*cm])
    ft.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PRI),('TEXTCOLOR',(0,0),(-1,-1),colors.HexColor('#c5cae9')),('FONTNAME',(0,0),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),8),('ALIGN',(0,0),(-1,-1),'CENTER'),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story.append(ft); doc.build(story); return buf.getvalue()

# ── ASOSIY HANDLER ─────────────────────────────────────
async def on_text(update, ctx):
    uid = update.effective_user.id
    text = update.message.text
    st = gs(uid); state = st.get("s", "")

    if text == "❌ Bekor qilish":
        cs(uid); d = load()
        await update.message.reply_text("❌ Bekor qilindi.", reply_markup=main_kb(uid, d)); return

    if state == "add_name":  await h_add_name(update, ctx); return
    if state == "add_id":    await h_add_id(update, ctx);   return
    if state == "add_ans":   await h_add_ans(update, ctx);  return
    if state == "sub_fn":    await h_sub_fn(update, ctx);   return
    if state == "sub_tid":   await h_sub_tid(update, ctx);  return
    if state == "sub_ans":   await h_sub_ans(update, ctx);  return

    if text == "📝 Testga javob berish": await start_sub(update, ctx)
    elif text == "➕ Test qo'shish":     await start_add(update, ctx)
    elif text == "📋 Mening testlarim":  await show_my_tests(update, ctx)
    elif text == "🔍 Natijalarim":       await show_results(update, ctx)
    elif text == "ℹ️ Yordam":            await show_help(update, ctx)
    else:
        if not await need_sub(update, ctx.bot): return
        d = load()
        await update.message.reply_text("Tugmalardan foydalaning 👇", reply_markup=main_kb(uid, d))

# ── MAIN ───────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CallbackQueryHandler(cb_check_sub,  pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(cb_my_tests,   pattern="^my_tests$"))
    app.add_handler(CallbackQueryHandler(cb_test_info,  pattern=r"^ti\|"))
    app.add_handler(CallbackQueryHandler(cb_action,     pattern=r"^(end|pdf|txt|del)\|"))
    app.add_handler(CallbackQueryHandler(cb_delok,      pattern=r"^delok\|"))
    app.add_handler(CallbackQueryHandler(cb_my_result,  pattern=r"^myres\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    print("🤖 Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

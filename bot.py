import os
import json
import re
import asyncio
from datetime import datetime, timezone, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMember, ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER
import io

# ===================== CONFIG =====================
BOT_TOKEN = "8950300608:AAGKzpg2uIyKlijdgO7JhdMZLpo2nYIuHzo"
CHANNEL_ID   = -1002847480970   # Kanal numeric ID (ishonchliroq)
CHANNEL_USER = "@huquqologiyauz"
CHANNEL_LINK = "https://t.me/huquqologiyauz"
# Ma'lumotlar fayli — Railway Volume /data papkasida, yo'q bo'lsa joriy papkada
DATA_DIR = "/data" if os.path.exists("/data") else "."
DATA_FILE = os.path.join(DATA_DIR, "data.json")

# O'zbekiston vaqt zonasi: UTC+5
UZT = timezone(timedelta(hours=5))

def now_uzt() -> datetime:
    return datetime.now(UZT)

def fmt_uzt(iso_str: str) -> str:
    """ISO string ni O'zbekiston vaqtida DD.MM.YYYY HH:MM:SS formatida qaytaradi"""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UZT)
        else:
            dt = dt.astimezone(UZT)
        return dt.strftime('%d.%m.%Y %H:%M:%S')
    except:
        return iso_str[:19]

# ===================== DATA =====================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tests": {}, "results": {}}

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

# ===================== KANAL TEKSHIRUVI =====================
async def is_subscribed(user_id: int, bot) -> bool:
    """
    Foydalanuvchi kanalga a'zo bo'lganini tekshiradi.
    Bot kanalda admin bo'lishi SHART.
    """
    for chat_id in [CHANNEL_ID, CHANNEL_USER]:
        try:
            m = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if m.status in ("member", "administrator", "creator"):
                return True
        except Exception as e:
            print(f"[kanal tekshiruv] {chat_id}: {e}")
            continue
    return False

def sub_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Kanalga a'zo bo'lish", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ A'zo bo'ldim, tekshir", callback_data="check_sub")]
    ])

async def require_sub(update: Update, bot) -> bool:
    """True = o'tdi, False = to'xtatildi"""
    uid = update.effective_user.id
    ok = await is_subscribed(uid, bot)
    if not ok:
        txt = (
            "⚠️ Botdan foydalanish uchun avval kanalimizga a'zo bo'ling!\n\n"
            f"📢 {CHANNEL_LINK}\n\n"
            "A'zo bo'lgach ✅ tugmasini bosing."
        )
        if update.message:
            await update.message.reply_text(txt, reply_markup=sub_kb())
        elif update.callback_query:
            await update.callback_query.message.reply_text(txt, reply_markup=sub_kb())
    return ok

# ===================== JAVOB PARSE =====================
def parse_answers(text: str):
    text = text.strip().lower().replace(" ", "")
    # 1ab = xato: har raqamdan keyin faqat 1 harf bo'lishi kerak
    bad = re.findall(r'\d+[a-e]{2,}', text)
    if bad:
        return None, f"❌ Xato: `{'  '.join(bad)}` — har savolga faqat 1 ta harf (a/b/c/d/e)"
    pairs = re.findall(r'(\d+)([a-e])', text)
    if not pairs:
        return None, "❌ Format noto'g'ri. Misol: `1a2b3c4d5e`"
    answers, seen = {}, {}
    for ns, letter in pairs:
        n = int(ns)
        if n in seen:
            return None, f"❌ {n}-savol uchun bir nechta javob! Har savolga 1 ta harf."
        answers[n] = letter
        seen[n] = True
    return answers, None

def calc(correct: dict, user: dict):
    total = len(correct)
    right, wrong, missing = 0, [], []
    for k, v in correct.items():
        k = int(k)
        if k in user:
            if user[k] == v: right += 1
            else: wrong.append((k, user[k], v))
        else:
            missing.append(k)
    return {"total": total, "right": right, "wrong": wrong,
            "missing": missing,
            "percent": round(right/total*100, 1) if total else 0}

# ===================== PDF =====================
def make_pdf(test_name, results, correct):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
          rightMargin=1.5*cm, leftMargin=1.5*cm,
          topMargin=2*cm, bottomMargin=1.5*cm)

    PRI = colors.HexColor('#1a237e')
    SEC = colors.HexColor('#283593')
    ACC = colors.HexColor('#e8eaf6')
    GRN = colors.HexColor('#2e7d32')
    RED = colors.HexColor('#c62828')
    GLD = colors.HexColor('#f57f17')
    LGT = colors.HexColor('#f5f5f5')
    WHT = colors.white

    ts = ParagraphStyle('T', fontSize=18, textColor=WHT,
                        alignment=TA_CENTER, fontName='Helvetica-Bold')
    ss = ParagraphStyle('S', fontSize=9,
                        textColor=colors.HexColor('#c5cae9'),
                        alignment=TA_CENTER, fontName='Helvetica')
    hs = ParagraphStyle('H', fontSize=12, textColor=PRI,
                        fontName='Helvetica-Bold', spaceAfter=5)
    story = []

    # Sarlavha
    hdr = Table([[Paragraph(f"📊 {test_name}", ts)],
                 [Paragraph(now_uzt().strftime('%d.%m.%Y %H:%M:%S'), ss)]],
                colWidths=[18*cm])
    hdr.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),PRI),
        ('TOPPADDING',(0,0),(-1,-1),14),
        ('BOTTOMPADDING',(0,0),(-1,-1),14),
        ('LEFTPADDING',(0,0),(-1,-1),20),
    ]))
    story += [hdr, Spacer(1, .4*cm)]

    # Umumiy stat
    if results:
        scores = [r['score'] for r in results]
        tq = len(correct)
        s = Table([
            ['👥 Ishtirokchi','📝 Savol','📈 O\'rtacha','🏆 Yuqori','📉 Past'],
            [str(len(results)), str(tq),
             f"{round(sum(scores)/len(scores),1)}/{tq}",
             f"{max(scores)}/{tq}", f"{min(scores)}/{tq}"]
        ], colWidths=[3.4*cm]*5)
        s.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),SEC),('TEXTCOLOR',(0,0),(-1,0),WHT),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,0),8),
            ('BACKGROUND',(0,1),(-1,1),ACC),('TEXTCOLOR',(0,1),(-1,1),PRI),
            ('FONTNAME',(0,1),(-1,1),'Helvetica-Bold'),('FONTSIZE',(0,1),(-1,1),13),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9),
            ('GRID',(0,0),(-1,-1),.5,colors.HexColor('#9fa8da')),
        ]))
        story += [s, Spacer(1,.4*cm)]

    # Natijalar
    story.append(Paragraph("🏅 Ishtirokchilar natijalari", hs))
    tq = len(correct)
    srt = sorted(results, key=lambda x: (-x['score'], x.get('date','')))
    td = [['#','Ism Familiya','To\'g\'ri','Xato','Ball','%','Vaqt']]
    for i, r in enumerate(srt, 1):
        med = {1:'🥇',2:'🥈',3:'🥉'}.get(i, str(i))
        pct = round(r['score']/tq*100,1) if tq else 0
        try:    vt = fmt_uzt(r['date'])
        except: vt = ''
        td.append([med, r.get('fullname','?')[:24], str(r['score']),
                   str(tq-r['score']), f"{r['score']}/{tq}", f"{pct}%", vt])
    rt = Table(td, colWidths=[1*cm,5.5*cm,1.8*cm,1.8*cm,1.8*cm,1.8*cm,2.3*cm])
    rts = [
        ('BACKGROUND',(0,0),(-1,0),PRI),('TEXTCOLOR',(0,0),(-1,0),WHT),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,0),8),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('FONTSIZE',(0,1),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),
        ('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('GRID',(0,0),(-1,-1),.3,colors.HexColor('#c5cae9')),
    ]
    for i in range(1, len(td)):
        rts.append(('BACKGROUND',(0,i),(-1,i), WHT if i%2==0 else LGT))
        try:
            p = srt[i-1]['score']/tq*100 if tq else 0
            c = GRN if p>=80 else (GLD if p>=50 else RED)
            rts += [('TEXTCOLOR',(4,i),(5,i),c),('FONTNAME',(4,i),(5,i),'Helvetica-Bold')]
        except: pass
    rt.setStyle(TableStyle(rts))
    story += [rt, Spacer(1,.4*cm)]

    # To'g'ri javoblar
    story.append(Paragraph("✅ To'g'ri javoblar", hs))
    ait = sorted(correct.items(), key=lambda x: int(x[0]))
    rpr, rows = 10, []
    for i in range(0, len(ait), rpr):
        chunk = ait[i:i+rpr]
        hr = [f"#{n}" for n,_ in chunk]
        ar = [a.upper() for _,a in chunk]
        while len(hr)<rpr: hr.append(''); ar.append('')
        rows += [hr, ar]
    if rows:
        at = Table(rows, colWidths=[1.7*cm]*rpr)
        ats = []
        for i in range(0,len(rows),2):
            ats += [
                ('BACKGROUND',(0,i),(-1,i),SEC),('TEXTCOLOR',(0,i),(-1,i),WHT),
                ('FONTNAME',(0,i),(-1,i),'Helvetica-Bold'),('FONTSIZE',(0,i),(-1,i),7),
                ('BACKGROUND',(0,i+1),(-1,i+1),ACC),('TEXTCOLOR',(0,i+1),(-1,i+1),PRI),
                ('FONTNAME',(0,i+1),(-1,i+1),'Helvetica-Bold'),('FONTSIZE',(0,i+1),(-1,i+1),10),
            ]
        ats += [('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
                ('GRID',(0,0),(-1,-1),.3,colors.HexColor('#9fa8da'))]
        at.setStyle(TableStyle(ats))
        story.append(at)

    story += [Spacer(1,.4*cm)]
    ft = Table([[f"© {now_uzt().year} | {CHANNEL_USER} | {now_uzt().strftime('%d.%m.%Y %H:%M:%S')}"]],
               colWidths=[18*cm])
    ft.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),PRI),('TEXTCOLOR',(0,0),(-1,-1),colors.HexColor('#c5cae9')),
        ('FONTNAME',(0,0),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),8),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
    ]))
    story.append(ft)
    doc.build(story)
    return buf.getvalue()

# ===================== KLAVIATURALAR =====================
def main_kb(uid, data):
    has_tests = any(t.get("owner_id")==uid for t in data["tests"].values())
    # Foydalanuvchi qatnashgan test bormi
    has_results = any(
        any(r["user_id"] == uid for r in data["results"].get(tid, []))
        for tid in data["tests"]
    )
    rows = [
        [KeyboardButton("📝 Testga javob berish")],
        [KeyboardButton("➕ Test qo'shish")],
    ]
    if has_tests:
        rows.append([KeyboardButton("📋 Mening testlarim")])
    if has_results:
        rows.append([KeyboardButton("🔍 Natijalarim va xatolarim")])
    rows.append([KeyboardButton("ℹ️ Yordam")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def test_mgmt_kb(tid, active):
    rows = []
    if active:
        rows.append([InlineKeyboardButton("🏁 Yakunlash", callback_data=f"end:{tid}")])
    rows += [
        [InlineKeyboardButton("📊 PDF statistika", callback_data=f"pdf:{tid}"),
         InlineKeyboardButton("📝 Matn", callback_data=f"txt:{tid}")],
        [InlineKeyboardButton("🗑 O'chirish", callback_data=f"del:{tid}")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="my_tests")],
    ]
    return InlineKeyboardMarkup(rows)

# ===================== STATE TIZIMI =====================
# user_data[uid] = {"state": "...", "tmp": {...}}
STATES = {}

def get_state(uid):
    return STATES.get(uid, {})

def set_state(uid, state, **kwargs):
    STATES[uid] = {"state": state, **kwargs}

def clear_state(uid):
    STATES.pop(uid, None)

# ===================== HANDLERS =====================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    clear_state(uid)
    data = load_data()
    ok = await is_subscribed(uid, ctx.bot)
    if not ok:
        await update.message.reply_text(
            f"👋 Salom, {update.effective_user.first_name}!\n\n"
            "⚠️ Botdan foydalanish uchun kanalimizga a'zo bo'ling!\n\n"
            f"📢 {CHANNEL_LINK}\n\nA'zo bo'lgach ✅ tugmasini bosing.",
            reply_markup=sub_kb()
        )
        return
    await update.message.reply_text(
        f"👋 Salom, {update.effective_user.first_name}!\n\n"
        "🤖 *Test Bot*ga xush kelibsiz!\n"
        "Quyidagi tugmalardan foydalaning 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_kb(uid, data)
    )

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    clear_state(uid)
    data = load_data()
    await update.message.reply_text(
        "❌ Bekor qilindi.",
        reply_markup=main_kb(uid, data)
    )

async def cb_check_sub(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    ok = await is_subscribed(uid, ctx.bot)
    if not ok:
        await q.edit_message_text(
            f"❌ Siz hali kanalga a'zo bo'lmadingiz!\n\n"
            f"Iltimos: {CHANNEL_LINK}\n\nA'zo bo'lgach qayta tekshiring.",
            reply_markup=sub_kb()
        )
        return
    data = load_data()
    await q.edit_message_text("✅ Zo'r! Kanalga a'zo bo'lgansiz.")
    await ctx.bot.send_message(
        chat_id=q.message.chat_id,
        text="Quyidagi tugmalardan foydalaning 👇",
        reply_markup=main_kb(uid, data)
    )

# ===================== TEST QO'SHISH =====================
async def start_add_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await require_sub(update, ctx.bot): return
    set_state(uid, "add_name")
    await update.message.reply_text(
        "➕ *Yangi test qo'shish*\n\n"
        "1️⃣ Test nomini yuboring:\n"
        "_(Misol: Jinoyat huquqi — 1-variant)_\n\n"
        "Bekor qilish: /cancel",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )

async def handle_add_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("❌ Nom juda qisqa. Qayta yuboring:")
        return
    set_state(uid, "add_id", name=name)
    await update.message.reply_text(
        f"✅ Nom: *{name}*\n\n"
        "2️⃣ Test uchun qisqa ID kiriting:\n"
        "_(faqat lotin harflari, raqamlar, _ )_\n"
        "_(Misol: huquq1, variant2)_",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_add_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = get_state(uid)
    tid = update.message.text.strip().lower().replace(" ", "_")
    if not re.match(r'^[a-z0-9_]+$', tid):
        await update.message.reply_text("❌ Faqat lotin harflari, raqamlar va _ kiriting:")
        return
    data = load_data()
    if tid in data["tests"]:
        await update.message.reply_text(f"⚠️ `{tid}` ID allaqachon bor. Boshqa ID kiriting:", parse_mode=ParseMode.MARKDOWN)
        return
    set_state(uid, "add_answers", name=st["name"], tid=tid)
    await update.message.reply_text(
        f"✅ ID: `{tid}`\n\n"
        "3️⃣ To'g'ri javoblarni yuboring:\n"
        "📌 Format: `1a2b3c4d5e...`\n"
        "_(Har savolga faqat 1 ta harf: a b c d e)_\n\n"
        "Misol: `1a2b3d4c5e6b7a8d`",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_add_answers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = get_state(uid)
    answers, err = parse_answers(update.message.text)
    if err:
        await update.message.reply_text(err + "\n\nQayta yuboring:", parse_mode=ParseMode.MARKDOWN)
        return
    data = load_data()
    tid = st["tid"]
    data["tests"][tid] = {
        "name": st["name"],
        "answers": {str(k): v for k, v in answers.items()},
        "created_at": now_uzt().isoformat(),
        "active": True,
        "owner_id": uid
    }
    data["results"][tid] = []
    save_data(data)
    clear_state(uid)
    await update.message.reply_text(
        f"✅ *Test qo'shildi!*\n\n"
        f"📋 Nom: *{st['name']}*\n"
        f"🔑 ID: `{tid}`\n"
        f"📊 Savollar: *{len(answers)}* ta\n"
        f"🟢 Holat: Faol\n\n"
        f"Kanalda e'lon qilishda test IDsini: `{tid}` ko'rsating.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_kb(uid, data)
    )

# ===================== JAVOB BERISH =====================
async def start_submit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await require_sub(update, ctx.bot): return
    data = load_data()
    active = {k: v for k, v in data["tests"].items() if v.get("active")}
    if not active:
        await update.message.reply_text(
            "📭 Hozirda faol test yo'q.",
            reply_markup=main_kb(uid, data)
        )
        return
    set_state(uid, "sub_fullname")
    await update.message.reply_text(
        "✍️ *Javob berish*\n\n"
        "1️⃣ Ism va familiyangizni yuboring:\n"
        "_(Misol: Usmonov Ibrohim)_\n\n"
        "Bekor qilish: /cancel",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )

async def handle_sub_fullname(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    fn = update.message.text.strip()
    if len(fn) < 3:
        await update.message.reply_text("❌ Ism familiya juda qisqa. Qayta yuboring:")
        return
    data = load_data()
    active = {k: v for k, v in data["tests"].items() if v.get("active")}
    tlist = "\n".join([f"🔹 *{t['name']}* — `{tid}`" for tid, t in active.items()])
    set_state(uid, "sub_test_id", fullname=fn)
    await update.message.reply_text(
        f"👤 Siz: *{fn}*\n\n"
        f"2️⃣ Test IDsini yuboring:\n\n"
        f"*Faol testlar:*\n{tlist}",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_sub_test_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = get_state(uid)
    data = load_data()
    tid = update.message.text.strip().lower()
    if tid not in data["tests"]:
        await update.message.reply_text(f"❌ `{tid}` ID topilmadi. To'g'ri ID kiriting:", parse_mode=ParseMode.MARKDOWN)
        return
    if not data["tests"][tid].get("active"):
        await update.message.reply_text(f"⚠️ `{tid}` testi yakunlangan. Boshqa ID kiriting:", parse_mode=ParseMode.MARKDOWN)
        return

    # BITTA MARTA YUBORISH CHEKLOVI: user_id bo'yicha — ism o'zgartirsa ham aniqlanadi
    existing = next((r for r in data["results"].get(tid, []) if r["user_id"] == uid), None)
    if existing:
        clear_state(uid)
        test = data["tests"][tid]
        tq = len(test["answers"])
        pct = round(existing['score']/tq*100, 1) if tq else 0
        try: vt = fmt_uzt(existing['date'])
        except: vt = existing.get('date','')
        await update.message.reply_text(
            f"⛔️ *Siz bu testga allaqachon javob yuborgansiz!*\n\n"
            f"📋 Test: *{test['name']}*\n"
            f"👤 {existing.get('fullname','')}\n"
            f"✅ Natijangiz: *{existing['score']}/{tq}* ({pct}%)\n"
            f"🕐 Yuborilgan: {vt}\n\n"
            f"⚠️ Har bir test uchun faqat *1 marta* javob yuborish mumkin. "
            f"Qayta urinish (ism o'zgartirib bo'lsa ham) qabul qilinmaydi.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_kb(uid, data)
        )
        return

    test = data["tests"][tid]
    set_state(uid, "sub_answers", fullname=st["fullname"], tid=tid)
    await update.message.reply_text(
        f"✅ Test: *{test['name']}*\n"
        f"📊 Savollar: *{len(test['answers'])}* ta\n\n"
        "3️⃣ Javoblaringizni yuboring:\n"
        "📌 Format: `1a2b3c4d5e...`\n\n"
        "⚠️ *Diqqat:* Faqat 1 marta javob yuborishingiz mumkin!",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_sub_answers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = get_state(uid)
    data = load_data()
    tid = st["tid"]
    fn = st["fullname"]
    test = data["tests"].get(tid)
    if not test:
        await update.message.reply_text("❌ Test topilmadi. /start bosing.")
        clear_state(uid)
        return

    # Qayta tekshiruv: javob yozish jarayonida boshqa joydan/parallel yuborgan bo'lishi mumkin
    existing = next((r for r in data["results"].get(tid, []) if r["user_id"] == uid), None)
    if existing:
        clear_state(uid)
        await update.message.reply_text(
            "⛔️ Siz bu testga allaqachon javob yuborgansiz. Qayta yuborish mumkin emas.",
            reply_markup=main_kb(uid, data)
        )
        return

    answers, err = parse_answers(update.message.text)
    if err:
        await update.message.reply_text(err + "\n\nQayta yuboring:", parse_mode=ParseMode.MARKDOWN)
        return
    correct = {int(k): v for k, v in test["answers"].items()}
    res = calc(correct, answers)
    now = now_uzt().isoformat()
    entry = {
        "user_id": uid,
        "username": update.effective_user.username or "",
        "fullname": fn,
        "answers": {str(k): v for k, v in answers.items()},
        "score": res["right"],
        "date": now
    }
    # Faqat birinchi marta qo'shiladi — qayta yozilmaydi
    lst = data["results"].get(tid, [])
    lst.append(entry)
    data["results"][tid] = lst
    save_data(data)
    clear_state(uid)

    pct = res["percent"]
    emoji = "🏆" if pct>=80 else ("👍" if pct>=60 else ("📚" if pct>=40 else "💪"))
    grade = "A'lo" if pct>=80 else ("Yaxshi" if pct>=60 else ("Qoniqarli" if pct>=40 else "Qayta o'qing"))
    await update.message.reply_text(
        f"✅ *Javobingiz qabul qilindi!*\n\n"
        f"👤 {fn}\n"
        f"📋 Test: *{test['name']}*\n"
        f"📊 Natija: *{res['right']}/{res['total']}* to'g'ri\n"
        f"📈 Foiz: *{pct}%*\n"
        f"{emoji} Baho: *{grade}*\n\n"
        "🏁 Test yakunlangach xatolaringizni ko'rishingiz mumkin!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_kb(uid, data)
    )
    # Egaga bildiruv — har bir savol tekshirilgan holda
    owner = test.get("owner_id")
    if owner:
        try:
            # Har bir javobni to'g'ri/xato belgilab ko'rsatish
            detail_lines = []
            for num in sorted(correct.keys()):
                c_ans = correct[num]
                u_ans = answers.get(num)
                if u_ans is None:
                    detail_lines.append(f"⚪️ {num}: — (javob berilmadi)")
                elif u_ans == c_ans:
                    detail_lines.append(f"✅ {num}: {u_ans.upper()}")
                else:
                    detail_lines.append(f"❌ {num}: {u_ans.upper()} (to'g'ri: {c_ans.upper()})")
            # Uzun bo'lsa ixchamlashtir
            if len(detail_lines) > 30:
                # Faqat xatolarni ko'rsat
                wrong_lines = [l for l in detail_lines if l.startswith("❌") or l.startswith("⚪️")]
                detail_txt = (
                    f"✅ To'g'rilar: {res['right']} ta\n"
                    f"❌ Xatolar ({len(wrong_lines)} ta):\n" +
                    "\n".join(wrong_lines)
                )
            else:
                detail_txt = "\n".join(detail_lines)

            await ctx.bot.send_message(
                chat_id=owner,
                text=f"🔔 *Yangi javob keldi!*\n\n"
                     f"👤 *{fn}*\n"
                     f"📋 *{test['name']}* (`{tid}`)\n"
                     f"📊 Natija: *{res['right']}/{res['total']}* ({pct}%)\n"
                     f"🕐 {fmt_uzt(now)}\n\n"
                     f"*Javoblar tahlili:*\n"
                     f"{detail_txt}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            print(f"Egaga bildiruv xatosi: {e}")

# ===================== MENING TESTLARIM =====================
async def show_my_tests(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await require_sub(update, ctx.bot): return
    data = load_data()
    my = {k: v for k, v in data["tests"].items() if v.get("owner_id") == uid}
    if not my:
        await update.message.reply_text(
            "📭 Sizda hech qanday test yo'q.\n\n➕ Test qo'shish tugmasini bosing!",
            reply_markup=main_kb(uid, data)
        )
        return

    # Eski "Mening testlarim" xabarini o'chirish
    old_msg_id = ctx.user_data.get("my_tests_msg_id")
    if old_msg_id:
        try:
            await ctx.bot.delete_message(chat_id=update.message.chat_id, message_id=old_msg_id)
        except Exception:
            pass
        ctx.user_data.pop("my_tests_msg_id", None)

    btns = _build_my_tests_buttons(my, data)
    sent = await update.message.reply_text(
        "📋 *Mening testlarim:*\n\nBoshqarish uchun tanlang 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(btns)
    )
    ctx.user_data["my_tests_msg_id"] = sent.message_id

def _build_my_tests_buttons(my, data):
    btns = []
    for tid, t in my.items():
        st = "🟢" if t.get("active") else "🔴"
        cnt = len(data["results"].get(tid, []))
        btns.append([InlineKeyboardButton(f"{st} {t['name']} ({cnt} javob)", callback_data=f"ti:{tid}")])
    return btns

async def cb_my_tests(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = load_data()
    my = {k: v for k, v in data["tests"].items() if v.get("owner_id") == uid}
    if not my:
        await q.edit_message_text("📭 Sizda test yo'q.")
        return
    btns = _build_my_tests_buttons(my, data)
    await q.edit_message_text(
        "📋 *Mening testlarim:*\n\nBoshqarish uchun tanlang 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(btns)
    )

async def cb_test_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, tid = q.data.split(":", 1)
    data = load_data()
    test = data["tests"].get(tid)
    if not test:
        await q.edit_message_text("❌ Test topilmadi.")
        return
    if test.get("owner_id") != q.from_user.id:
        await q.edit_message_text("❌ Bu test sizniki emas.")
        return
    cnt = len(data["results"].get(tid, []))
    status = "🟢 Faol" if test.get("active") else "🔴 Yakunlangan"
    await q.edit_message_text(
        f"📋 *{test['name']}*\n\n"
        f"🔑 ID: `{tid}`\n"
        f"📊 Savollar: *{len(test['answers'])}* ta\n"
        f"👥 Javoblar: *{cnt}* ta\n"
        f"📍 Holat: {status}\n"
        f"📅 Yaratilgan: {test['created_at'][:10]}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=test_mgmt_kb(tid, test.get("active", False))
    )

async def cb_test_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action, tid = q.data.split(":", 1)
    data = load_data()
    test = data["tests"].get(tid)
    if not test:
        await q.edit_message_text("❌ Test topilmadi.")
        return
    if test.get("owner_id") != q.from_user.id:
        await q.edit_message_text("❌ Ruxsat yo'q.")
        return
    results = data["results"].get(tid, [])
    correct = {int(k): v for k, v in test["answers"].items()}

    if action == "end":
        data["tests"][tid]["active"] = False
        save_data(data)
        # Yakunlangandan keyin darhol boshqaruv panelini yangilab ko'rsat
        await q.edit_message_text(
            f"✅ *{test['name']}* yakunlandi!\n\n"
            f"👥 Jami {len(results)} ta ishtirokchi\n\n"
            f"🔑 ID: `{tid}`\n"
            f"📍 Holat: 🔴 Yakunlangan",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=test_mgmt_kb(tid, active=False)
        )

    elif action == "pdf":
        if not results:
            await q.edit_message_text("📭 Hech qanday natija yo'q.")
            return
        await q.edit_message_text("⏳ PDF tayyorlanmoqda...")
        pdf = make_pdf(test["name"], results, correct)
        fname = f"stat_{tid}_{now_uzt().strftime('%Y%m%d_%H%M')}.pdf"
        await ctx.bot.send_document(
            chat_id=q.message.chat_id,
            document=io.BytesIO(pdf), filename=fname,
            caption=f"📊 *{test['name']}*\n👥 {len(results)} ta ishtirokchi",
            parse_mode=ParseMode.MARKDOWN
        )
        await q.delete_message()

    elif action == "txt":
        if not results:
            await q.edit_message_text("📭 Hech qanday natija yo'q.")
            return
        tq = len(correct)
        srt = sorted(results, key=lambda x: (-x['score'], x.get('date','')))
        scores = [r['score'] for r in results]
        text = (
            f"📊 *{test['name']}*\n"
            f"📅 {now_uzt().strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"─────────────────────\n"
            f"👥 Ishtirokchi: *{len(results)}*\n"
            f"📈 O'rtacha: *{round(sum(scores)/len(scores),1)}/{tq}*\n"
            f"🏆 Eng yuqori: *{max(scores)}/{tq}*\n"
            f"📉 Eng past: *{min(scores)}/{tq}*\n"
            f"─────────────────────\n\n"
        )
        for i, r in enumerate(srt, 1):
            med = {1:'🥇',2:'🥈',3:'🥉'}.get(i, f"{i}.")
            pct = round(r['score']/tq*100,1) if tq else 0
            try:    vt = fmt_uzt(r['date'])
            except: vt = ''
            text += f"{med} *{r.get('fullname','?')}* — {r['score']}/{tq} ({pct}%) | {vt}\n"
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)

    elif action == "del":
        await q.edit_message_text(
            f"⚠️ *{test['name']}* testini o'chirishni tasdiqlaysizmi?\n"
            "Bu amal qaytarilmaydi!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Ha, o'chir", callback_data=f"delok:{tid}")],
                [InlineKeyboardButton("❌ Yo'q", callback_data=f"ti:{tid}")]
            ])
        )

async def cb_del_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, tid = q.data.split(":", 1)
    data = load_data()
    test = data["tests"].get(tid)
    if not test or test.get("owner_id") != q.from_user.id:
        await q.edit_message_text("❌ Ruxsat yo'q.")
        return
    name = test["name"]
    del data["tests"][tid]
    data["results"].pop(tid, None)
    save_data(data)
    await q.edit_message_text(f"✅ *{name}* o'chirildi.", parse_mode=ParseMode.MARKDOWN)

# ===================== XATOLARNI KO'RISH =====================
async def show_errors_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await require_sub(update, ctx.bot): return
    data = load_data()
    # Foydalanuvchi qatnashgan BARCHA testlar (faol yoki yakunlangan)
    participated = [
        (tid, t) for tid, t in data["tests"].items()
        if any(r["user_id"] == uid for r in data["results"].get(tid, []))
    ]
    if not participated:
        await update.message.reply_text(
            "📭 Siz hali hech qanday testga javob bermadingiz.",
            reply_markup=main_kb(uid, data)
        )
        return
    btns = []
    for tid, t in participated:
        status = "🟢" if t.get("active") else "🔴"
        label = f"{status} {t['name']}"
        if t.get("active"):
            label += " (faol — natija yakunlangach)"
        btns.append([InlineKeyboardButton(label, callback_data=f"myerr:{tid}")])
    await update.message.reply_text(
        "🔍 Qaysi testdagi natijangizni ko'rmoqchisiz?\n\n"
        "🟢 Faol testlarda xatolar test yakunlangach ko'rinadi\n"
        "🔴 Yakunlangan testlarda xatolarni ko'rishingiz mumkin",
        reply_markup=InlineKeyboardMarkup(btns)
    )

async def cb_my_errors(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, tid = q.data.split(":", 1)
    data = load_data()
    test = data["tests"].get(tid)
    if not test:
        await q.edit_message_text("❌ Test topilmadi.")
        return
    results = data["results"].get(tid, [])
    entry = next((r for r in results if r["user_id"] == q.from_user.id), None)
    if not entry:
        await q.edit_message_text("❌ Siz bu testda qatnashmadingiz.")
        return
    # Faol test bo'lsa — faqat natijani ko'rsat, xatolarni emas
    if test.get("active"):
        pct = round(entry['score'] / len(test['answers']) * 100, 1) if test['answers'] else 0
        try: vt = fmt_uzt(entry['date'])
        except: vt = entry.get('date','')
        await q.edit_message_text(
            f"📊 *{test['name']}*\n\n"
            f"👤 {entry.get('fullname','')}\n"
            f"✅ Natija: *{entry['score']}/{len(test['answers'])}* ({pct}%)\n"
            f"🕐 Yuborilgan: {vt}\n\n"
            f"⏳ Test hali faol — xatolar test yakunlangach ko'rinadi.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    # Yakunlangan test — xatolarni to'liq ko'rsat
    correct = {int(k): v for k, v in test["answers"].items()}
    user_ans = {int(k): v for k, v in entry["answers"].items()}
    res = calc(correct, user_ans)
    try: vt = fmt_uzt(entry['date'])
    except: vt = entry.get('date','')

    # Har bir savol bo'yicha tahlil
    detail_lines = []
    for num in sorted(correct.keys()):
        c_ans = correct[num]
        u_ans = user_ans.get(num)
        if u_ans is None:
            detail_lines.append(f"⚪️ {num}: javob berilmagan (to'g'ri: *{c_ans.upper()}*)")
        elif u_ans == c_ans:
            detail_lines.append(f"✅ {num}: *{u_ans.upper()}*")
        else:
            detail_lines.append(f"❌ {num}: *{u_ans.upper()}* → to'g'ri: *{c_ans.upper()}*")

    detail_txt = "\n".join(detail_lines)

    # Telegram 4096 belgi chegarasi — kerak bo'lsa qisqartir
    header = (
        f"📊 *{test['name']}* — Natijangiz\n\n"
        f"👤 {entry.get('fullname','')}\n"
        f"✅ To'g'ri: *{res['right']}/{res['total']}* ({res['percent']}%)\n"
        f"🕐 Yuborilgan: {vt}\n\n"
        f"*Batafsil tahlil:*\n"
    )
    full_msg = header + detail_txt
    if len(full_msg) > 4000:
        # Faqat xatolarni ko'rsat
        wrong_lines = [l for l in detail_lines if l.startswith("❌") or l.startswith("⚪️")]
        if wrong_lines:
            full_msg = header + "\n".join(wrong_lines) + f"\n\n_✅ To'g'ri javoblar: {res['right']} ta ko'rsatilmadi_"
        else:
            full_msg = header + "🎉 Barcha javoblar to'g'ri edi!"
    if not res["wrong"] and not res["missing"]:
        full_msg = header + "🎉 Barcha javoblar to'g'ri edi!"
    await q.edit_message_text(full_msg, parse_mode=ParseMode.MARKDOWN)

# ===================== YORDAM =====================
async def show_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_data()
    await update.message.reply_text(
        "ℹ️ *Yordam*\n\n"
        "📝 *Testga javob berish:*\n"
        "   Ism-familiya → Test ID → Javoblar\n\n"
        "➕ *Test qo'shish:*\n"
        "   Nom → ID → `1a2b3c...`\n\n"
        "📋 *Mening testlarim:*\n"
        "   Statistika, yakunlash, o'chirish\n\n"
        "📌 *Javob formati:*\n"
        "   `1a2b3c4d5e` (raqam + 1 harf)\n\n"
        "🔍 Xatolarni test yakunlangandan keyin ko'rishingiz mumkin.\n\n"
        f"📢 Kanal: {CHANNEL_LINK}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_kb(uid, data)
    )

# ===================== ASOSIY TEXT HANDLER =====================
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    st = get_state(uid)
    state = st.get("state", "")

    # Bekor qilish har qanday holatda
    if text == "❌ Bekor qilish":
        clear_state(uid)
        data = load_data()
        await update.message.reply_text("❌ Bekor qilindi.", reply_markup=main_kb(uid, data))
        return

    # Aktiv state bo'lsa unga yo'naltiramiz
    if state == "add_name":
        await handle_add_name(update, ctx); return
    if state == "add_id":
        await handle_add_id(update, ctx); return
    if state == "add_answers":
        await handle_add_answers(update, ctx); return
    if state == "sub_fullname":
        await handle_sub_fullname(update, ctx); return
    if state == "sub_test_id":
        await handle_sub_test_id(update, ctx); return
    if state == "sub_answers":
        await handle_sub_answers(update, ctx); return

    # Tugmalar
    if text == "📝 Testga javob berish":
        await start_submit(update, ctx)
    elif text == "➕ Test qo'shish":
        await start_add_test(update, ctx)
    elif text == "📋 Mening testlarim":
        await show_my_tests(update, ctx)
    elif text == "ℹ️ Yordam":
        await show_help(update, ctx)
    elif text in ("🔍 Xatolarimni ko'rish", "🔍 Natijalarim va xatolarim"):
        await show_errors_menu(update, ctx)
    else:
        if not await require_sub(update, ctx.bot): return
        data = load_data()
        await update.message.reply_text(
            "Tugmalardan foydalaning 👇",
            reply_markup=main_kb(uid, data)
        )

# ===================== MAIN =====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CallbackQueryHandler(cb_check_sub, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(cb_my_tests, pattern="^my_tests$"))
    app.add_handler(CallbackQueryHandler(cb_test_info, pattern="^ti:"))
    app.add_handler(CallbackQueryHandler(cb_test_action, pattern="^(end|pdf|txt|del):"))
    app.add_handler(CallbackQueryHandler(cb_del_confirm, pattern="^delok:"))
    app.add_handler(CallbackQueryHandler(cb_my_errors, pattern="^myerr:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    print("🤖 Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

import os
import json
import re
import asyncio
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMember, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
    ConversationHandler
)
from telegram.constants import ParseMode
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import io

# ===================== KONFIGURATSIYA =====================
BOT_TOKEN = "8950300608:AAGKzpg2uIyKlijdgO7JhdMZLpo2nYIuHzo"
CHANNEL_USERNAME = "@huquqologiyauz"
CHANNEL_LINK = "https://t.me/huquqologiyauz"
DATA_FILE = "data.json"

# ConversationHandler states
(
    ADD_TEST_NAME, ADD_TEST_ID, ADD_TEST_ANSWERS,
    SUBMIT_FULLNAME, SUBMIT_TEST_ID, SUBMIT_ANSWERS
) = range(6)

# ===================== MA'LUMOTLAR =====================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "tests": {},
        # test_id -> {name, answers, created_at, active, owner_id}
        "results": {}
        # test_id -> [{user_id, fullname, answers, score, date}]
    }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ===================== KANAL TEKSHIRISH =====================
async def check_subscription(user_id: int, bot) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"Kanal tekshirish xatosi: {e}")
        # Agar kanal topilmasa yoki bot admin emas bo'lsa, o'tkazib yuboramiz
        return True

def sub_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Kanalga a'zo bo'lish", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ A'zo bo'ldim, tekshir", callback_data="check_sub")]
    ])

# ===================== JAVOB PARSE =====================
def parse_answers(text: str):
    """1a2b3c shaklida parse, har savolga faqat 1 ta javob"""
    text = text.strip().lower().replace(" ", "")
    pairs = re.findall(r'(\d+)([a-e])', text)
    if not pairs:
        return None, "Format noto'g'ri"
    
    answers = {}
    for num_str, letter in pairs:
        num = int(num_str)
        if num in answers:
            return None, f"⚠️ {num}-savol uchun bir nechta javob kiritdingiz! Har savolga faqat 1 ta harf kiriting."
        answers[num] = letter
    return answers, None

def validate_answers_strict(text: str):
    """Har bir raqamdan keyin faqat 1 ta harf bo'lishini tekshirish"""
    text = text.strip().lower().replace(" ", "")
    # Agar raqamdan keyin 2 ta harf bo'lsa xato
    invalid = re.findall(r'\d+[a-e]{2,}', text)
    if invalid:
        return False, f"❌ Xato format: `{'  '.join(invalid)}` — har savolga faqat 1 ta harf (a/b/c/d/e)"
    return True, None

# ===================== NATIJA HISOBLASH =====================
def calculate_result(correct: dict, user: dict):
    total = len(correct)
    right = 0
    wrong = []
    missing = []
    for num, ans in correct.items():
        num = int(num)
        if num in user:
            if user[num] == ans:
                right += 1
            else:
                wrong.append((num, user[num], ans))
        else:
            missing.append(num)
    return {
        "total": total, "right": right,
        "wrong": wrong, "missing": missing,
        "percent": round(right / total * 100, 1) if total > 0 else 0
    }

# ===================== PDF GENERATSIYA =====================
def generate_pdf(test_name: str, results: list, correct_answers: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=1.5*cm)

    PRIMARY   = colors.HexColor('#1a237e')
    SECONDARY = colors.HexColor('#283593')
    ACCENT    = colors.HexColor('#e8eaf6')
    GREEN     = colors.HexColor('#2e7d32')
    RED       = colors.HexColor('#c62828')
    GOLD      = colors.HexColor('#f57f17')
    LIGHT     = colors.HexColor('#f5f5f5')
    WHITE     = colors.white

    title_s = ParagraphStyle('T', fontSize=18, textColor=WHITE,
        alignment=TA_CENTER, fontName='Helvetica-Bold')
    sub_s = ParagraphStyle('S', fontSize=9, textColor=colors.HexColor('#c5cae9'),
        alignment=TA_CENTER, fontName='Helvetica')
    hdr_s = ParagraphStyle('H', fontSize=12, textColor=PRIMARY,
        fontName='Helvetica-Bold', spaceAfter=5)

    story = []

    # SARLAVHA
    title_tbl = Table([
        [Paragraph(f"📊 {test_name}", title_s)],
        [Paragraph(f"Natijalar | {datetime.now().strftime('%d.%m.%Y %H:%M')}", sub_s)]
    ], colWidths=[18*cm])
    title_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), PRIMARY),
        ('TOPPADDING', (0,0), (-1,-1), 14),
        ('BOTTOMPADDING', (0,0), (-1,-1), 14),
        ('LEFTPADDING', (0,0), (-1,-1), 20),
    ]))
    story.append(title_tbl)
    story.append(Spacer(1, 0.4*cm))

    # UMUMIY STATISTIKA
    if results:
        scores = [r['score'] for r in results]
        total_q = len(correct_answers)
        avg = round(sum(scores)/len(scores), 1)
        stat = Table([
            ['👥 Ishtirokchi', '📝 Savol', '📈 O\'rtacha', '🏆 Yuqori', '📉 Past'],
            [str(len(results)), str(total_q),
             f"{avg}/{total_q}", f"{max(scores)}/{total_q}", f"{min(scores)}/{total_q}"]
        ], colWidths=[3.4*cm]*5)
        stat.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), SECONDARY),
            ('TEXTCOLOR', (0,0), (-1,0), WHITE),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,1), ACCENT),
            ('TEXTCOLOR', (0,1), (-1,1), PRIMARY),
            ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,1), (-1,1), 13),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 9),
            ('BOTTOMPADDING', (0,0), (-1,-1), 9),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#9fa8da')),
        ]))
        story.append(stat)
        story.append(Spacer(1, 0.4*cm))

    # NATIJALAR JADVALI — ball bo'yicha, teng bo'lsa vaqt bo'yicha
    story.append(Paragraph("🏅 Ishtirokchilar natijalari", hdr_s))

    sorted_r = sorted(results,
        key=lambda x: (-x['score'], x.get('date', '')))

    total_q = len(correct_answers)
    tbl_data = [['#', 'Ism Familiya', 'To\'g\'ri', 'Xato', 'Ball', '%', 'Vaqt']]
    for i, r in enumerate(sorted_r, 1):
        medal = {1:'🥇',2:'🥈',3:'🥉'}.get(i, str(i))
        wrong_c = total_q - r['score']
        pct = round(r['score']/total_q*100, 1) if total_q > 0 else 0
        # Vaqt formatlash
        try:
            dt = datetime.fromisoformat(r.get('date',''))
            vaqt = dt.strftime('%d.%m %H:%M')
        except:
            vaqt = r.get('date','')[:10]
        tbl_data.append([
            medal, r.get('fullname','Noma\'lum')[:24],
            str(r['score']), str(wrong_c),
            f"{r['score']}/{total_q}", f"{pct}%", vaqt
        ])

    res_tbl = Table(tbl_data, colWidths=[1*cm, 5.5*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm, 2.3*cm])
    ts = [
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 8),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#c5cae9')),
    ]
    for i in range(1, len(tbl_data)):
        bg = WHITE if i % 2 == 0 else LIGHT
        ts.append(('BACKGROUND', (0,i), (-1,i), bg))
        try:
            sc = sorted_r[i-1]['score']
            p = sc/total_q*100 if total_q > 0 else 0
            c = GREEN if p >= 80 else (GOLD if p >= 50 else RED)
            ts += [('TEXTCOLOR', (4,i), (5,i), c),
                   ('FONTNAME', (4,i), (5,i), 'Helvetica-Bold')]
        except: pass
    res_tbl.setStyle(TableStyle(ts))
    story.append(res_tbl)
    story.append(Spacer(1, 0.4*cm))

    # TO'G'RI JAVOBLAR
    story.append(Paragraph("✅ To'g'ri javoblar", hdr_s))
    ans_items = sorted(correct_answers.items(), key=lambda x: int(x[0]))
    rprow = 10
    rows = []
    for i in range(0, len(ans_items), rprow):
        chunk = ans_items[i:i+rprow]
        hr = [f"#{n}" for n,_ in chunk]
        ar = [a.upper() for _,a in chunk]
        while len(hr) < rprow: hr.append(''); ar.append('')
        rows.append(hr); rows.append(ar)

    if rows:
        at = Table(rows, colWidths=[1.7*cm]*rprow)
        ast_ = []
        for i in range(0, len(rows), 2):
            ast_ += [
                ('BACKGROUND',(0,i),(-1,i), SECONDARY),
                ('TEXTCOLOR',(0,i),(-1,i), WHITE),
                ('FONTNAME',(0,i),(-1,i),'Helvetica-Bold'),
                ('FONTSIZE',(0,i),(-1,i),7),
                ('BACKGROUND',(0,i+1),(-1,i+1), ACCENT),
                ('TEXTCOLOR',(0,i+1),(-1,i+1), PRIMARY),
                ('FONTNAME',(0,i+1),(-1,i+1),'Helvetica-Bold'),
                ('FONTSIZE',(0,i+1),(-1,i+1),10),
            ]
        ast_ += [
            ('ALIGN',(0,0),(-1,-1),'CENTER'),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('TOPPADDING',(0,0),(-1,-1),5),
            ('BOTTOMPADDING',(0,0),(-1,-1),5),
            ('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#9fa8da')),
        ]
        at.setStyle(TableStyle(ast_))
        story.append(at)

    # FOOTER
    story.append(Spacer(1, 0.4*cm))
    ft = Table([[f"© {datetime.now().year} | {CHANNEL_USERNAME} | {datetime.now().strftime('%d.%m.%Y %H:%M')}"]], colWidths=[18*cm])
    ft.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1), PRIMARY),
        ('TEXTCOLOR',(0,0),(-1,-1), colors.HexColor('#c5cae9')),
        ('FONTNAME',(0,0),(-1,-1),'Helvetica'),
        ('FONTSIZE',(0,0),(-1,-1),8),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('TOPPADDING',(0,0),(-1,-1),8),
        ('BOTTOMPADDING',(0,0),(-1,-1),8),
    ]))
    story.append(ft)
    doc.build(story)
    return buffer.getvalue()

# ===================== KLAVIATURALAR =====================
def main_menu_keyboard(user_id, data):
    """Har bir foydalanuvchi uchun asosiy menyu"""
    my_tests = [tid for tid, t in data["tests"].items() if t.get("owner_id") == user_id]
    buttons = [
        [KeyboardButton("📝 Testga javob berish")],
        [KeyboardButton("➕ Test qo'shish")],
    ]
    if my_tests:
        buttons.append([KeyboardButton("📋 Mening testlarim")])
    buttons.append([KeyboardButton("ℹ️ Yordam")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def admin_test_keyboard(test_id, is_active):
    buttons = []
    if is_active:
        buttons.append([InlineKeyboardButton("🏁 Testni yakunlash", callback_data=f"end:{test_id}")])
    buttons.append([InlineKeyboardButton("📊 PDF statistika", callback_data=f"pdf:{test_id}")])
    buttons.append([InlineKeyboardButton("📝 Matn statistika", callback_data=f"txt:{test_id}")])
    buttons.append([InlineKeyboardButton("🗑 O'chirish", callback_data=f"del:{test_id}")])
    buttons.append([InlineKeyboardButton("◀️ Orqaga", callback_data="my_tests")])
    return InlineKeyboardMarkup(buttons)

# ===================== START =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user

    # Kanal tekshiruvi
    is_sub = await check_subscription(user.id, context.bot)
    if not is_sub:
        await update.message.reply_text(
            f"👋 Salom, {user.first_name}!\n\n"
            f"⚠️ Botdan foydalanish uchun avval kanalimizga a'zo bo'ling!\n\n"
            f"📢 {CHANNEL_LINK}",
            reply_markup=sub_keyboard()
        )
        return ConversationHandler.END

    kb = main_menu_keyboard(user.id, data)
    await update.message.reply_text(
        f"👋 Salom, {user.first_name}!\n\n"
        f"🤖 *Test Bot*ga xush kelibsiz!\n\n"
        f"Quyidagi tugmalardan foydalaning 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb
    )
    return ConversationHandler.END

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    is_sub = await check_subscription(query.from_user.id, context.bot)
    if not is_sub:
        await query.edit_message_text(
            f"❌ Siz hali a'zo bo'lmadingiz!\n\nIltimos, avval kanalga a'zo bo'ling: {CHANNEL_LINK}",
            reply_markup=sub_keyboard()
        )
        return
    data = load_data()
    kb = main_menu_keyboard(query.from_user.id, data)
    await query.edit_message_text("✅ Rahmat! Endi botdan foydalanishingiz mumkin.")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Quyidagi tugmalardan foydalaning 👇",
        reply_markup=kb
    )

# ===================== TEST QO'SHISH (ConversationHandler) =====================
async def add_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    is_sub = await check_subscription(user.id, context.bot)
    if not is_sub:
        await update.message.reply_text(
            "⚠️ Botdan foydalanish uchun kanalga a'zo bo'ling!",
            reply_markup=sub_keyboard()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "➕ *Yangi test qo'shish*\n\n"
        "1️⃣ Test nomini yuboring:\n"
        "_(Misol: Jinoyat huquqi — 1-variant)_\n\n"
        "Bekor qilish uchun /cancel",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Bekor qilish")]], resize_keyboard=True)
    )
    return ADD_TEST_NAME

async def add_test_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await cancel_conv(update, context)
    context.user_data['new_test_name'] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ Nom: *{context.user_data['new_test_name']}*\n\n"
        f"2️⃣ Test uchun qisqa ID kiriting (lotin, raqam, _):\n"
        f"_(Misol: huquq1, variant2)_",
        parse_mode=ParseMode.MARKDOWN
    )
    return ADD_TEST_ID

async def add_test_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await cancel_conv(update, context)
    data = load_data()
    test_id = update.message.text.strip().lower().replace(" ", "_")
    # Faqat ruxsat etilgan belgilar
    if not re.match(r'^[a-z0-9_]+$', test_id):
        await update.message.reply_text(
            "❌ ID faqat lotin harflari, raqamlar va _ dan iborat bo'lishi kerak.\nQayta kiriting:"
        )
        return ADD_TEST_ID
    if test_id in data["tests"]:
        await update.message.reply_text(
            f"⚠️ *{test_id}* ID allaqachon mavjud. Boshqa ID kiriting:",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADD_TEST_ID
    context.user_data['new_test_id'] = test_id
    await update.message.reply_text(
        f"✅ ID: `{test_id}`\n\n"
        f"3️⃣ To'g'ri javoblarni yuboring:\n"
        f"📌 Format: `1a2b3c4d5e...`\n"
        f"_(Har savolga faqat 1 ta harf: a, b, c, d yoki e)_\n\n"
        f"Misol: `1a2b3d4c5e6b7a8d9c10b`",
        parse_mode=ParseMode.MARKDOWN
    )
    return ADD_TEST_ANSWERS

async def add_test_answers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await cancel_conv(update, context)

    text = update.message.text.strip()
    valid, err = validate_answers_strict(text)
    if not valid:
        await update.message.reply_text(err, parse_mode=ParseMode.MARKDOWN)
        return ADD_TEST_ANSWERS

    answers, err2 = parse_answers(text)
    if err2:
        await update.message.reply_text(f"❌ {err2}", parse_mode=ParseMode.MARKDOWN)
        return ADD_TEST_ANSWERS

    data = load_data()
    test_id = context.user_data['new_test_id']
    test_name = context.user_data['new_test_name']
    owner_id = update.effective_user.id

    data["tests"][test_id] = {
        "name": test_name,
        "answers": {str(k): v for k, v in answers.items()},
        "created_at": datetime.now().isoformat(),
        "active": True,
        "owner_id": owner_id
    }
    data["results"][test_id] = []
    save_data(data)

    formatted = "".join(f"{k}{v}" for k, v in sorted(answers.items()))
    kb = main_menu_keyboard(owner_id, data)
    await update.message.reply_text(
        f"✅ *Test muvaffaqiyatli qo'shildi!*\n\n"
        f"📋 Nom: *{test_name}*\n"
        f"🔑 ID: `{test_id}`\n"
        f"📊 Savollar: *{len(answers)}* ta\n"
        f"🟢 Holat: Faol\n\n"
        f"*Kanalda e'lon qilish uchun:*\n"
        f"```\nTest ID: {test_id}\n```\n"
        f"Foydalanuvchilar shu ID bilan javob yuborishadi.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb
    )
    return ConversationHandler.END

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    kb = main_menu_keyboard(update.effective_user.id, data)
    await update.message.reply_text(
        "❌ Bekor qilindi.",
        reply_markup=kb
    )
    return ConversationHandler.END

# ===================== TESTGA JAVOB BERISH =====================
async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    is_sub = await check_subscription(user.id, context.bot)
    if not is_sub:
        await update.message.reply_text(
            "⚠️ Botdan foydalanish uchun kanalga a'zo bo'ling!",
            reply_markup=sub_keyboard()
        )
        return ConversationHandler.END

    active = {tid: t for tid, t in data["tests"].items() if t.get("active")}
    if not active:
        await update.message.reply_text(
            "📭 Hozirda faol test mavjud emas.\nKeyinroq qaytib keling!",
            reply_markup=main_menu_keyboard(user.id, data)
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "✍️ *Javob berish*\n\n"
        "1️⃣ Ism va familiyangizni yuboring:\n"
        "_(Misol: Usmonov Ibrohim)_\n\n"
        "/cancel — bekor qilish",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Bekor qilish")]], resize_keyboard=True)
    )
    return SUBMIT_FULLNAME

async def submit_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await cancel_conv(update, context)
    fullname = update.message.text.strip()
    if len(fullname) < 3:
        await update.message.reply_text("❌ Ism familiya juda qisqa. Qayta yuboring:")
        return SUBMIT_FULLNAME
    context.user_data['submit_fullname'] = fullname

    data = load_data()
    active = {tid: t for tid, t in data["tests"].items() if t.get("active")}
    # Faol testlarni ko'rsatish
    tests_text = "\n".join([f"🔹 *{t['name']}* — ID: `{tid}`" for tid, t in active.items()])
    await update.message.reply_text(
        f"👤 Siz: *{fullname}*\n\n"
        f"2️⃣ Test ID'sini yuboring:\n\n"
        f"*Faol testlar:*\n{tests_text}",
        parse_mode=ParseMode.MARKDOWN
    )
    return SUBMIT_TEST_ID

async def submit_test_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await cancel_conv(update, context)
    data = load_data()
    test_id = update.message.text.strip().lower()
    if test_id not in data["tests"]:
        await update.message.reply_text(
            f"❌ *{test_id}* ID'li test topilmadi.\nTo'g'ri ID kiriting:",
            parse_mode=ParseMode.MARKDOWN
        )
        return SUBMIT_TEST_ID
    if not data["tests"][test_id].get("active"):
        await update.message.reply_text(
            f"⚠️ *{test_id}* testi yakunlangan. Boshqa ID kiriting:",
            parse_mode=ParseMode.MARKDOWN
        )
        return SUBMIT_TEST_ID

    context.user_data['submit_test_id'] = test_id
    test = data["tests"][test_id]
    total = len(test["answers"])
    await update.message.reply_text(
        f"✅ Test: *{test['name']}*\n"
        f"📊 Savollar soni: *{total}* ta\n\n"
        f"3️⃣ Javoblaringizni yuboring:\n"
        f"📌 Format: `1a2b3c4d5e...`\n"
        f"_(Har savolga faqat 1 ta harf)_\n\n"
        f"Misol: `1a2b3d4c5e6b`",
        parse_mode=ParseMode.MARKDOWN
    )
    return SUBMIT_ANSWERS

async def submit_answers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        return await cancel_conv(update, context)

    data = load_data()
    user = update.effective_user
    text = update.message.text.strip()
    test_id = context.user_data.get('submit_test_id')
    fullname = context.user_data.get('submit_fullname')

    if not test_id or test_id not in data["tests"]:
        await update.message.reply_text("❌ Xato yuz berdi. /start bosing.")
        return ConversationHandler.END

    # Strict tekshiruv
    valid, err = validate_answers_strict(text)
    if not valid:
        await update.message.reply_text(err, parse_mode=ParseMode.MARKDOWN)
        return SUBMIT_ANSWERS

    user_answers, err2 = parse_answers(text)
    if err2:
        await update.message.reply_text(f"❌ {err2}\n\nQayta yuboring:", parse_mode=ParseMode.MARKDOWN)
        return SUBMIT_ANSWERS

    test = data["tests"][test_id]
    correct = {int(k): v for k, v in test["answers"].items()}
    result = calculate_result(correct, user_answers)
    now = datetime.now().isoformat()

    entry = {
        "user_id": user.id,
        "username": user.username or "",
        "fullname": fullname,
        "answers": {str(k): v for k, v in user_answers.items()},
        "score": result["right"],
        "date": now
    }

    # Takroriy yuborish — yangilash
    results_list = data["results"].get(test_id, [])
    results_list = [r for r in results_list if r["user_id"] != user.id]
    results_list.append(entry)
    data["results"][test_id] = results_list
    save_data(data)

    # Foydalanuvchiga javob
    pct = result["percent"]
    emoji = "🏆" if pct>=80 else ("👍" if pct>=60 else ("📚" if pct>=40 else "💪"))
    grade = "A'lo" if pct>=80 else ("Yaxshi" if pct>=60 else ("Qoniqarli" if pct>=40 else "Qayta o'qing"))

    kb = main_menu_keyboard(user.id, data)
    await update.message.reply_text(
        f"✅ *Javobingiz qabul qilindi!*\n\n"
        f"👤 {fullname}\n"
        f"📋 Test: *{test['name']}*\n"
        f"📊 Natija: *{result['right']}/{result['total']}* ta to'g'ri\n"
        f"📈 Foiz: *{pct}%*\n"
        f"{emoji} Baho: *{grade}*\n\n"
        f"🏁 Test yakunlangach xatolaringizni ko'rishingiz mumkin!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb
    )

    # Test egasiga bildiruv
    owner_id = test.get("owner_id")
    if owner_id:
        try:
            await context.bot.send_message(
                chat_id=owner_id,
                text=f"🔔 *Yangi javob keldi!*\n\n"
                     f"👤 *{fullname}*\n"
                     f"📋 Test: *{test['name']}* (`{test_id}`)\n"
                     f"✅ To'g'ri: *{result['right']}/{result['total']}*\n"
                     f"📈 Foiz: *{pct}%*\n"
                     f"🕐 Vaqt: {datetime.fromisoformat(now).strftime('%d.%m.%Y %H:%M')}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            print(f"Egaga xabar yuborishda xato: {e}")

    return ConversationHandler.END

# ===================== MENING TESTLARIM =====================
async def my_tests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    is_sub = await check_subscription(user.id, context.bot)
    if not is_sub:
        await update.message.reply_text("⚠️ Kanalga a'zo bo'ling!", reply_markup=sub_keyboard())
        return

    my = {tid: t for tid, t in data["tests"].items() if t.get("owner_id") == user.id}
    if not my:
        await update.message.reply_text(
            "📭 Sizda hech qanday test yo'q.\n\n➕ Test qo'shish tugmasini bosing!",
            reply_markup=main_menu_keyboard(user.id, data)
        )
        return

    buttons = []
    for tid, t in my.items():
        status = "🟢" if t.get("active") else "🔴"
        count = len(data["results"].get(tid, []))
        buttons.append([InlineKeyboardButton(
            f"{status} {t['name']} ({count} ta javob)",
            callback_data=f"test_info:{tid}"
        )])

    await update.message.reply_text(
        "📋 *Mening testlarim:*\n\nBoshqarish uchun testni tanlang 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def test_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    if query.data == "my_tests":
        my = {tid: t for tid, t in data["tests"].items() if t.get("owner_id") == query.from_user.id}
        if not my:
            await query.edit_message_text("📭 Sizda test yo'q.")
            return
        buttons = []
        for tid, t in my.items():
            status = "🟢" if t.get("active") else "🔴"
            count = len(data["results"].get(tid, []))
            buttons.append([InlineKeyboardButton(
                f"{status} {t['name']} ({count} ta javob)",
                callback_data=f"test_info:{tid}"
            )])
        await query.edit_message_text(
            "📋 *Mening testlarim:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    _, test_id = query.data.split(":", 1)
    test = data["tests"].get(test_id)
    if not test:
        await query.edit_message_text("❌ Test topilmadi.")
        return

    # Faqat egasi boshqara oladi
    if test.get("owner_id") != query.from_user.id:
        await query.edit_message_text("❌ Bu test sizniki emas.")
        return

    count = len(data["results"].get(test_id, []))
    status = "🟢 Faol" if test.get("active") else "🔴 Yakunlangan"
    created = test.get("created_at", "")[:10]

    await query.edit_message_text(
        f"📋 *{test['name']}*\n\n"
        f"🔑 ID: `{test_id}`\n"
        f"📊 Savollar: *{len(test['answers'])}* ta\n"
        f"👥 Javoblar: *{count}* ta\n"
        f"📍 Holat: {status}\n"
        f"📅 Yaratilgan: {created}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_test_keyboard(test_id, test.get("active", False))
    )

async def test_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    action, test_id = query.data.split(":", 1)
    test = data["tests"].get(test_id)
    if not test:
        await query.edit_message_text("❌ Test topilmadi.")
        return
    if test.get("owner_id") != query.from_user.id:
        await query.edit_message_text("❌ Ruxsat yo'q.")
        return

    results = data["results"].get(test_id, [])
    correct = {int(k): v for k, v in test["answers"].items()}

    if action == "end":
        data["tests"][test_id]["active"] = False
        save_data(data)
        count = len(results)
        await query.edit_message_text(
            f"✅ *{test['name']}* yakunlandi!\n\n"
            f"👥 Jami {count} ta ishtirokchi\n\n"
            f"Statistikani olish uchun testni qayta oching 👆",
            parse_mode=ParseMode.MARKDOWN
        )

    elif action == "pdf":
        if not results:
            await query.edit_message_text("📭 Hech qanday natija yo'q.")
            return
        await query.edit_message_text("⏳ PDF tayyorlanmoqda...")
        pdf_bytes = generate_pdf(test["name"], results, correct)
        fname = f"statistika_{test_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=io.BytesIO(pdf_bytes),
            filename=fname,
            caption=f"📊 *{test['name']}*\n👥 {len(results)} ta ishtirokchi",
            parse_mode=ParseMode.MARKDOWN
        )
        await query.delete_message()

    elif action == "txt":
        if not results:
            await query.edit_message_text("📭 Hech qanday natija yo'q.")
            return
        total_q = len(correct)
        sorted_r = sorted(results, key=lambda x: (-x['score'], x.get('date','')))
        scores = [r['score'] for r in results]
        text = (
            f"📊 *{test['name']}* — Statistika\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"─────────────────────\n"
            f"👥 Ishtirokchi: *{len(results)}*\n"
            f"📈 O'rtacha: *{round(sum(scores)/len(scores),1)}/{total_q}*\n"
            f"🏆 Yuqori: *{max(scores)}/{total_q}*\n"
            f"📉 Past: *{min(scores)}/{total_q}*\n"
            f"─────────────────────\n\n"
        )
        for i, r in enumerate(sorted_r, 1):
            medal = {1:'🥇',2:'🥈',3:'🥉'}.get(i, f"{i}.")
            pct = round(r['score']/total_q*100,1) if total_q>0 else 0
            try:
                vaqt = datetime.fromisoformat(r['date']).strftime('%d.%m %H:%M')
            except:
                vaqt = ''
            text += f"{medal} *{r.get('fullname','?')}* — {r['score']}/{total_q} ({pct}%) | {vaqt}\n"

        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)

    elif action == "del":
        # Tasdiqlash
        await query.edit_message_text(
            f"⚠️ *{test['name']}* testini o'chirishni tasdiqlaysizmi?\n\n"
            f"Bu amal qaytarilmaydi!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Ha, o'chir", callback_data=f"delconfirm:{test_id}")],
                [InlineKeyboardButton("❌ Yo'q", callback_data=f"test_info:{test_id}")]
            ])
        )

async def del_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, test_id = query.data.split(":", 1)
    data = load_data()
    test = data["tests"].get(test_id)
    if not test or test.get("owner_id") != query.from_user.id:
        await query.edit_message_text("❌ Ruxsat yo'q.")
        return
    name = test["name"]
    del data["tests"][test_id]
    if test_id in data["results"]:
        del data["results"][test_id]
    save_data(data)
    await query.edit_message_text(f"✅ *{name}* o'chirildi.", parse_mode=ParseMode.MARKDOWN)

# ===================== XATOLARNI KO'RISH (yakunlangan test) =====================
async def show_my_errors_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi yakunlangan testda xatolarini ko'rish"""
    data = load_data()
    user = update.effective_user
    # Foydalanuvchi qatnashgan yakunlangan testlar
    finished = []
    for tid, t in data["tests"].items():
        if not t.get("active"):
            results = data["results"].get(tid, [])
            entry = next((r for r in results if r["user_id"] == user.id), None)
            if entry:
                finished.append((tid, t, entry))
    if not finished:
        await update.message.reply_text(
            "📭 Siz qatnashgan yakunlangan test yo'q.",
            reply_markup=main_menu_keyboard(user.id, data)
        )
        return
    buttons = [
        [InlineKeyboardButton(f"📋 {t['name']}", callback_data=f"myerr:{tid}")]
        for tid, t, _ in finished
    ]
    await update.message.reply_text(
        "🔍 Qaysi testdagi xatolaringizni ko'rmoqchisiz?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def my_errors_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, test_id = query.data.split(":", 1)
    data = load_data()
    test = data["tests"].get(test_id)
    results = data["results"].get(test_id, [])
    entry = next((r for r in results if r["user_id"] == query.from_user.id), None)
    if not entry:
        await query.edit_message_text("❌ Siz bu testda qatnashmadingiz.")
        return
    correct = {int(k): v for k, v in test["answers"].items()}
    user_ans = {int(k): v for k, v in entry["answers"].items()}
    result = calculate_result(correct, user_ans)
    error_text = ""
    if result["wrong"]:
        lines = "\n".join([f"❌ {n}-savol: Siz *{u.upper()}*, To'g'ri: *{c.upper()}*"
                           for n, u, c in sorted(result["wrong"])])
        error_text = f"\n\n🔴 *Xatolaringiz:*\n{lines}"
    if result["missing"]:
        error_text += f"\n\n⚠️ Javob berilmagan: {', '.join(str(n) for n in sorted(result['missing']))}"
    if not result["wrong"] and not result["missing"]:
        error_text = "\n\n🎉 Barcha javoblar to'g'ri edi!"
    await query.edit_message_text(
        f"📊 *{test['name']}* — Natijangiz\n\n"
        f"👤 {entry.get('fullname','')}\n"
        f"✅ To'g'ri: *{result['right']}/{result['total']}* ({result['percent']}%)"
        f"{error_text}",
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== YORDAM =====================
async def help_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(
        "ℹ️ *Yordam*\n\n"
        "📝 *Testga javob berish:*\n"
        "   Ism-familiya → Test ID → Javoblar\n\n"
        "➕ *Test qo'shish:*\n"
        "   Nom → ID → `1a2b3c...` javoblar\n\n"
        "📋 *Mening testlarim:*\n"
        "   Statistika, yakunlash, o'chirish\n\n"
        "📌 *Javob formati:* `1a2b3c4d5e`\n"
        "_(raqam + 1 ta harf, ketma-ket)_\n\n"
        f"📢 Kanal: {CHANNEL_LINK}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(update.effective_user.id, data)
    )

# ===================== MAIN HANDLER (tugmalar) =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    data = load_data()
    user = update.effective_user

    is_sub = await check_subscription(user.id, context.bot)
    if not is_sub:
        await update.message.reply_text("⚠️ Botdan foydalanish uchun kanalga a'zo bo'ling!", reply_markup=sub_keyboard())
        return

    if text == "📋 Mening testlarim":
        await my_tests_menu(update, context)
    elif text == "ℹ️ Yordam":
        await help_msg(update, context)
    elif text == "🔍 Xatolarimni ko'rish":
        await show_my_errors_flow(update, context)
    else:
        await update.message.reply_text(
            "Tugmalardan foydalaning 👇",
            reply_markup=main_menu_keyboard(user.id, data)
        )

# ===================== MAIN =====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Test qo'shish conversation
    add_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Test qo'shish$"), add_test_start)],
        states={
            ADD_TEST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_test_name)],
            ADD_TEST_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_test_id)],
            ADD_TEST_ANSWERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_test_answers)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv),
                   MessageHandler(filters.Regex("^❌ Bekor qilish$"), cancel_conv)],
    )

    # Javob berish conversation
    submit_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📝 Testga javob berish$"), submit_start)],
        states={
            SUBMIT_FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, submit_fullname)],
            SUBMIT_TEST_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, submit_test_id)],
            SUBMIT_ANSWERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, submit_answers)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv),
                   MessageHandler(filters.Regex("^❌ Bekor qilish$"), cancel_conv)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_conv))
    app.add_handler(add_conv)
    app.add_handler(submit_conv)

    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(test_info_callback, pattern="^test_info:"))
    app.add_handler(CallbackQueryHandler(test_info_callback, pattern="^my_tests$"))
    app.add_handler(CallbackQueryHandler(test_action_callback, pattern="^(end|pdf|txt|del):"))
    app.add_handler(CallbackQueryHandler(del_confirm_callback, pattern="^delconfirm:"))
    app.add_handler(CallbackQueryHandler(my_errors_callback, pattern="^myerr:"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

    print("🤖 Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

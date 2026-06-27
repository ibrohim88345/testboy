import os
import json
import re
import asyncio
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMember
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
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io

# ===================== KONFIGURATSIYA =====================
BOT_TOKEN = "8950300608:AAGKzpg2uIyKlijdgO7JhdMZLpo2nYIuHzo"
ADMIN_ID = None  # Birinchi /start bosgan admin bo'ladi, yoki quyida qo'ying
CHANNEL_USERNAME = "@huquqologiyauz"
CHANNEL_LINK = "https://t.me/huquqologiyauz"

# Ma'lumotlar fayli
DATA_FILE = "data.json"

# ===================== MA'LUMOTLAR =====================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "admin_id": None,
        "tests": {},       # test_id -> {name, answers, created_at, active}
        "results": {}      # test_id -> [{"user_id","username","answers","score","date"}]
    }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ===================== KANAL TEKSHIRISH =====================
async def check_subscription(user_id: int, bot) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in [
            ChatMember.MEMBER,
            ChatMember.ADMINISTRATOR,
            ChatMember.OWNER
        ]
    except Exception:
        return False

def subscription_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 Kanalga a'zo bo'lish", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ A'zo bo'ldim, tekshir", callback_data="check_sub")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===================== JAVOBLARNI PARSE QILISH =====================
def parse_answers(text: str):
    """1a2b3c4d shaklida parse qiladi"""
    text = text.strip().lower().replace(" ", "")
    pattern = re.findall(r'(\d+)([a-e])', text)
    if not pattern:
        return None
    answers = {}
    for num, letter in pattern:
        answers[int(num)] = letter
    return answers

def format_answers(answers: dict) -> str:
    return "".join(f"{k}{v}" for k, v in sorted(answers.items()))

# ===================== NATIJALARNI HISOBLASH =====================
def calculate_result(correct: dict, user: dict):
    total = len(correct)
    right = 0
    wrong = []
    missing = []
    
    for num, ans in correct.items():
        if num in user:
            if user[num] == ans:
                right += 1
            else:
                wrong.append((num, user[num], ans))
        else:
            missing.append(num)
    
    return {
        "total": total,
        "right": right,
        "wrong": wrong,
        "missing": missing,
        "percent": round(right / total * 100, 1) if total > 0 else 0
    }

# ===================== PDF GENERATSIYA =====================
def generate_pdf(test_name: str, results: list, correct_answers: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=1.5*cm
    )
    
    story = []
    
    # Ranglar
    PRIMARY = colors.HexColor('#1a237e')
    SECONDARY = colors.HexColor('#283593')
    ACCENT = colors.HexColor('#e8eaf6')
    GREEN = colors.HexColor('#2e7d32')
    RED = colors.HexColor('#c62828')
    GOLD = colors.HexColor('#f57f17')
    LIGHT_GRAY = colors.HexColor('#f5f5f5')
    WHITE = colors.white
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'Title', fontSize=20, textColor=WHITE,
        alignment=TA_CENTER, fontName='Helvetica-Bold',
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'Subtitle', fontSize=11, textColor=colors.HexColor('#c5cae9'),
        alignment=TA_CENTER, fontName='Helvetica', spaceAfter=0
    )
    header_style = ParagraphStyle(
        'Header', fontSize=13, textColor=PRIMARY,
        fontName='Helvetica-Bold', spaceAfter=6
    )
    normal_style = ParagraphStyle(
        'Normal2', fontSize=9, textColor=colors.HexColor('#424242'),
        fontName='Helvetica'
    )
    
    # --- SARLAVHA BLOKI ---
    title_table = Table(
        [[Paragraph(f"📊 {test_name}", title_style)],
         [Paragraph(f"Natijalar statistikasi | {datetime.now().strftime('%d.%m.%Y %H:%M')}", subtitle_style)]],
        colWidths=[18*cm]
    )
    title_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), PRIMARY),
        ('TOPPADDING', (0,0), (-1,0), 16),
        ('BOTTOMPADDING', (0,-1), (-1,-1), 16),
        ('LEFTPADDING', (0,0), (-1,-1), 20),
        ('RIGHTPADDING', (0,0), (-1,-1), 20),
        ('ROUNDEDCORNERS', [8]),
    ]))
    story.append(title_table)
    story.append(Spacer(1, 0.5*cm))
    
    # --- UMUMIY STATISTIKA ---
    if results:
        scores = [r['score'] for r in results]
        avg = round(sum(scores) / len(scores), 1)
        max_s = max(scores)
        min_s = min(scores)
        total_q = len(correct_answers)
        
        stat_data = [
            ['👥 Ishtirokchilar', '📝 Savollar', '📈 O\'rtacha', '🏆 Eng yuqori', '📉 Eng past'],
            [
                str(len(results)),
                str(total_q),
                f"{avg}/{total_q}",
                f"{max_s}/{total_q}",
                f"{min_s}/{total_q}"
            ]
        ]
        
        stat_table = Table(stat_data, colWidths=[3.4*cm]*5)
        stat_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), SECONDARY),
            ('TEXTCOLOR', (0,0), (-1,0), WHITE),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), ACCENT),
            ('TEXTCOLOR', (0,1), (-1,-1), PRIMARY),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,1), (-1,-1), 14),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [ACCENT]),
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#9fa8da')),
        ]))
        story.append(stat_table)
        story.append(Spacer(1, 0.4*cm))
    
    # --- NATIJALAR JADVALI ---
    story.append(Paragraph("🏅 Ishtirokchilar natijalari", header_style))
    
    table_data = [['#', 'Ism', 'To\'g\'ri', 'Xato', 'Ball', '%', 'Sana']]
    
    sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)
    
    for i, r in enumerate(sorted_results, 1):
        total_q = len(correct_answers)
        wrong_count = total_q - r['score']
        percent = round(r['score'] / total_q * 100, 1) if total_q > 0 else 0
        
        # Rang belgilash
        if percent >= 80:
            ball_color = GREEN
        elif percent >= 50:
            ball_color = GOLD
        else:
            ball_color = RED
        
        # Medal
        medal = {1: '🥇', 2: '🥈', 3: '🥉'}.get(i, str(i))
        
        name = r.get('username') or r.get('first_name') or f"Foydalanuvchi {r['user_id']}"
        
        table_data.append([
            medal,
            name[:22],
            str(r['score']),
            str(wrong_count),
            f"{r['score']}/{total_q}",
            f"{percent}%",
            r.get('date', '')[:10]
        ])
    
    col_widths = [1.2*cm, 5*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2.5*cm]
    results_table = Table(table_data, colWidths=col_widths)
    
    table_style = [
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 8),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#c5cae9')),
    ]
    
    for i in range(1, len(table_data)):
        bg = WHITE if i % 2 == 0 else LIGHT_GRAY
        table_style.append(('BACKGROUND', (0,i), (-1,i), bg))
        
        # Ball ustuniga rang
        total_q = len(correct_answers)
        try:
            score = sorted_results[i-1]['score']
            pct = score / total_q * 100 if total_q > 0 else 0
            if pct >= 80:
                table_style.append(('TEXTCOLOR', (4,i), (5,i), GREEN))
            elif pct >= 50:
                table_style.append(('TEXTCOLOR', (4,i), (5,i), GOLD))
            else:
                table_style.append(('TEXTCOLOR', (4,i), (5,i), RED))
            table_style.append(('FONTNAME', (4,i), (5,i), 'Helvetica-Bold'))
        except:
            pass
    
    results_table.setStyle(TableStyle(table_style))
    story.append(results_table)
    story.append(Spacer(1, 0.4*cm))
    
    # --- TO'G'RI JAVOBLAR ---
    story.append(Paragraph("✅ To'g'ri javoblar", header_style))
    
    ans_items = sorted(correct_answers.items())
    rows_per_row = 10
    ans_rows = []
    
    for i in range(0, len(ans_items), rows_per_row):
        chunk = ans_items[i:i+rows_per_row]
        header_row = [f"#{num}" for num, _ in chunk]
        ans_row = [ans.upper() for _, ans in chunk]
        # pad
        while len(header_row) < rows_per_row:
            header_row.append('')
            ans_row.append('')
        ans_rows.append(header_row)
        ans_rows.append(ans_row)
    
    if ans_rows:
        col_w = [1.7*cm] * rows_per_row
        ans_table = Table(ans_rows, colWidths=col_w)
        ans_style = []
        for i in range(0, len(ans_rows), 2):
            ans_style += [
                ('BACKGROUND', (0,i), (-1,i), SECONDARY),
                ('TEXTCOLOR', (0,i), (-1,i), WHITE),
                ('FONTNAME', (0,i), (-1,i), 'Helvetica-Bold'),
                ('FONTSIZE', (0,i), (-1,i), 7),
                ('BACKGROUND', (0,i+1), (-1,i+1), colors.HexColor('#e8eaf6')),
                ('TEXTCOLOR', (0,i+1), (-1,i+1), PRIMARY),
                ('FONTNAME', (0,i+1), (-1,i+1), 'Helvetica-Bold'),
                ('FONTSIZE', (0,i+1), (-1,i+1), 10),
            ]
        ans_style += [
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#9fa8da')),
        ]
        ans_table.setStyle(TableStyle(ans_style))
        story.append(ans_table)
    
    # --- FOOTER ---
    story.append(Spacer(1, 0.5*cm))
    footer_data = [[f"© {datetime.now().year} | @huquqologiyauz | Yaratilgan vaqt: {datetime.now().strftime('%d.%m.%Y %H:%M')}"]]
    footer_table = Table(footer_data, colWidths=[18*cm])
    footer_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor('#c5cae9')),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(footer_table)
    
    doc.build(story)
    return buffer.getvalue()

# ===================== HANDLERS =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    
    # Birinchi admin
    if data["admin_id"] is None:
        data["admin_id"] = user.id
        save_data(data)
    
    is_admin = user.id == data["admin_id"]
    
    if is_admin:
        await update.message.reply_text(
            f"👋 Salom, Admin!\n\n"
            f"🤖 *Test Bot* boshqaruv paneliga xush kelibsiz.\n\n"
            f"📋 *Buyruqlar:*\n"
            f"➕ /addtest — Yangi test qo'shish\n"
            f"📊 /tests — Barcha testlar ro'yxati\n"
            f"🏁 /endtest — Testni yakunlash\n"
            f"📈 /stats — Statistika (PDF)\n"
            f"📝 /statstext — Statistika (matn)\n"
            f"🗑 /deletetest — Testni o'chirish\n"
            f"ℹ️ /help — Yordam",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Oddiy foydalanuvchi — kanal tekshiruvi
    is_subscribed = await check_subscription(user.id, context.bot)
    
    if not is_subscribed:
        await update.message.reply_text(
            f"👋 Salom, {user.first_name}!\n\n"
            f"⚠️ Botdan foydalanish uchun avval kanalimizga a'zo bo'lishingiz shart!\n\n"
            f"📢 Kanal: {CHANNEL_LINK}\n\n"
            f"A'zo bo'lgach, pastdagi tugmani bosing 👇",
            reply_markup=subscription_keyboard()
        )
        return
    
    await show_user_menu(update, context)

async def show_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    active_tests = {tid: t for tid, t in data["tests"].items() if t.get("active")}
    
    if not active_tests:
        text = (
            f"👋 Salom!\n\n"
            f"📋 Hozirda faol test mavjud emas.\n"
            f"Tez orada test qo'yiladi, kuting! 🕐"
        )
    else:
        tests_list = "\n".join([f"🔹 *{t['name']}* (ID: `{tid}`)" for tid, t in active_tests.items()])
        text = (
            f"👋 Salom!\n\n"
            f"📝 *Faol testlar:*\n{tests_list}\n\n"
            f"✍️ Javob yuborish uchun quyidagi formatdan foydalaning:\n"
            f"```\ntest_id 1a2b3c4d...\n```\n"
            f"*Misol:* `test1 1a2b3c4d5e`"
        )
    
    await (update.message or update.callback_query.message).reply_text(
        text, parse_mode=ParseMode.MARKDOWN
    )

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    is_subscribed = await check_subscription(query.from_user.id, context.bot)
    
    if not is_subscribed:
        await query.edit_message_text(
            f"❌ Siz hali kanalga a'zo bo'lmadingiz!\n\n"
            f"Iltimos, avval {CHANNEL_LINK} kanaliga a'zo bo'ling, so'ng qayta tekshiring. 👇",
            reply_markup=subscription_keyboard()
        )
        return
    
    await query.edit_message_text(
        f"✅ Zo'r! Siz kanalga a'zo bo'lgansiz.\n\n"
        f"Endi /start bosib botdan foydalanishingiz mumkin! 🎉"
    )

# ===================== ADMIN: TEST QO'SHISH =====================

async def addtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if update.effective_user.id != data["admin_id"]:
        await update.message.reply_text("❌ Sizda ruxsat yo'q.")
        return
    
    context.user_data['state'] = 'waiting_test_name'
    await update.message.reply_text(
        "📝 *Yangi test qo'shish*\n\n"
        "1️⃣ Avval test nomini yuboring:\n"
        "_(Misol: Jinoyat huquqi — 1-variant)_",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    text = update.message.text.strip()
    
    # ADMIN HOLATLARI
    if user.id == data["admin_id"]:
        state = context.user_data.get('state', '')
        
        if state == 'waiting_test_name':
            context.user_data['test_name'] = text
            context.user_data['state'] = 'waiting_test_id'
            await update.message.reply_text(
                f"✅ Test nomi: *{text}*\n\n"
                f"2️⃣ Endi test ID'sini yuboring (faqat lotin harflari va raqamlar):\n"
                f"_(Misol: test1, variant2, huquq_2024)_",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if state == 'waiting_test_id':
            test_id = text.lower().replace(" ", "_")
            if test_id in data["tests"]:
                await update.message.reply_text(
                    f"⚠️ Bu ID allaqachon mavjud: *{test_id}*\n"
                    f"Boshqa ID kiriting:",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            context.user_data['test_id'] = test_id
            context.user_data['state'] = 'waiting_test_answers'
            await update.message.reply_text(
                f"✅ Test ID: *{test_id}*\n\n"
                f"3️⃣ Endi to'g'ri javoblarni yuboring:\n"
                f"📌 Format: `1a2b3c4d5e...`\n\n"
                f"_(Misol: 1a2b3d4c5e6b7a8d9c10b)_",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if state == 'waiting_test_answers':
            answers = parse_answers(text)
            if not answers:
                await update.message.reply_text(
                    "❌ Format noto'g'ri! Qaytadan yuboring.\n"
                    "📌 To'g'ri format: `1a2b3c4d5e`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            test_id = context.user_data['test_id']
            test_name = context.user_data['test_name']
            
            data["tests"][test_id] = {
                "name": test_name,
                "answers": {str(k): v for k, v in answers.items()},
                "created_at": datetime.now().isoformat(),
                "active": True
            }
            if test_id not in data["results"]:
                data["results"][test_id] = []
            save_data(data)
            
            context.user_data['state'] = ''
            
            formatted = format_answers(answers)
            await update.message.reply_text(
                f"✅ *Test muvaffaqiyatli qo'shildi!*\n\n"
                f"📋 Nom: *{test_name}*\n"
                f"🔑 ID: `{test_id}`\n"
                f"📊 Savollar soni: *{len(answers)}* ta\n"
                f"🗝 Javoblar: `{formatted}`\n\n"
                f"🟢 Test faol holda. Foydalanuvchilar javob yuborishdi mumkin.\n\n"
                f"*Kanalda e'lon qilish uchun:*\n"
                f"```\nJavoblar: {test_id} 1a2b3c...\nBot: @{(await context.bot.get_me()).username}\n```",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Admin buyruqlar kelsa ham foydalanuvchi oqimiga tushmasin
        if not text.startswith('/'):
            await update.message.reply_text(
                "ℹ️ Buyruqlar uchun /help yuboring."
            )
        return
    
    # ODDIY FOYDALANUVCHI
    is_subscribed = await check_subscription(user.id, context.bot)
    if not is_subscribed:
        await update.message.reply_text(
            "⚠️ Botdan foydalanish uchun kanalga a'zo bo'ling!",
            reply_markup=subscription_keyboard()
        )
        return
    
    # Javob formati: "test_id 1a2b3c..."
    parts = text.split(None, 1)
    if len(parts) != 2:
        await update.message.reply_text(
            "📌 *Format:* `test_id 1a2b3c4d...`\n\n"
            "Misol: `test1 1a2b3c4d5e`\n\n"
            "Faol testlarni ko'rish uchun /start bosing.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    test_id, answers_text = parts
    test_id = test_id.lower()
    
    if test_id not in data["tests"]:
        await update.message.reply_text(
            f"❌ *{test_id}* ID'li test topilmadi.\n\n"
            f"Faol testlarni ko'rish uchun /start bosing.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    test = data["tests"][test_id]
    
    if not test.get("active"):
        # Test yakunlangan — xatolarni ko'rsatish mumkin
        await show_finished_test_results(update, context, data, test_id, user, answers_text)
        return
    
    user_answers = parse_answers(answers_text)
    if not user_answers:
        await update.message.reply_text(
            "❌ Javob formati noto'g'ri!\n"
            "📌 To'g'ri format: `1a2b3c4d5e`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    correct = {int(k): v for k, v in test["answers"].items()}
    result = calculate_result(correct, user_answers)
    
    # Natijani saqlash
    entry = {
        "user_id": user.id,
        "username": user.username or user.first_name or "Noma'lum",
        "first_name": user.first_name,
        "answers": {str(k): v for k, v in user_answers.items()},
        "score": result["right"],
        "date": datetime.now().isoformat()
    }
    
    # Takroriy yuborish oldini olish
    existing = next((r for r in data["results"].get(test_id, []) if r["user_id"] == user.id), None)
    if existing:
        data["results"][test_id].remove(existing)
    
    data["results"].setdefault(test_id, []).append(entry)
    save_data(data)
    
    # Foydalanuvchiga javob
    pct = result["percent"]
    if pct >= 80:
        emoji = "🏆"
        grade = "A'lo"
    elif pct >= 60:
        emoji = "👍"
        grade = "Yaxshi"
    elif pct >= 40:
        emoji = "📚"
        grade = "Qoniqarli"
    else:
        emoji = "💪"
        grade = "Qayta o'qing"
    
    keyboard = [[InlineKeyboardButton("🔍 Xatolarimni ko'rish", callback_data=f"show_errors:{test_id}")]]
    # Faqat test yakunlanganda ko'rsatiladi — hozir disabled qilamiz
    keyboard = []  # Test faol — xatolarni ko'rsatmaymiz
    
    await update.message.reply_text(
        f"✅ *Javobingiz qabul qilindi!*\n\n"
        f"📋 Test: *{test['name']}*\n"
        f"📊 Natija: *{result['right']}/{result['total']}* ta to'g'ri\n"
        f"📈 Foiz: *{pct}%*\n"
        f"{emoji} Baho: *{grade}*\n\n"
        f"🏁 Test yakunlangach xatolaringizni ko'rishingiz mumkin bo'ladi!",
        parse_mode=ParseMode.MARKDOWN
    )

async def show_finished_test_results(update, context, data, test_id, user, answers_text=None):
    """Yakunlangan test uchun foydalanuvchi xatolarini ko'rsatish"""
    test = data["tests"][test_id]
    results = data["results"].get(test_id, [])
    entry = next((r for r in results if r["user_id"] == user.id), None)
    
    if not entry:
        await update.message.reply_text(
            f"❌ Siz bu testda qatnashmadingiz yoki test yakunlangan.\n"
            f"Test ID: *{test_id}*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    correct = {int(k): v for k, v in test["answers"].items()}
    user_ans = {int(k): v for k, v in entry["answers"].items()}
    result = calculate_result(correct, user_ans)
    
    error_text = ""
    if result["wrong"]:
        errors = "\n".join([
            f"  ❌ {num}-savol: Siz *{u.upper()}*, To'g'ri: *{c.upper()}*"
            for num, u, c in sorted(result["wrong"])
        ])
        error_text = f"\n\n🔴 *Xatolaringiz:*\n{errors}"
    
    if result["missing"]:
        missing = ", ".join(str(n) for n in sorted(result["missing"]))
        error_text += f"\n\n⚠️ *Javob berilmagan:* {missing}"
    
    if not result["wrong"] and not result["missing"]:
        error_text = "\n\n🎉 *Barcha javoblar to'g'ri!*"
    
    await update.message.reply_text(
        f"📊 *Test yakunlandi — Natijangiz*\n\n"
        f"📋 Test: *{test['name']}*\n"
        f"✅ To'g'ri: *{result['right']}/{result['total']}*\n"
        f"📈 Foiz: *{result['percent']}%*"
        f"{error_text}",
        parse_mode=ParseMode.MARKDOWN
    )

async def show_errors_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, test_id = query.data.split(":", 1)
    data = load_data()
    user = query.from_user
    
    test = data["tests"].get(test_id)
    if not test or test.get("active"):
        await query.edit_message_text("⏳ Test hali yakunlanmagan. Kuting!")
        return
    
    results = data["results"].get(test_id, [])
    entry = next((r for r in results if r["user_id"] == user.id), None)
    
    if not entry:
        await query.edit_message_text("❌ Siz bu testda qatnashmadingiz.")
        return
    
    correct = {int(k): v for k, v in test["answers"].items()}
    user_ans = {int(k): v for k, v in entry["answers"].items()}
    result = calculate_result(correct, user_ans)
    
    error_lines = ""
    if result["wrong"]:
        error_lines = "\n".join([
            f"❌ {num}-savol: Siz *{u.upper()}*, To'g'ri: *{c.upper()}*"
            for num, u, c in sorted(result["wrong"])
        ])
    else:
        error_lines = "🎉 Barcha javoblar to'g'ri!"
    
    if result["missing"]:
        error_lines += f"\n\n⚠️ Javob berilmagan: {', '.join(str(n) for n in sorted(result['missing']))}"
    
    await query.edit_message_text(
        f"🔍 *Xatolaringiz — {test['name']}*\n\n"
        f"✅ To'g'ri: *{result['right']}/{result['total']}* ({result['percent']}%)\n\n"
        f"{error_lines}",
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== ADMIN: TESTLAR RO'YXATI =====================

async def tests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if update.effective_user.id != data["admin_id"]:
        return
    
    if not data["tests"]:
        await update.message.reply_text("📭 Hech qanday test yo'q.")
        return
    
    text = "📋 *Barcha testlar:*\n\n"
    for tid, t in data["tests"].items():
        status = "🟢 Faol" if t.get("active") else "🔴 Yakunlangan"
        count = len(data["results"].get(tid, []))
        text += (
            f"🔹 *{t['name']}*\n"
            f"   ID: `{tid}` | {status} | 👥 {count} ta javob\n"
            f"   📅 {t['created_at'][:10]}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ===================== ADMIN: TEST YAKUNLASH =====================

async def endtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if update.effective_user.id != data["admin_id"]:
        return
    
    active = {tid: t for tid, t in data["tests"].items() if t.get("active")}
    if not active:
        await update.message.reply_text("❌ Yakunlash uchun faol test yo'q.")
        return
    
    keyboard = [
        [InlineKeyboardButton(f"🏁 {t['name']}", callback_data=f"endtest:{tid}")]
        for tid, t in active.items()
    ]
    keyboard.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")])
    
    await update.message.reply_text(
        "🏁 *Qaysi testni yakunlamoqchisiz?*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def endtest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Bekor qilindi.")
        return
    
    _, test_id = query.data.split(":", 1)
    data = load_data()
    
    if update.effective_user.id != data["admin_id"]:
        return
    
    data["tests"][test_id]["active"] = False
    save_data(data)
    
    count = len(data["results"].get(test_id, []))
    test_name = data["tests"][test_id]["name"]
    
    await query.edit_message_text(
        f"✅ *{test_name}* — test yakunlandi!\n\n"
        f"👥 Jami {count} ta ishtirokchi\n\n"
        f"📊 Statistikani olish uchun:\n"
        f"/stats — PDF ko'rinishida\n"
        f"/statstext — Matn ko'rinishida",
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== ADMIN: STATISTIKA =====================

async def stats_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if update.effective_user.id != data["admin_id"]:
        return
    
    # Test tanlash
    if not data["tests"]:
        await update.message.reply_text("📭 Testlar yo'q.")
        return
    
    keyboard = [
        [InlineKeyboardButton(f"📊 {t['name']}", callback_data=f"statspdf:{tid}")]
        for tid, t in data["tests"].items()
    ]
    
    await update.message.reply_text(
        "📊 *Qaysi test statistikasini PDF ko'rinishida olmoqchisiz?*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def stats_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if update.effective_user.id != data["admin_id"]:
        return
    
    if not data["tests"]:
        await update.message.reply_text("📭 Testlar yo'q.")
        return
    
    keyboard = [
        [InlineKeyboardButton(f"📝 {t['name']}", callback_data=f"statstext:{tid}")]
        for tid, t in data["tests"].items()
    ]
    
    await update.message.reply_text(
        "📝 *Qaysi test statistikasini matn ko'rinishida olmoqchisiz?*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Tayyorlanmoqda...")
    
    data = load_data()
    
    if query.data.startswith("statspdf:"):
        test_id = query.data.split(":", 1)[1]
        test = data["tests"].get(test_id)
        results = data["results"].get(test_id, [])
        
        if not results:
            await query.edit_message_text("📭 Bu test uchun natijalar yo'q.")
            return
        
        await query.edit_message_text("⏳ PDF tayyorlanmoqda...")
        
        correct = {int(k): v for k, v in test["answers"].items()}
        pdf_bytes = generate_pdf(test["name"], results, correct)
        
        filename = f"statistika_{test_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        
        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=io.BytesIO(pdf_bytes),
            filename=filename,
            caption=f"📊 *{test['name']}* — statistika\n👥 {len(results)} ta ishtirokchi",
            parse_mode=ParseMode.MARKDOWN
        )
        await query.delete_message()
    
    elif query.data.startswith("statstext:"):
        test_id = query.data.split(":", 1)[1]
        test = data["tests"].get(test_id)
        results = data["results"].get(test_id, [])
        correct = {int(k): v for k, v in test["answers"].items()}
        
        if not results:
            await query.edit_message_text("📭 Bu test uchun natijalar yo'q.")
            return
        
        sorted_r = sorted(results, key=lambda x: x['score'], reverse=True)
        total_q = len(correct)
        
        text = f"📊 *{test['name']}* — Statistika\n"
        text += f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        text += f"─────────────────────\n"
        text += f"👥 Ishtirokchilar: *{len(results)}* ta\n"
        
        if results:
            scores = [r['score'] for r in results]
            text += f"📈 O'rtacha ball: *{round(sum(scores)/len(scores),1)}/{total_q}*\n"
            text += f"🏆 Eng yuqori: *{max(scores)}/{total_q}*\n"
            text += f"📉 Eng past: *{min(scores)}/{total_q}*\n"
        
        text += f"─────────────────────\n\n"
        text += f"🏅 *Natijalar ro'yxati:*\n"
        
        for i, r in enumerate(sorted_r, 1):
            medal = {1:'🥇',2:'🥈',3:'🥉'}.get(i, f"{i}.")
            name = r.get('username') or r.get('first_name') or "Noma'lum"
            pct = round(r['score']/total_q*100,1) if total_q > 0 else 0
            text += f"{medal} *{name}* — {r['score']}/{total_q} ({pct}%)\n"
        
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)

# ===================== ADMIN: O'CHIRISH =====================

async def deletetest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if update.effective_user.id != data["admin_id"]:
        return
    
    if not data["tests"]:
        await update.message.reply_text("📭 Testlar yo'q.")
        return
    
    keyboard = [
        [InlineKeyboardButton(f"🗑 {t['name']}", callback_data=f"deltest:{tid}")]
        for tid, t in data["tests"].items()
    ]
    keyboard.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")])
    
    await update.message.reply_text(
        "🗑 *Qaysi testni o'chirmoqchisiz?*\n"
        "⚠️ Bu amal qaytarilmaydi!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def deltest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Bekor qilindi.")
        return
    
    _, test_id = query.data.split(":", 1)
    data = load_data()
    
    if update.effective_user.id != data["admin_id"]:
        return
    
    test_name = data["tests"][test_id]["name"]
    del data["tests"][test_id]
    if test_id in data["results"]:
        del data["results"][test_id]
    save_data(data)
    
    await query.edit_message_text(f"✅ *{test_name}* test o'chirildi.", parse_mode=ParseMode.MARKDOWN)

# ===================== HELP =====================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    is_admin = update.effective_user.id == data["admin_id"]
    
    if is_admin:
        text = (
            "📖 *Admin Yordam*\n\n"
            "➕ /addtest — Yangi test qo'shish\n"
            "   _Bosqichma-bosqich: nom → ID → javoblar_\n\n"
            "📋 /tests — Barcha testlar ro'yxati\n\n"
            "🏁 /endtest — Testni yakunlash\n"
            "   _Yakunlangach foydalanuvchilar xatolarini ko'ra oladi_\n\n"
            "📊 /stats — PDF statistika\n\n"
            "📝 /statstext — Matn statistika\n\n"
            "🗑 /deletetest — Testni o'chirish\n\n"
            "📌 *Javob formati:* `1a2b3c4d5e...`\n"
            "_(raqam + harf, ketma-ket)_"
        )
    else:
        text = (
            "📖 *Yordam*\n\n"
            "✍️ *Javob yuborish:*\n"
            "`test_id 1a2b3c4d5e`\n\n"
            "📌 *Misol:*\n"
            "`huquq1 1a2b3d4c5e6b`\n\n"
            "🔹 test_id — admin e'lon qilgan ID\n"
            "🔹 Keyin javoblar: raqam + harf\n\n"
            "🏁 Test yakunlangach xatolaringizni ko'rishingiz mumkin."
        )
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ===================== MAIN =====================

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addtest", addtest))
    app.add_handler(CommandHandler("tests", tests_list))
    app.add_handler(CommandHandler("endtest", endtest))
    app.add_handler(CommandHandler("stats", stats_pdf))
    app.add_handler(CommandHandler("statstext", stats_text))
    app.add_handler(CommandHandler("deletetest", deletetest))
    app.add_handler(CommandHandler("help", help_command))
    
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(endtest_callback, pattern="^endtest:"))
    app.add_handler(CallbackQueryHandler(stats_callback, pattern="^statspdf:"))
    app.add_handler(CallbackQueryHandler(stats_callback, pattern="^statstext:"))
    app.add_handler(CallbackQueryHandler(deltest_callback, pattern="^deltest:"))
    app.add_handler(CallbackQueryHandler(show_errors_callback, pattern="^show_errors:"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.edit_message_text("❌ Bekor qilindi."), pattern="^cancel$"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Test Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

# 📚 Huquqologiya Test Bot

## 🚀 Bosqichma-bosqich ishga tushirish

### Variant 1: Railway.app (BEPUL, DOIMIY, OSON) — TAVSIYA ETILADI

1. **https://railway.app** — ga kiring, GitHub bilan ro'yxatdan o'ting (bepul)
2. **New Project → Deploy from GitHub repo** tanlang
3. Bu papkani GitHub'ga yuklang:
   - https://github.com ga kiring
   - **New repository** → nom bering (masalan: testbot)
   - Fayllarni yuklang: `bot.py`, `requirements.txt`, `Procfile`, `runtime.txt`
4. Railway'da GitHub repo'ni tanlang
5. **Variables** bo'limida hech narsa kiritish shart emas (token kodda)
6. **Deploy** — tugdi! Bot doimiy ishlaydi ✅

---

### Variant 2: Render.com (BEPUL)

1. **https://render.com** — GitHub bilan kirish
2. **New → Background Worker** tanlang
3. GitHub repo'ni ulang
4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:** `python bot.py`
6. **Create** — tayyor!

---

### Variant 3: VPS/Server bo'lsa

```bash
# 1. Fayllarni serverga yuklang
# 2. Kutubxonalarni o'rnating
pip install -r requirements.txt

# 3. Botni ishga tushiring (fon rejimida)
nohup python bot.py &

# Yoki screen bilan:
screen -S testbot
python bot.py
# Ctrl+A+D — fonga o'tish
```

---

### Variant 4: Lokal test qilish

```bash
pip install -r requirements.txt
python bot.py
```

---

## 📁 Kerakli fayllar

```
testbot/
├── bot.py           # Asosiy bot kodi
├── requirements.txt # Kutubxonalar
├── Procfile         # Railway/Heroku uchun
├── runtime.txt      # Python versiyasi
└── README.md        # Shu fayl
```

---

## 🎮 Bot funksiyalari

### Admin (siz):
| Buyruq | Vazifasi |
|--------|----------|
| `/addtest` | Yangi test qo'shish |
| `/tests` | Barcha testlar ro'yxati |
| `/endtest` | Testni yakunlash |
| `/stats` | PDF statistika |
| `/statstext` | Matn statistika |
| `/deletetest` | Testni o'chirish |

### Test qo'shish jarayoni:
```
/addtest
→ Test nomini yuboring
→ Test ID'sini yuboring (masalan: huquq1)
→ Javoblarni yuboring (1a2b3c4d5e...)
✅ Test faol!
```

### Foydalanuvchilar:
```
# Javob yuborish:
test_id 1a2b3c4d5e

# Misol:
huquq1 1a2b3d4c5e6b7a
```

---

## ⚙️ Kanal o'zgartirish

`bot.py` faylida:
```python
CHANNEL_USERNAME = "@huquqologiyauz"
CHANNEL_LINK = "https://t.me/huquqologiyauz"
```
Bu yerda o'z kanalingizni kiriting.

---

## 📊 Ma'lumotlar

Barcha testlar va natijalar `data.json` faylida saqlanadi.
Railway/Render'da persistent disk ulash tavsiya etiladi (yoki Supabase/MongoDB).

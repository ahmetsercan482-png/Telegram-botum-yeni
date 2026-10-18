import os
import json
import asyncio
import logging
import time

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)


TOKEN = "TOKENINI_BURAYA_YAPISTIR"

ADMIN_ID = 1138570615


KANALLAR = []
KANAL_KONTROL_AKTIF = True


aboneler = set()


# Paketler
chatgpt = []
whatsapp = []
youtube = []
speedtest = []
paketsiz = []


# Admin işlemleri
dosya_yukleme = set()
duyuru_modu = set()
silme_modu = set()

# Davet sistemi için yeni kayıtlar
davet_hedef_modu = set()


def load(dosya, varsayilan):
    if os.path.exists(dosya):
        try:
            with open(dosya, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return varsayilan
    return varsayilan


def save(dosya, veri):
    if isinstance(veri, set):
        veri = list(veri)

    with open(dosya, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)


def paket_kayitlari():
    return [
        ("chatgpt", chatgpt), ("whatsapp", whatsapp),
        ("youtube", youtube), ("speedtest", speedtest), ("paketsiz", paketsiz)
    ]


def suresi_dolanlari_temizle():
    """Süresi dolan dosyaları paket JSON'larından kaldırır. Süresiz ve eski kayıtlar kalır."""
    degisen = False
    yollar = {
        "chatgpt": "chatgpt.json", "whatsapp": "whatsapp.json",
        "youtube": "youtube.json", "speedtest": "speedtest.json",
        "paketsiz": "paketsiz.json"
    }
    for ad, liste in paket_kayitlari():
        yeni = []
        for dosya in liste:
            bitis = dosya.get("son_kullanma") if isinstance(dosya, dict) else None
            if bitis is not None:
                try:
                    if float(bitis) <= time.time():
                        degisen = True
                        continue
                except (TypeError, ValueError):
                    pass
            yeni.append(dosya)
        if len(yeni) != len(liste):
            liste[:] = yeni
            save(yollar[ad], liste)
    return degisen


aboneler = set(load("aboneler.json", []))

chatgpt = load("chatgpt.json", [])
whatsapp = load("whatsapp.json", [])
youtube = load("youtube.json", [])
speedtest = load("speedtest.json", [])
paketsiz = load("paketsiz.json", [])

# Yeni davet kayıtları:
# davetler.json: davet eden kullanıcı ID'si -> davet ettiği kullanıcı ID'leri
# bekleyen_davetler.json: kanallara katılmayı tamamlamamış kullanıcı -> davet eden
# davet_hedef.json: dosya almak için gereken davet sayısı
davetler = load("davetler.json", {})
bekleyen_davetler = load("bekleyen_davetler.json", {})
davet_hedef = load("davet_hedef.json", 3)
# İlk kez bu sürüm çalıştırıldığında eski zorunlu kanal listesini yalnızca bir kez temizle.
# Diğer JSON dosyalarına (aboneler, davetler ve paketler) dokunulmaz.
KANAL_SIFIRLAMA_ISARETI = ".kanal_listesi_sifirlandi_v2"
if not os.path.exists(KANAL_SIFIRLAMA_ISARETI):
    KANALLAR = []
    save("zorunlu_kanallar.json", KANALLAR)
    with open(KANAL_SIFIRLAMA_ISARETI, "w", encoding="utf-8") as f:
        f.write("ok")
else:
    KANALLAR = load("zorunlu_kanallar.json", KANALLAR)
KANAL_KONTROL_AKTIF = load("zorunlu_kanal_aktif.json", True)
if not isinstance(KANALLAR, list):
    KANALLAR = []

if not isinstance(davetler, dict):
    davetler = {}
if not isinstance(bekleyen_davetler, dict):
    bekleyen_davetler = {}
try:
    davet_hedef = max(0, int(davet_hedef))
except (TypeError, ValueError):
    davet_hedef = 3


def menu(admin=False):
    liste = [
        ["🤖 ChatGPT Paketi"],
        ["💬 WhatsApp Paketi"],
        ["▶️ YouTube Paketi"],
        ["⚡ Hız Paketi"],
        ["🌐 Paketsiz Dosya"],
        ["💾 100 GB"]
    ]

    if admin:
        liste.append(["⚙️ Admin Paneli"])

    return ReplyKeyboardMarkup(liste, resize_keyboard=True)


def davet_sayisi(uid):
    return len(set(davetler.get(str(uid), [])))


def davet_kaydet(davet_eden, yeni_kullanici):
    """Aynı Telegram hesabını birden fazla kez saymaz."""
    if not davet_eden or davet_eden == yeni_kullanici:
        return False

    davet_eden = str(davet_eden)
    yeni_kullanici = str(yeni_kullanici)

    liste = davetler.setdefault(davet_eden, [])

    if yeni_kullanici in liste:
        return False

    liste.append(yeni_kullanici)
    save("davetler.json", davetler)
    return True


async def kanal_kontrol(uid, context):
    if not KANAL_KONTROL_AKTIF:
        return True
    for kanal in KANALLAR:
        try:
            uye = await context.bot.get_chat_member(kanal, uid)

            if uye.status not in ["member", "administrator", "creator"]:
                return False

        except Exception as exc:
            logging.exception("Zorunlu kanal üyeliği kontrol edilemedi (kanal=%s, kullanıcı=%s): %s", kanal, uid, exc)
            return False

    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id

    # /start DAVET_EDEN_ID biçimindeki davet bağlantısını yakala.
    # Kullanıcı kanallara katılmayı tamamlamadıysa daveti beklemede tutarız.
    if context.args:
        try:
            davet_eden = int(context.args[0])
            if davet_eden != uid and uid not in aboneler:
                bekleyen_davetler[str(uid)] = davet_eden
                save("bekleyen_davetler.json", bekleyen_davetler)
        except (TypeError, ValueError):
            pass

    if uid != ADMIN_ID:
        if not await kanal_kontrol(uid, context):
            kanal_butonlari = []
            for i, kanal in enumerate(KANALLAR, start=1):
                kanal_adi = kanal.lstrip("@")
                kanal_butonlari.append([
                    InlineKeyboardButton(f"📢 Kanal {i}: {kanal}", url=f"https://t.me/{kanal_adi}")
                ])
            kanal_butonlari.append([InlineKeyboardButton("✅ Kontrol", callback_data="kontrol")])
            await update.message.reply_text(
                "❌ Önce aşağıdaki zorunlu kanallara katılın.",
                reply_markup=InlineKeyboardMarkup(kanal_butonlari)
            )
            return

    # Davet sayımı yalnızca daha önce kayıtlı olmayan ve kanal kontrolünü geçen
    # yeni kullanıcı için yapılır.
    if uid not in aboneler:
        davet_eden = bekleyen_davetler.pop(str(uid), None)
        if davet_eden is not None:
            davet_kaydet(davet_eden, uid)
            save("bekleyen_davetler.json", bekleyen_davetler)

        aboneler.add(uid)
        save("aboneler.json", aboneler)

    await update.message.reply_text(
        "🚀 Hoş geldiniz",
        reply_markup=menu(uid == ADMIN_ID)
    )


async def kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if await kanal_kontrol(uid, context):
        # Kanal kontrolünü geçen kullanıcıyı burada da kaydet. Böylece
        # kullanıcı ayrıca /start yazmadan Kontrol düğmesiyle tamamlayabilir.
        if uid not in aboneler:
            davet_eden = bekleyen_davetler.pop(str(uid), None)
            if davet_eden is not None:
                davet_kaydet(davet_eden, uid)
                save("bekleyen_davetler.json", bekleyen_davetler)

            aboneler.add(uid)
            save("aboneler.json", aboneler)

        await q.message.reply_text("✅ Onaylandı. Menü için /start yazın.")
    else:
        await q.message.reply_text("❌ Katılım eksik. Tüm zorunlu kanallara katıldığınızdan emin olun.")


# Kullanıcının kendine özel davet bağlantısı
async def davet_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start={uid}"
    sayi = davet_sayisi(uid)

    await update.effective_message.reply_text(
        "👥 **Davet sistemin**\n\n"
        f"🔗 Kişisel davet bağlantın:\n{link}\n\n"
        f"✅ Tamamlanan davet: {sayi}\n"
        f"🎯 Dosya almak için gereken: {davet_hedef}\n\n"
        "Davet ettiğin kişinin bağlantın üzerinden bota ilk kez girmesi "
        "ve zorunlu kanallara katılımı tamamlaması gerekir.",
        parse_mode="Markdown"
    )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return

    butonlar = [
        ["👥 Abone Sayısı"],
        ["📢 Duyuru Gönder"],
        ["📂 Dosya Yükle"],
        ["🗑️ Dosya Sil"],
        ["👥 Gerekli Davet Sayısı"],
        ["📢 Zorunlu Kanal Ayarları"],
        ["⬅️ Ana Menü"]
    ]

    await update.message.reply_text(
        "⚙️ Admin Paneli",
        reply_markup=ReplyKeyboardMarkup(butonlar, resize_keyboard=True)
    )


async def admin_islem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global davet_hedef

    uid = update.message.from_user.id
    yazi = update.message.text

    if uid != ADMIN_ID:
        return

    # Adminin kanal ekleme/silme için beklenen metin girişi
    if context.user_data.get("kanal_ekleme_modu"):
        kanal = yazi.strip()
        if not kanal.startswith("@"):
            kanal = "@" + kanal.lstrip("t.me/").strip("/")
        if len(kanal) < 2 or " " in kanal:
            await update.message.reply_text("❌ Kanal kullanıcı adını @kanal şeklinde gönder.")
            return
        if kanal not in KANALLAR:
            KANALLAR.append(kanal)
            save("zorunlu_kanallar.json", KANALLAR)
        context.user_data.pop("kanal_ekleme_modu", None)
        await update.message.reply_text(f"✅ Zorunlu kanal eklendi: {kanal}")
        return

    if context.user_data.get("kanal_silme_modu"):
        kanal = yazi.strip()
        if not kanal.startswith("@"):
            kanal = "@" + kanal.lstrip("t.me/").strip("/")
        if kanal in KANALLAR:
            KANALLAR.remove(kanal)
            save("zorunlu_kanallar.json", KANALLAR)
            await update.message.reply_text(f"✅ Kanal silindi: {kanal}")
        else:
            await update.message.reply_text("❌ Bu kanal listede bulunamadı. @kanal şeklinde gönder.")
        context.user_data.pop("kanal_silme_modu", None)
        return

    # Admin, davet hedefini değiştirmek için sayı gönderdiğinde
    if uid in davet_hedef_modu:
        try:
            yeni_hedef = int(yazi)
            if yeni_hedef < 0:
                raise ValueError

            davet_hedef = yeni_hedef
            save("davet_hedef.json", davet_hedef)
            davet_hedef_modu.remove(uid)

            await update.message.reply_text(
                f"✅ Dosya almak için gereken davet sayısı {davet_hedef} olarak ayarlandı."
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Lütfen 0 veya daha büyük bir tam sayı gönder."
            )
        return

    if yazi == "⚙️ Admin Paneli":
        await admin_panel(update, context)

    elif yazi == "👥 Abone Sayısı":
        await update.message.reply_text(f"👥 Toplam abone: {len(aboneler)}")

    elif yazi == "📢 Duyuru Gönder":
        duyuru_modu.add(uid)
        await update.message.reply_text("📢 Duyuru mesajını gönder.")

    elif yazi == "📂 Dosya Yükle":
        dosya_yukleme.add(uid)
        await update.message.reply_text("📂 Yüklemek istediğin dosyayı gönder.")

    elif yazi == "🗑️ Dosya Sil":
        await dosya_listesi(update, context)

    elif yazi == "📢 Zorunlu Kanal Ayarları":
        durum = "AÇIK" if KANAL_KONTROL_AKTIF else "KAPALI"
        liste = "\n".join(KANALLAR) if KANALLAR else "(kanal yok)"
        await update.message.reply_text(
            f"📢 Zorunlu kanal yönetimi\nDurum: {durum}\n\nMevcut kanallar:\n{liste}\n\n"
            "Komutlar:\n/kanal_ekle — kanal ekle\n/kanal_sil — kanal sil\n"
            "/kanallar — listele\n/kanal_durum — katılım kontrolünü aç/kapat"
        )

    elif yazi == "👥 Gerekli Davet Sayısı":
        davet_hedef_modu.add(uid)
        await update.message.reply_text(
            f"Şu an gereken davet sayısı: {davet_hedef}\n\n"
            "Yeni sayıyı gönder. Örnek: 5\n"
            "Davet şartını kaldırmak için 0 gönder."
        )

    elif yazi == "⬅️ Ana Menü":
        await start(update, context)


async def duyuru_gonder(update, context):
    uid = update.effective_user.id
    if uid not in duyuru_modu:
        return

    # Duyuru metin, fotoğraf, video veya belge olabilir; orijinal mesajı kopyala.
    mesaj = update.effective_message
    basarili = 0
    basarisiz = 0
    hatalar = []

    # Abone listesi boşsa başarı mesajı verme.
    hedefler = list(aboneler)
    if not hedefler:
        duyuru_modu.discard(uid)
        await mesaj.reply_text(
            "❌ Abone listesi boş görünüyor. aboneler.json dosyasını ve botun doğru klasörden çalıştığını kontrol et."
        )
        return

    for kisi in hedefler:
        try:
            await context.bot.copy_message(
                chat_id=int(kisi),
                from_chat_id=mesaj.chat_id,
                message_id=mesaj.message_id
            )
            basarili += 1
        except Exception as e:
            basarisiz += 1
            if len(hatalar) < 3:
                hatalar.append(f"{kisi}: {type(e).__name__}: {str(e)[:160]}")
        await asyncio.sleep(0.05)

    duyuru_modu.discard(uid)
    sonuc = (
        f"📢 Duyuru işlemi tamamlandı.\n"
        f"👥 Listedeki abone: {len(hedefler)}\n"
        f"✅ Gönderildi: {basarili}\n"
        f"❌ Gönderilemedi: {basarisiz}"
    )
    if hatalar:
        sonuc += "\n\nÖrnek hatalar:\n" + "\n".join(hatalar)
    await mesaj.reply_text(sonuc)


async def dosya_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id

    if uid != ADMIN_ID:
        return

    if uid not in dosya_yukleme:
        return

    if not update.message.document:
        await update.message.reply_text("❌ Lütfen dosya gönder.")
        return

    dosya = {
        "id": update.message.document.file_id,
        "ad": update.message.document.file_name
    }

    context.user_data["bekleyen_dosya"] = dosya
    dosya_yukleme.remove(uid)
    tuslar = [[InlineKeyboardButton("7 gün sonra sil", callback_data="sure_7")],
              [InlineKeyboardButton("1 ay sonra sil", callback_data="sure_30")],
              [InlineKeyboardButton("Süresiz tut", callback_data="sure_suresiz")]]
    await update.message.reply_text(
        "✅ Dosya alındı: " + str(dosya.get("ad", "Dosya")) + "\n\n"
        "Bu dosya ne zaman otomatik silinsin?",
        reply_markup=InlineKeyboardMarkup(tuslar)
    )


async def dosya_suresi_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.edit_message_text("Bu işlem yalnızca yöneticiye açık.")
        return
    dosya = context.user_data.get("bekleyen_dosya")
    if not dosya:
        await q.edit_message_text("❌ Bekleyen dosya bulunamadı. Lütfen yeniden yükle.")
        return
    if q.data == "sure_7":
        dosya["son_kullanma"] = time.time() + 7 * 24 * 60 * 60
        secim = "7 gün sonra otomatik silinecek"
    elif q.data == "sure_30":
        dosya["son_kullanma"] = time.time() + 30 * 24 * 60 * 60
        secim = "1 ay (30 gün) sonra otomatik silinecek"
    else:
        dosya.pop("son_kullanma", None)
        secim = "süresiz tutulacak"
    context.user_data["bekleyen_dosya"] = dosya
    await q.edit_message_text(
        f"✅ Süre ayarlandı: {secim}.\n\nŞimdi dosyanın hangi pakete ekleneceğini seç ve ilgili komutu gönder:\n"
        "/chatgpt  /whatsapp  /youtube  /speedtest  /paketsiz"
    )


async def paket_sec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id

    if uid != ADMIN_ID:
        return

    dosya = context.user_data.get("bekleyen_dosya")

    if not dosya:
        await update.message.reply_text("❌ Önce dosya yükle.")
        return

    komut = update.message.text

    paketler = {
        "/chatgpt": chatgpt,
        "/whatsapp": whatsapp,
        "/youtube": youtube,
        "/speedtest": speedtest,
        "/paketsiz": paketsiz
    }

    if komut not in paketler:
        return

    paketler[komut].append(dosya)

    isimler = {
        "/chatgpt": "chatgpt.json",
        "/whatsapp": "whatsapp.json",
        "/youtube": "youtube.json",
        "/speedtest": "speedtest.json",
        "/paketsiz": "paketsiz.json"
    }

    save(isimler[komut], paketler[komut])
    context.user_data.pop("bekleyen_dosya", None)

    await update.message.reply_text("✅ Dosya eklendi.")


async def dosya_listesi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    suresi_dolanlari_temizle()

    butonlar = []
    paketler = [
        ("ChatGPT", "🤖 ChatGPT", chatgpt),
        ("WhatsApp", "💬 WhatsApp", whatsapp),
        ("YouTube", "▶️ YouTube", youtube),
        ("Hiz", "⚡ Hız", speedtest),
        ("Paketsiz", "🌐 Paketsiz", paketsiz)
    ]

    for anahtar, isim, liste in paketler:
        for sira, dosya in enumerate(liste):
            butonlar.append([
                InlineKeyboardButton(
                    f"{isim} - {dosya.get('ad', 'Dosya')} ❌",
                    callback_data=f"sil_{anahtar}_{sira}"
                )
            ])

    if len(butonlar) == 0:
        await update.message.reply_text("❌ Silinecek dosya yok.")
        return

    await update.message.reply_text(
        "🗑️ Silmek istediğin dosyayı seç:",
        reply_markup=InlineKeyboardMarkup(butonlar)
    )


async def sil_buton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.from_user.id != ADMIN_ID:
        return

    veri = q.data.split("_")
    if len(veri) != 3:
        await q.edit_message_text("❌ Silme isteği tanınmadı. /start yazıp yeniden dene.")
        return
    paket = veri[1]
    try:
        sira = int(veri[2])
    except ValueError:
        await q.edit_message_text("❌ Dosya numarası geçersiz.")
        return

    secimler = {
        "ChatGPT": chatgpt,
        "WhatsApp": whatsapp,
        "YouTube": youtube,
        "Hiz": speedtest,
        "Paketsiz": paketsiz
    }

    dosya_yollari = {
        "ChatGPT": "chatgpt.json",
        "WhatsApp": "whatsapp.json",
        "YouTube": "youtube.json",
        "Hiz": "speedtest.json",
        "Paketsiz": "paketsiz.json"
    }

    liste = secimler.get(paket)
    if liste is not None and 0 <= sira < len(liste):
        liste.pop(sira)
        save(dosya_yollari[paket], liste)
        await q.edit_message_text("✅ Dosya paketten silindi.")
    else:
        await q.edit_message_text("❌ Bu dosya bulunamadı veya zaten silinmiş. /start yazıp tekrar dene.")


async def paket_gonder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    suresi_dolanlari_temizle()
    yazi = update.message.text
    chat_id = update.message.chat_id
    uid = update.message.from_user.id

    paketler = {
        "🤖 ChatGPT Paketi": chatgpt,
        "💬 WhatsApp Paketi": whatsapp,
        "▶️ YouTube Paketi": youtube,
        "⚡ Hız Paketi": speedtest,
        "🌐 Paketsiz Dosya": paketsiz,
        "💾 100 GB": paketsiz
    }

    if yazi not in paketler:
        return

    # Her dosya isteğinde zorunlu kanallar yeniden kontrol edilir.
    # Böylece eski aboneler ve daha önce dosya almış kişiler de yeni kanallara katılmadan dosya alamaz.
    if uid != ADMIN_ID and not await kanal_kontrol(uid, context):
        kanal_butonlari = []
        for i, kanal in enumerate(KANALLAR, start=1):
            kanal_adi = kanal.lstrip("@")
            kanal_butonlari.append([
                InlineKeyboardButton(f"📢 Kanal {i}: {kanal}", url=f"https://t.me/{kanal_adi}")
            ])
        kanal_butonlari.append([InlineKeyboardButton("✅ Katılımı Kontrol Et", callback_data="kontrol")])
        await update.message.reply_text(
            "🔒 Dosya alamazsın. Önce tüm zorunlu kanallara katıl, ardından kontrol et.",
            reply_markup=InlineKeyboardMarkup(kanal_butonlari)
        )
        return

    # Admin davet şartından muaftır.
    if uid != ADMIN_ID and davet_sayisi(uid) < davet_hedef:
        kalan = davet_hedef - davet_sayisi(uid)
        bot = await context.bot.get_me()
        link = f"https://t.me/{bot.username}?start={uid}"

        await update.message.reply_text(
            "🔒 Dosya almak için önce davet şartını tamamlamalısın.\n\n"
            f"👥 Tamamlanan davet: {davet_sayisi(uid)}\n"
            f"🎯 Gerekli davet: {davet_hedef}\n"
            f"📌 Kalan davet: {kalan}\n\n"
            f"🔗 Kişisel davet bağlantın:\n{link}\n\n"
            "Davet ettiğin kişinin bu bağlantıyla bota ilk kez girmesi "
            "ve zorunlu kanallara katılması gerekir."
        )
        return

    if not paketler[yazi]:
        await update.message.reply_text("❌ Bu pakette şu anda dosya yok.")
        return

    for dosya in paketler[yazi]:
        try:
            await context.bot.send_document(chat_id, dosya["id"])
            await asyncio.sleep(0.02)
        except Exception:
            pass


async def kanal_ekle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["kanal_ekleme_modu"] = True
    await update.effective_message.reply_text("Eklenecek kanalın kullanıcı adını gönder. Örnek: @kanalim")

async def kanal_sil_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["kanal_silme_modu"] = True
    await update.effective_message.reply_text("Silinecek kanalın kullanıcı adını gönder. Örnek: @kanalim")

async def kanallar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    durum = "AÇIK" if KANAL_KONTROL_AKTIF else "KAPALI"
    liste = "\n".join(KANALLAR) if KANALLAR else "(kanal yok)"
    await update.effective_message.reply_text(f"Zorunlu katılım: {durum}\n\n{liste}")

async def kanal_durum_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global KANAL_KONTROL_AKTIF
    if update.effective_user.id != ADMIN_ID:
        return
    KANAL_KONTROL_AKTIF = not KANAL_KONTROL_AKTIF
    save("zorunlu_kanal_aktif.json", KANAL_KONTROL_AKTIF)
    await update.effective_message.reply_text("✅ Zorunlu kanal katılımı " + ("AÇILDI." if KANAL_KONTROL_AKTIF else "KAPATILDI."))

# Hata mesajları Pydroid konsolunda görünsün; sorun olursa teşhis kolaylaşır.
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

if not TOKEN or TOKEN == "TOKENINI_BURAYA_YAPISTIR":
    raise RuntimeError("TOKEN satırına BotFather tokenini yapıştırmalısın.")

suresi_dolanlari_temizle()
app = Application.builder().token(TOKEN).build()

async def hata_yakala(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.exception("Bot işlem hatası:", exc_info=context.error)

app.add_error_handler(hata_yakala)


# Başlat
app.add_handler(CommandHandler("start", start))

# Kişisel davet bağlantısı
app.add_handler(CommandHandler("davet", davet_link))
app.add_handler(CommandHandler("kanal_ekle", kanal_ekle_cmd))
app.add_handler(CommandHandler("kanal_sil", kanal_sil_cmd))
app.add_handler(CommandHandler("kanallar", kanallar_cmd))
app.add_handler(CommandHandler("kanal_durum", kanal_durum_cmd))

# Kanal kontrol butonu
app.add_handler(CallbackQueryHandler(kontrol, "kontrol"))

# Paket seçme
app.add_handler(CommandHandler("chatgpt", paket_sec))
app.add_handler(CommandHandler("whatsapp", paket_sec))
app.add_handler(CommandHandler("youtube", paket_sec))
app.add_handler(CommandHandler("speedtest", paket_sec))
app.add_handler(CommandHandler("paketsiz", paket_sec))

# Dosya yükleme
app.add_handler(MessageHandler(filters.Document.ALL, dosya_al))

# Dosya saklama süresi seçimi
app.add_handler(CallbackQueryHandler(dosya_suresi_sec, pattern="^sure_(7|30|suresiz)$"))

# Silme butonu
app.add_handler(CallbackQueryHandler(sil_buton, pattern="^sil_"))


async def tum_mesajlar(update, context):
    uid = update.message.from_user.id

    if uid == ADMIN_ID and uid in duyuru_modu:
        await duyuru_gonder(update, context)
        return

    await admin_islem(update, context)
    await paket_gonder(update, context)


app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        tum_mesajlar
    )
)


print("🚀 Bot çalışıyor...")

app.run_polling(drop_pending_updates=False)

import logging
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)

# Bot tokenınızı buraya girin
BOT_TOKEN = "7052188046:AAEjFUXOwivxgifO6hgNBEebQs1VGIVOgEQ"  # Lütfen burada yeni token'ınızı kullanın

# Admin grup ID'si (admin komutlarını kullanabilmek için)
ADMIN_GROUP_ID = -1002095036242  # Admin grubunuzun chat ID'si

# Loglama ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ConversationHandler için durumlar
WAITING_FOR_AD = range(1)

# Grup/Kanal ID'lerini saklamak için dosya yolu
GROUPS_FILE = 'groups.json'

# Başlangıç mesajı
START_MESSAGE = """
🔔 **Hoş Geldiniz!**

Bu bot aracılığıyla ilanlarınızı **ücretsiz olarak** ekleyebilirsiniz.

İlan eklemek için /ilan komutunu kullanabilirsiniz.
"""

# Admin kontrolü yapan yardımcı fonksiyon
async def is_user_in_admin_group(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(ADMIN_GROUP_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        logger.error(f"Admin grup üyeliği kontrolü sırasında hata: {e}")
    return False

# /start komutunu işleyen fonksiyon
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START_MESSAGE, parse_mode='Markdown')
    return ConversationHandler.END

# /ilan komutunu işleyen fonksiyon
async def ilan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 **İlan metninizi** yazınız (detayları içerecek şekilde):",
        parse_mode='Markdown'
    )
    return WAITING_FOR_AD

# İlan metnini işleyen fonksiyon
async def handle_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ilan_metni = update.message.text.strip()
    if not ilan_metni:
        await update.message.reply_text("📄 Lütfen geçerli bir ilan metni giriniz.")
        return WAITING_FOR_AD

    user_id = update.message.from_user.id
    user = update.message.from_user
    username = user.username
    first_name = user.first_name
    last_name = user.last_name if user.last_name else ''

    if username:
        user_display = f"@{username}"
    else:
        user_display = f"{first_name} {last_name}".strip()

    # İlan verilerini formatla
    ilan_text = (
        f"**Yeni İlan:**\n\n"
        f"{ilan_metni}\n\n"
        f"**Kullanıcı:** {user_display}"
    )

    # Admin grubuna ilanı gönder
    keyboard = [
        [
            InlineKeyboardButton("✅ Onayla", callback_data=f"approve|{user_id}"),
            InlineKeyboardButton("❌ Reddet", callback_data=f"reject|{user_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=ilan_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        logger.info(f"İlan admin onayına gönderildi: {user_display}")
        await update.message.reply_text("✅ **İlanınız admin onayına gönderildi. Yeniden ilan vermek için /ilan komutunu kullanabilirsiniz.**")
    except Exception as e:
        logger.error(f"İlan admin onayına gönderilemedi: {e}")
        await update.message.reply_text("❌ **İlanınız gönderilirken bir hata oluştu. Lütfen tekrar deneyin.**")

    # Kullanıcının verilerini temizle
    context.user_data.clear()
    return ConversationHandler.END

# Callback query'leri işleyen fonksiyon
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    if len(data) != 2:
        await query.edit_message_text("❌ **Geçersiz işlem.**")
        logger.warning("Geçersiz callback data yapısı.")
        return

    action, user_id_str = data
    try:
        user_id = int(user_id_str)
    except ValueError:
        await query.edit_message_text("❌ **Geçersiz kullanıcı ID'si.**")
        logger.error("Kullanıcı ID'si integer olarak dönüştürülemedi.")
        return

    if action == "approve":
        # İlanı public gruplara/kanallara gönder
        message = query.message

        ilan_text = message.text if message.text else "📄 **Açıklama bulunamadı.**"

        if ilan_text:
            # İlan metnine ek metni ekleyin
            ekstra_metin = "\n\nÜcretsiz ilan vermek için @Trisilanvermebot"
            ilan_text += ekstra_metin

            # Grupları/kanalları yükle
            groups = load_groups()

            if not groups:
                await query.edit_message_text("❌ **Hiçbir hedef grup veya kanal eklenmemiş.**")
                logger.warning("Onaylanmış ilan göndermek için hedef grup veya kanal yok.")
                return

            send_errors = []
            for group_id in groups:
                try:
                    await context.bot.send_message(
                        chat_id=group_id,
                        text=ilan_text,
                        parse_mode='Markdown'
                    )
                    logger.info(f"İlan {group_id} ID'li gruba/kanala gönderildi.")
                except Exception as e:
                    logger.error(f"İlan {group_id} ID'li gruba/kanala gönderilemedi: {e}")
                    send_errors.append(group_id)

            if send_errors:
                await query.edit_message_text(f"✅ **İlan onaylandı ve gönderildi. Ancak bazı gruplara/kanallara gönderilemedi.**\n\nGönderilemeyen ID'ler: {send_errors}")
            else:
                await query.edit_message_text("✅ **İlan onaylandı ve tüm hedef gruplara/kanallara gönderildi.**")
        else:
            await query.edit_message_text("❌ **İlan onaylandı ancak ilan metni bulunamadı.**")
            logger.warning("İlan onaylandı ancak metin eksik.")
    elif action == "reject":
        # İlanı reddet
        try:
            # İlan mesajının metnini güncelle
            await query.edit_message_text("❌ **İlan reddedildi.**")
            logger.info("İlan reddedildi.")

            # Kullanıcıya özel mesaj gönder
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ **İlanınız reddedildi. Lütfen ilan metninizi tekrar giriniz.**"
            )
            logger.info(f"İlan reddedildi ve kullanıcıya bildirildi: User ID {user_id}")
        except Exception as e:
            logger.error(f"Kullanıcıya mesaj gönderilemedi: {e}")
    else:
        await query.edit_message_text("❌ **Geçersiz işlem.**")
        logger.warning("Geçersiz işlem denendi.")

# /yap komutunu işleyen fonksiyon
async def yap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if not await is_user_in_admin_group(context, user_id):
        await update.message.reply_text("❌ **Bu komutu kullanma yetkiniz yok.**")
        return

    args = context.args
    if not args:
        await update.message.reply_text("ℹ️ **Lütfen eklemek istediğiniz grup veya kanalın ID'sini belirtin.**\n\nÖrnek kullanım: /yap -1001234567890")
        return

    group_id_str = args[0]
    if not group_id_str.startswith("-100") or not group_id_str[1:].isdigit():
        await update.message.reply_text("❌ **Geçersiz grup veya kanal ID'si.**\n\nID'nin -100 ile başlaması ve ardından rakamlar gelmesi gerekmektedir.")
        return

    group_id = int(group_id_str)
    groups = load_groups()

    if group_id in groups:
        await update.message.reply_text("ℹ️ **Bu grup veya kanal zaten eklenmiş.**")
        return

    groups.append(group_id)
    save_groups(groups)

    await update.message.reply_text(f"✅ **Grup/Kanal ID'si {group_id} başarıyla eklendi.**")
    logger.info(f"Yeni grup/kanal eklendi: {group_id}")

# /kaldir komutunu işleyen fonksiyon (grupları kaldırmak için)
async def kaldir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if not await is_user_in_admin_group(context, user_id):
        await update.message.reply_text("❌ **Bu komutu kullanma yetkiniz yok.**")
        return

    args = context.args
    if not args:
        await update.message.reply_text("ℹ️ **Lütfen silmek istediğiniz grup veya kanalın ID'sini belirtin.**\n\nÖrnek kullanım: /kaldir -1001234567890")
        return

    group_id_str = args[0]
    if not group_id_str.startswith("-100") or not group_id_str[1:].isdigit():
        await update.message.reply_text("❌ **Geçersiz grup veya kanal ID'si.**\n\nID'nin -100 ile başlaması ve ardından rakamlar gelmesi gerekmektedir.")
        return

    group_id = int(group_id_str)
    groups = load_groups()

    if group_id not in groups:
        await update.message.reply_text("ℹ️ **Bu grup veya kanal listede bulunmuyor.**")
        return

    groups.remove(group_id)
    save_groups(groups)

    await update.message.reply_text(f"✅ **Grup/Kanal ID'si {group_id} başarıyla kaldırıldı.**")
    logger.info(f"Grup/kanal kaldırıldı: {group_id}")

# Grupları yükleyen fonksiyon
def load_groups():
    if not os.path.exists(GROUPS_FILE):
        return []
    with open(GROUPS_FILE, 'r') as f:
        try:
            groups = json.load(f)
            if isinstance(groups, list):
                return groups
            else:
                logger.error("groups.json dosyası geçerli bir liste içermiyor.")
                return []
        except json.JSONDecodeError:
            logger.error("groups.json dosyası okunamadı veya bozuk.")
            return []

# Grupları kaydeden fonksiyon
def save_groups(groups):
    try:
        with open(GROUPS_FILE, 'w') as f:
            json.dump(groups, f, indent=4)
    except Exception as e:
        logger.error(f"groups.json dosyasına yazılırken hata oluştu: {e}")

# /goster komutunu işleyen fonksiyon (mevcut grupları listelemek için)
async def goster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if not await is_user_in_admin_group(context, user_id):
        await update.message.reply_text("❌ **Bu komutu kullanma yetkiniz yok.**")
        return

    groups = load_groups()
    if not groups:
        await update.message.reply_text("ℹ️ **Henüz hiçbir grup veya kanal eklenmemiş.**")
        return

    groups_text = "\n".join([str(gid) for gid in groups])
    await update.message.reply_text(f"📋 **Eklenmiş Grup/Kanal ID'leri:**\n{groups_text}")

# /getid komutunu işleyen fonksiyon (grup ID'si almak için kullanılabilir)
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"📢 **Chat ID:** {chat_id}")

def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_NEW_BOT_TOKEN_HERE":
        logger.error("Lütfen BOT_TOKEN'ı tanımlayın.")
        return

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # ConversationHandler'ı oluştur
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('ilan', ilan_start)],
        states={
            WAITING_FOR_AD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ad)],
        },
        fallbacks=[CommandHandler('start', start)],
    )

    # Handler'ları ekle
    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CommandHandler("yap", yap))        # /ekle yerine /yap
    application.add_handler(CommandHandler("kaldir", kaldir))  # /sil yerine /kaldir
    application.add_handler(CommandHandler("goster", goster))  # /liste yerine /goster
    application.add_handler(CommandHandler("getid", get_id))   # Grup ID'si almak için

    # Botu çalıştır
    application.run_polling()

if __name__ == '__main__':
    main()

import os
import uuid
from pytube import YouTube
from pydub import AudioSegment, effects
from tqdm import tqdm
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
import logging

# Log ayarları
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# .env'den token yükle
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Oturumlar
user_sessions = {}

# Efekt seçenekleri
effect_options = {
    "8D": "8d",
    "Bass Boost": "bass",
    "Volume Boost": "volume",
    "Nightcore": "nightcore",
    "Echo": "echo",
    "Slowed + Reverb": "slowed_reverb",
}

# Klasörleri oluştur
os.makedirs("downloads", exist_ok=True)

# 🎞 YouTube'dan ses indir
def download_audio(url, user_id, kbps="192"):
    yt = YouTube(url)
    temp_path = os.path.join("downloads", f"{user_id}_{uuid.uuid4()}.mp3")
    yt.streams.filter(only_audio=True).first().download(filename=temp_path)
    audio = AudioSegment.from_file(temp_path)
    audio.export(temp_path, format="mp3", bitrate=f"{kbps}k")
    return temp_path, yt.title

# 📽 YouTube'dan video indir
def download_video(url, user_id, resolution="720p"):
    yt = YouTube(url)
    stream = yt.streams.filter(progressive=True, file_extension="mp4", res=resolution).first()
    if not stream:
        stream = yt.streams.get_highest_resolution()
    file_path = os.path.join("downloads", f"{user_id}_{uuid.uuid4()}.mp4")
    stream.download(filename=file_path)
    return file_path, yt.title

# 🎚 Efekt uygula
def apply_effects_with_progress(input_path, selected_effects, song_title):
    audio = AudioSegment.from_file(input_path)
    output_effects = []

    with tqdm(total=len(selected_effects), desc="Efektler Uygulanıyor", unit="effect") as progress:
        for effect in selected_effects:
            if effect == "8D":
                audio = effects.normalize(audio.pan(-0.5))
            elif effect == "Bass Boost":
                audio = audio.low_pass_filter(100).apply_gain(8)
            elif effect == "Volume Boost":
                audio = audio + 5
            elif effect == "Nightcore":
                audio = audio.speedup(playback_speed=1.25)
            elif effect == "Echo":
                echo = audio[-1000:].fade_in(200).fade_out(200)
                audio = audio.append(echo, crossfade=300)
            elif effect == "Slowed + Reverb":
                audio = audio.speedup(playback_speed=0.8)
            output_effects.append(effect)
            progress.update(1)

    output_name = f"{song_title}_{'-'.join(output_effects)}.mp3"
    output_path = os.path.join("downloads", output_name.replace(" ", "_"))
    audio.export(output_path, format="mp3")
    return output_path

# 🚀 Başlat komutu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions[update.effective_user.id] = {
        "urls": [],
        "audio_video": None,
        "resolution": "720p",
        "kbps": "192",
        "effects": []
    }
    await update.message.reply_text(
        "🎵 Merhaba! YouTube link(ler)ini gönder:\n"
        "`https://youtu.be/...`\n\n"
        "Çoklu URL için her satıra bir link yaz.",
        parse_mode="Markdown"
    )

# 🔗 Kullanıcı link gönderirse
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    urls = [line.strip() for line in update.message.text.splitlines() if line.strip().startswith("http")]
    if not urls:
        return await update.message.reply_text("❌ Geçerli link(ler) gönder.")
    user_sessions[user_id]["urls"] = urls
    keyboard = [
        [InlineKeyboardButton("🎧 MP3", callback_data="audio"),
         InlineKeyboardButton("📹 MP4", callback_data="video")],
    ]
    await update.message.reply_text("🔽 Format seç:", reply_markup=InlineKeyboardMarkup(keyboard))

# 🎚 Format seçimi
async def format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_sessions[user_id]["audio_video"] = query.data

    if query.data == "video":
        keyboard = [[InlineKeyboardButton(res, callback_data=f"res_{res}")] for res in ["144p", "360p", "720p", "1080p"]]
        await query.edit_message_text("📺 Çözünürlük seç:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        keyboard = [[InlineKeyboardButton(kbps, callback_data=f"kbps_{kbps}")] for kbps in ["128", "192", "256", "320"]]
        await query.edit_message_text("🔊 Ses kalitesi seç (kbps):", reply_markup=InlineKeyboardMarkup(keyboard))

# 🎚 Kbps veya çözünürlük seçimi
async def quality_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("res_"):
        res = query.data.split("_")[1]
        user_sessions[user_id]["resolution"] = res
    elif query.data.startswith("kbps_"):
        kbps = query.data.split("_")[1]
        user_sessions[user_id]["kbps"] = kbps

    keyboard = [[InlineKeyboardButton(name, callback_data=f"fx_{name}")] for name in effect_options]
    keyboard.append([InlineKeyboardButton("✅ Uygula ve İndir", callback_data="apply_effects")])
    await query.edit_message_text("🎛 Efekt seç (çoklu seçim mümkün):", reply_markup=InlineKeyboardMarkup(keyboard))

# 🎚 Efekt seçimi
async def effect_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    effect = query.data.split("_", 1)[1]

    if effect in user_sessions[user_id]["effects"]:
        user_sessions[user_id]["effects"].remove(effect)
    else:
        user_sessions[user_id]["effects"].append(effect)

    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(name + (" ✅" if name in user_sessions[user_id]["effects"] else ""), callback_data=f"fx_{name}")]
             for name in effect_options] +
            [[InlineKeyboardButton("✅ Uygula ve İndir", callback_data="apply_effects")]]
        )
    )

# 🎯 Uygula ve İndir
async def apply_and_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    session = user_sessions.get(user_id)

    if not session or not session["urls"]:
        return await query.edit_message_text("❌ Hata: URL bulunamadı.")

    for url in session["urls"]:
        if session["audio_video"] == "video":
            file_path, title = download_video(url, user_id, session["resolution"])
            await context.bot.send_video(chat_id=user_id, video=open(file_path, "rb"), caption=title)
        else:
            file_path, title = download_audio(url, user_id, session["kbps"])
            if session["effects"]:
                file_path = apply_effects_with_progress(file_path, session["effects"], title)
            await context.bot.send_audio(chat_id=user_id, audio=open(file_path, "rb"), caption=title)

    await query.edit_message_text("✅ Dosya(lar) hazır!")

# 🔌 Botu çalıştır
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(format_selection, pattern="^(audio|video)$"))
    app.add_handler(CallbackQueryHandler(quality_selected, pattern="^(res|kbps)_"))
    app.add_handler(CallbackQueryHandler(effect_selection, pattern="^fx_"))
    app.add_handler(CallbackQueryHandler(apply_and_download, pattern="^apply_effects$"))

    print("✅ Bot çalışıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()

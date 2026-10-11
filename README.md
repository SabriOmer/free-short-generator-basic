# Shorts Bot

Gemini + (edge-tts / Gemini TTS) + FFmpeg ile otomatik YouTube Shorts uretir.

## Kurulum
1. Python 3.10+ ve FFmpeg kur (`winget install Gyan.FFmpeg`)
2. `pip install -r requirements.txt`
3. API anahtarlarini ortam degiskeni olarak ayarla (koda ASLA yazma):
   - `setx GEMINI_API_KEY "..."`
   - `setx PIXABAY_API_KEY "..."` (istege bagli)

## Kullanim
- Arayuz: `python shorts_gui.py`
- Komut satiri: `python shorts_bot.py "video konusu"`

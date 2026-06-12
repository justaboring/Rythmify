import asyncio
import yt_dlp
from config import Config

async def main():
    loop = asyncio.get_event_loop()
    ytdl = yt_dlp.YoutubeDL(Config.YTDL_FORMAT_OPTIONS)
    try:
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info('https://www.youtube.com/watch?v=NnkrnP67gRg', download=False))
        formats = data.get('formats', [])
        playable = [f for f in formats if f.get('acodec') != 'none']
        print(f'SUCCESS! Title: {data.get("title")} | Audio Formats: {len(playable)}')
    except Exception as e:
        print('FAIL:', e)

asyncio.run(main())

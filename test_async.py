import asyncio
import yt_dlp

async def main():
    loop = asyncio.get_event_loop()
    ydl_opts = {'extractor_args': {'youtube': {'player_client': ['ios', 'android']}}}

    ytdl = yt_dlp.YoutubeDL(ydl_opts)
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info('https://www.youtube.com/watch?v=NnkrnP67gRg', download=False))
    formats = data.get('formats', [])
    print(f'SUCCESS! Title: {data.get("title")} | Available formats: {len(formats)}')
    
asyncio.run(main())

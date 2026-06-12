import asyncio
import yt_dlp
from config import Config
import concurrent.futures

def fetch(url):
    ytdl = yt_dlp.YoutubeDL(Config.YTDL_FORMAT_OPTIONS)
    return ytdl.extract_info(url, download=False)

async def main():
    loop = asyncio.get_event_loop()
    with concurrent.futures.ProcessPoolExecutor() as pool:
        data = await loop.run_in_executor(pool, fetch, 'https://www.youtube.com/watch?v=NnkrnP67gRg')
        print('SUCCESS! Title:', data.get('title'))

if __name__ == '__main__':
    asyncio.run(main())

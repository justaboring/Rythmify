import yt_dlp
ydl_opts = {'extractor_args': {'youtube': {'player_client': ['tv', 'web']}}}
ytdl = yt_dlp.YoutubeDL(ydl_opts)
data = ytdl.extract_info('https://www.youtube.com/watch?v=NnkrnP67gRg', download=False)
formats = data.get('formats', [])
playable = [f for f in formats if f.get('acodec') != 'none']
print(f'Audio Formats: {len(playable)}')

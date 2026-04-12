import yt_dlp

ydl_opts = {'extractor_args': {'youtube': {'player_client': ['tv', 'web']}}}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info('https://www.youtube.com/watch?v=D2kYW93T0dI', download=False)
    print('SUCCESS! Title:', info.get('title'))

# an utility tool to downoald YouTube video transcript file and audio source for local analysis. If only transcript is needed, a official API download should be prefered

#Usage/requirements:
#pip install yt-dlp
# must have Firefox browser for authentication/anti bot detection
#if video is private or age restricted, firefox must be logged into Youtube account eligible to watch the video

#video url is stored into url variable, and output will be saved into OUTPUT_DIR FOLDER

import subprocess
import json
import os

url = 'https://www.youtube.com/watch?v=5sZbjauqa-s'

def get_video_metadata(url):
    print(f"\n Checking metadata for: {url}")
    try:
        # First, try to get cookies from a browser (e.g., Chrome)
        print(" Attempting to extract cookies from browser...")
        result = subprocess.run(
            ['yt-dlp', '--cookies-from-browser', 'firefox','--remote-components', 'ejs:github', '--dump-json', url],
            capture_output=True,
            text=True,
            check=True
        )
        print(" Successfully extracted cookies from browser.")
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print("could not extract data")


metadata = get_video_metadata(url)

def select_optimal_formats(metadata):
    best_audio_format_id = None
    best_audio_quality = -1

    for format_entry in metadata.get('formats', []):
        vcodec = format_entry.get('vcodec')
        acodec = format_entry.get('acodec')
        format_id = format_entry.get('format_id')

        if acodec and acodec != 'none' and (not vcodec or vcodec == 'none'):
            abr = format_entry.get('abr', 0)
            # Fallback to tbr if abr is not available or 0
            quality = abr if abr > 0 else format_entry.get('tbr', 0)
            if quality > best_audio_quality:
                best_audio_quality = quality
                best_audio_format_id = format_id
    print(f"Selected audio format ID: {best_audio_format_id}")
    return best_audio_format_id


OUTPUT_DIR = "downloads"


def download_channels(url, title, video_id):
    base_name = os.path.join(OUTPUT_DIR, f"{video_id}_{title.replace('/', '_')}")

    audio_format_id = select_optimal_formats(metadata)
    common_yt_dlp_args = ['--remote-components', 'ejs:github']

    audio_command = [
        'yt-dlp',
        '--cookies-from-browser',
        'firefox',
        '-f', audio_format_id,
        url,
        '-o', f"{base_name}_audio_only.%(ext)s"
    ] + common_yt_dlp_args if audio_format_id else None

    transcript_command = [
        'yt-dlp',
        '--cookies-from-browser',
        'firefox',
        '--skip-download',
        '--write-auto-sub',
        '--sub-lang', 'en',
        '--sub-format', 'srt',
        url,
        '-o', f"{base_name}_transcript.%(ext)s"
    ] + common_yt_dlp_args
    try:

        if audio_command:
            print("\n--- Running audio download command ---")
            audio_result = subprocess.run(audio_command, check=True, capture_output=True, text=True)
            print(audio_result.stdout)
            print(audio_result.stderr)
        else:
            print("\n--- Skipping audio download due to no suitable format ---")

        print("\n--- Running transcript download command ---")
        transcript_result = subprocess.run(transcript_command, check=True, capture_output=True, text=True)
        print(transcript_result.stdout)
        print(transcript_result.stderr)

        print(f"Video, Audio, and Transcript downloaded to {OUTPUT_DIR}/")
    except subprocess.CalledProcessError as e:
        print(f"Download failed for {title}: {e}")
        print(f"yt-dlp stdout: {e.stdout}")
        print(f"yt-dlp stderr: {e.stderr}")
    




video_title = metadata.get('title', 'untitled').strip()
video_id = metadata.get('id', 'unknown')
download_channels(url, video_title, video_id)

#regenerates transcripts for audio files; useful mostlyfor non-youtube videos
#that do not have autoprovidede captions

#pip install faster-whisper
#suggested to run on colab or device supporting cuda (swap decice='cuda')
#as otherwise can be really slow (about video original length)

import glob
import os
from faster_whisper import WhisperModel

model = WhisperModel("medium", device="cpu")


# Helper function
def format_timestamp(seconds):
    milliseconds = int(seconds * 1000)

    hours = milliseconds // 3600000
    milliseconds %= 3600000

    minutes = milliseconds // 60000
    milliseconds %= 60000

    secs = milliseconds // 1000
    milliseconds %= 1000

    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"
files = glob.glob("*.mp4") + glob.glob("*.m4a") + glob.glob("*.wav")
for file in files:
    out = "whisper_"+file+".srt"
    print(out)
    if os.path.exists(out):
        print(f" Skipping: {out} (SRT already exists)")
        continue
    print(f" Transcribing: {out}")

    segments, info = model.transcribe(
    file,
    language="en"
    )

    with open(out, "w", encoding="utf-8") as f:
        for i, segment in enumerate(segments, start=1):

            start = format_timestamp(segment.start)
            end = format_timestamp(segment.end)

            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(segment.text.strip() + "\n\n")







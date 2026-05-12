#attemt to improve existing transcript quality with gemini api

#pip install -U google-genai
#pip install pysrt
#api keys can be set in aistudio.google.com

import glob
import json
import pysrt
import os
import math
import re
import time

from google import genai
from google.genai import types


def remove_repetitions(text):
    return re.sub(r"\b(\w+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)

FILLERS = [
    r"\bso\b", r"\buh\b",r"\bhere\b", r"\bvery\b", r"\blike\b", r"\bum\b", r"\bwill\b",
    r"\breallyl\b", r"\bactually\b",  r"\bokay\b", r"\bof course\b" , r"\bstill\b", r"\bsimply\b",
    r"\bprobablly\b" , r"\bquite\b" , r"\bkind of\b", r"\bsort of\b",
    r"\bbasically\b", r"\busually\b", r"\bobviously\b", r"\bdefinitely\b", r"\bI mean\b"
]

def remove_fillers(text):
    pattern = re.compile("|".join(FILLERS), re.IGNORECASE)
    return pattern.sub("", text)


def get_gemini_corrections(srt):
    base_name = os.path.basename(srt)
    subs = pysrt.open(srt)

    all_text = [sub.text for sub in subs]
    clean_string = "\n".join(all_text)
    out = "gemini_"+base_name # possibly add path here
    if os.path.exists(out):
        print(f"{out} already exists, skipping")
        return

    prompt = f"Review this chess video transcript and identify potential misspellings. Focus on proper names likely to be known chess players or other chess related terms. Also try to identify misspelled homophones based on context (like 'night' likely means 'knight' piece in chess transcript). Transcript: {clean_string}"

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema={
                "type": "OBJECT",
                "properties": {
                    "corrections": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "wrong": {"type": "STRING"},
                                "right": {"type": "STRING"}
                            }
                        }
                    }
                }
            }
        )
    )

    print(response.text)

    corrections = json.loads(response.text).get('corrections', [])
    correction_map = {item['wrong']: item['right'] for item in corrections}

    for sub in subs:
        for wrong, right in correction_map.items():
            pattern = r'\b{}\b'.format(re.escape(wrong))
            sub.text = re.sub(pattern, right, sub.text)
            sub.text = remove_repetitions(sub.text)
            sub.text = remove_fillers(sub.text)

    subs.save(out)



client = genai.Client(api_key="PUT YOUR API KEY HERE")
files = glob.glob("*.srt")
for file in files:
      print(f"Processing {file}...")
      get_gemini_corrections(file)
      time.sleep(10)






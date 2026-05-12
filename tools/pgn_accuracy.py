#rename fround truth file to "a.pgn"
#and generated file to "b.pgn"
#code compares both files and theit commenatary matches.

#pip install -U google-genai
#pip install pysrt


import chess.pgn
import re
import json


def extract_specific_comment(full_comment, target):

    if not full_comment or target not in full_comment:
        return ""


    pattern = rf"(?:\[|%){re.escape(target)}\]?(.*?)(?=\[|%|$)"
    match = re.search(pattern, full_comment, re.DOTALL)
    
    return match.group(1).strip() if match else ""

print(extract_specific_comment("[person1] hi all %person2 hello to you to", "person1"))

def collect_positions(node, board, positions, target_person=None):
  for variation in node.variations:
    board.push(variation.move)

        # Use shfen (Simplified FEN) to handle transpositions correctly
        # ignores move clocks but keeps turn/castling/ep
    fen = board.epd() 

    raw_comment = variation.comment.strip() if variation.comment else ""
    if target_person:
        comment = extract_specific_comment(raw_comment, target_person)
    else:
        comment = raw_comment

    if fen not in positions or (not positions[fen] and comment):
        positions[fen] = comment

    collect_positions(variation, board, positions, target_person)

    board.pop()


def extract_all_positions(pgn_file, target_person=None):
    positions = {} 

    with open(pgn_file, encoding="utf-8") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break

            board = game.board()
            positions[board.epd()] = ""

            collect_positions(game, board, positions, target_person)
            
    return positions

def collect_lines(node, current_line, lines, type):
    if not node.variations:
        lines.add(tuple(current_line))
        return

    for variation in node.variations:
        if type:
          move_data = {
            "uci": variation.move.uci(),
            "comment": variation.comment.strip()
            }
        else:
          move_data = {
            "uci": variation.move.uci(),
            "comment": extract_specific_comment(variation.comment.strip(), "Source")
            }

        current_line.append(tuple(move_data.items()))

        collect_lines(variation, current_line, lines, type)

        current_line.pop()


def extract_variations(pgn_file, type):
    lines = set()

    with open(pgn_file, encoding="utf-8") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break

            collect_lines(game, [], lines, type)

    return lines


a = extract_all_positions("a.pgn")
b = extract_all_positions("b.pgn", "Source")


print(a)
print(b)

master_keys = a.keys()
attempt_keys = b.keys()

only_a = master_keys - attempt_keys  
only_b = attempt_keys - master_keys  
both = master_keys & attempt_keys  

coverage = len(both) / len(a) if a else 0
precision = len(both) / len(b) if b else 0

print ("_________________________________________")


print(len(a))

print("coverage", coverage)
print("precision", precision)

print ("_________________________________________")

#using analogy where original - master, recreated = student recall
def extract_audit_paragraphs(master_map, attempt_map):
    """
    master_map: {epd: comment} (Source of Truth)
    attempt_map: {epd: comment} (Student Attempt)
    """
    shared_epds = master_map.keys() & attempt_map.keys()
    

    master_comments = [
        master_map[epd] for epd in shared_epds if master_map[epd].strip()
    ]
    master_paragraph = " ".join(master_comments)
    

    attempt_comments = [
        comm for comm in attempt_map.values() if comm.strip()
    ]
    attempt_paragraph = " ".join(attempt_comments)
    
    return master_paragraph, attempt_paragraph


master_paragraph, attempt_paragraph = extract_audit_paragraphs(a, b)
print("Master Paragraph:", master_paragraph)
print("Attempt Paragraph:", attempt_paragraph)


from google import genai
from google.genai import types

response_schema = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "fact": {
                "type": "string", 
                "description": "A distinct claim or evaluation found ONLY in the MASTER TEXT."
            },
            "present": {
                "type": "boolean",
                "description": "True if the STUDENT TEXT captures this specific idea, even if phrased differently (e.g., 'c5' vs 'Sicilian')."
            }
        },
        "required": ["fact", "present"]
    }
}



client = genai.Client(api_key="put your api key here",#gemini
                        http_options=types.HttpOptions(
                        retry_options=types.HttpRetryOptions(
                        attempts=7,
                        http_status_codes=[503, 504, 502]
                        )
                      )
                      )


MODEL_ID = "gemini-2.5-flash"

prompt = f"""
You are a Chess Knowledge Auditor. 

RULES:
1. STRICT SOURCE: Extract facts ONLY from the MASTER TEXT. Do not include ideas found only in the STUDENT TEXT.
2. SEMANTIC MATCHING: Mark 'present: true' if the Student understands the CORE IDEA. 
   - Example: If Master says "g4 allows bad knight exchange" and Student says "g4 is played to trade the bad knight," this is a MATCH.
3. CHESS SYMBOLS: Treat symbols (??, !!) and evaluations (+-, -+) as equivalent to their text meanings (Blunder, Great Move, White is winning).
4. POLARITY: If the Master says "White is better" and Student text says only "Black is better," this is NOT a match.

MASTER TEXT: "{master_paragraph}"
STUDENT TEXT: "{attempt_paragraph}"

Respond ONLY with a JSON list:
[
  {{"fact": "...", "present": true/false}},
  ...
]
"""

response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema
        )
    )

print(response)

data = json.loads(response.text)
total_facts = len(data)
true_facts = sum(item['present'] for item in data)

agreement_score = (true_facts / total_facts * 100) if total_facts > 0 else 100
print(f"Total Facts: {total_facts}")
print(f"Agreement Score: {agreement_score:.2f}%")

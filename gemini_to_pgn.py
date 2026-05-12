#code attempts to generate valid .pgn file from provided transcript .srt file
#currently, multiple files processing isn't implemented,
#to use, rename desired transcript in this folder to "g1.srt" and run the file 

#pip install -U google-genai
#pip install pysrt

client = genai.Client(api_key="put your api key here",#gemini
                        http_options=types.HttpOptions(
                        retry_options=types.HttpRetryOptions(
                        attempts=7, #auto retry on 503 server error
                        http_status_codes=[503, 504, 502]
                        )
                      )
                      )
MODEL_ID = "gemini-3-flash-preview"

subs = pysrt.open("g1.srt")


#TRANSCRIPT = subs.text # use instead, if timestamps are still required


subs = pysrt.open("g1.srt")
TRANSCRIPT = subs.text
f = open('g1.srt')
TRANSCRIPT = f.read()

move_extraction_schema = {
    "type": "OBJECT",
    "properties": {
        "action": {"type": "STRING", "enum": ["MOVE_BATCH", "JUMP_AND_VARIATION", "DONE"]},
        "jump_target_san": {
            "type": "STRING",
            "description": "The SAN of the move from CURRENT variation, we are jumping back to change in next batch. The NEW first move that starts new variation WE JUMPED INTO should always come in MOVES list. Use '4. d4' or '4... d5' to identify move and its index."
        },
        "moves": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "san": {"type": "STRING",
                            "description": "Only add SAN notation here, do not include move number here"},
                    "transcript_comment": {"type": "STRING", "description": "Actual words used to describe position/future ideas from the presenter."},
                    "ai_evaluation": {"type": "STRING", "description": "Your internal feedback or analysis of move quality/skill level."}
                }
            }
        },
        "source_quote": {"type": "STRING",
                         "description":"part of text, where last actions (moves or jumpback) was extracted from. NEVER return EARLIER part of file than what Last Found Text already marks."}
    }
}

chess_cache = client.caches.create(
    model=MODEL_ID,
    config=types.CreateCachedContentConfig(
        display_name="chess_analysis_v3",
        system_instruction=(
            "You are a chess expert. Analyze the transcript to find the next (batch of consequtive) moves played IN ORDER they appear in file. Always provide the source sentence used as a 'bookmark' from where next extractor could continue. NEVER return a source that appears EARLIER in transcript than current bookmark/last found text. You can return current line again if retrying after errors. "),
        contents=[TRANSCRIPT],
        ttl="3600s"
    )
)
print(f"Cache created: {chess_cache.name}")


def get_moves(pgneditor, current_bookmark, jumpback = False, err_move = None, many_tries = False):

  reminder =""
  if(jumpback):
    """ Last action was taking some moves back, if current bookmark still has more moves
    return these now without advancing bookmark. Otherwise look into next section as usual.
    Note! after jumpin back, board state might be identical to previously analysed state. Use LAST FOUND TEXT to identify, where we are in analysis, and continue move
    extraction from there.
    """
  problems =""
  if (err_move):
    move_num = editor.board.fullmove_number
    turn = "White" if editor.board.turn == chess.WHITE else "Black"

    if(many_tries):
      problems = f"""
      !!!{turn} {move_num} move {err_move} was invalid. The transcript video is targeted for visual audience, so
      some moves might actually be not pronounced explicidly or there might be a typo in audio to notation convertion.
      YOU MUST **SKIP**: as the transcript seems  broken/unclear, use 'JUMP_AND_VARIATION' to skip this move and find the next variation starting point from the text.
      """
    else:
      problems = f"""
      !!!{turn} {move_num} move {err_move} was invalid. YOU MUST **RETRY** new MOVE_BATCH starting from erroring move. Based on context (known opening theory) or looking the provided legal move list at given position.
      Consider that  transcript is made automatically from audio, and poor spelling/accents may give slightly wrong result. Also it is possible that presenter was confused with black's perspective, changing a1 to h8 etc.
      """

  prompt = f"""
      CURRENT STATE:
      - Current Board State: {pgneditor.show_board()}
      - Full Game History: {pgneditor.show_moves()}
      - Last Found Text: "{current_bookmark}"

      {problems}

      TASK:
      Identify the next moves. Note: The commentator may JUMP BACK to a previous position
      or discuss a "what if" variation. The goal is to find ALL chess variations
      discussed within the transcript in same order as they appear in source file.

      INSTRUCTIONS:
      1. If the moves follow the current board, use action "MOVE_BATCH".
         If many moves are listed in a row, return them is single batch, and only add commentary to last move, where annotator actually includes relevant information.
         Otherwise keep comment fields empty.
         Return ONLY SAN move numbers here, WITHOUT move number prefix. You do NOT need to include check or checkmate symbols (+, #, ++, 'mate' etc.)
      2. If the commentator jumps back to an earlier position, use action "JUMP_AND_VARIATION".
         Identify which move in current batch commentator is going back to.
         The NEW move starting next variation (replacing old move on board) can be returned in MOVES list (SAN only, no move numbers in actual forward going variations).
         For example, if game started analysis with 1.e4 e5 2.Nf3 Nc6 ... and annotator wants to analyse sicilian (1.e4 c5) next,
         return 'JUMP_AND_VARIATION', 'jump_target_san': '1... e5', to replace e5 and  start new variation with 'moves': [{{'san': 'c5'}}]
      3. After reaching END OF transcript file, and there are NO more moves discussed, return action "DONE"

      {reminder}

      """

  response = client.models.generate_content(
          model=MODEL_ID,
          contents=prompt,
          config=types.GenerateContentConfig(
              cached_content=chess_cache.name,
              response_mime_type="application/json",
              response_schema=move_extraction_schema
          )
      )
  print(prompt)
  print(response)
  data = json.loads(response.text)
  return data

import re
class PGNEditor:
    def __init__(self):
        self.game = chess.pgn.Game()
        self.node = self.game
        self.board = self.game.board()

    def show_board(self):
        board_ascii = str(self.board)
        fen = self.board.fen()
        return f"\n{board_ascii}\nFEN: {fen}"

    def show_moves(self):
        moves = []
        node = self.node
        while node.parent is not None:
            moves.append(node.move)
            node = node.parent
        moves.reverse()
        board = self.game.board()

        move_number = 1
        output_lines = ["Current line:"]

        i = 0
        while i < len(moves):
            white_move = board.san(moves[i])
            board.push(moves[i])

            line = f"{move_number}. {white_move}"
            # If there's a black move, add it
            if i + 1 < len(moves):
                black_move = board.san(moves[i + 1])
                board.push(moves[i + 1])
                line += f" {black_move}"
                i += 2
            else:
                i += 1

            output_lines.append(line)
            move_number += 1

        return "\n".join(output_lines)

    def show_legal_moves(self):
        legal_moves = [self.board.san(m) for m in self.board.legal_moves]
        return " ".join(legal_moves)

    def add_move(self, move, comment = None):
        try:
            move = self.board.parse_san(move)
        except ValueError:
            print(f"Invalid move: {move}")
            return False
        self.node = self.node.add_variation(move)
        if comment:
            self.node.comment = comment
        self.board.push(move)
        print(f"Added move: {move}")
        return True
    def handle_jumpback(self, move_str):
      pattern = r"(\d+)(\.{1,3})\s*([a-zA-Z0-9+#=x/-]+)"
      match = re.search(pattern, move_str)

      if match:
        move_num = int(match.group(1))
        dots = match.group(2)
        move_san = match.group(3)
        is_white = len(dots) == 1 # If there are 3 dots (4... c5), it's Black's move

      current_ply = len(self.board.move_stack)
      if(is_white): target_ply = (move_num - 1) *2
      else: target_ply = (move_num -1) *2 +1
      n_steps = current_ply - target_ply
      if(n_steps < 0): return False
      print(f"Going back {n_steps} steps")
      self.go_back(n_steps)
      return True


    def go_back(self, n=1):
        for _ in range(n):
            if self.node.parent is not None:
                self.node = self.node.parent
                self.board.pop()
    def save_game(self, filename):
        with open(filename, "w") as f:
            exporter = chess.pgn.FileExporter(f)
            self.game.accept(exporter)
            print(f"Saved to {filename}")
editor = PGNEditor()

import time
from google.api_core import exceptions

current_bookmark = "Beginning of the game file"
many_tries = False
err_move = None
jumpback = False

data = get_moves(editor, current_bookmark=current_bookmark, jumpback = jumpback , err_move=err_move, many_tries=many_tries)
start_time = time.time()
many_tries = False
err_move = None


while True:
  jumpback = False

  action = data.get('action') or 'MOVE_BATCH'

  if action == 'MOVE_BATCH':
    for move_data in data.get('moves', []):
      san = move_data['san']
      transcript = move_data.get('transcript_comment', '')
      ai_note = move_data.get('ai_evaluation', '')
      # Format: { [Transcript] ... } { [%ai ...] }
      full_comment = ""
      if transcript:
        full_comment += f"[Source] {transcript} "
      if ai_note:
        full_comment += f"{{ [%ai {ai_note}] }}"
      print(full_comment)
      print(san)
      test= editor.add_move(san, full_comment)
      if test == False:
        if(err_move):
          many_tries = True
        err_move = san
        break
      else:
        many_tries = False
        err_move = None

  elif action == 'JUMP_AND_VARIATION':
    test = editor.handle_jumpback(data.get('jump_target_san', ''))
    if test == False:
      err_move = data.get('jump_target_san', '')
      err_move += "\n either invalid move after jump, or jumped to future move"
    jumpback = True
    for move_data in data.get('moves', []): # this code could only be in move_branch code, but
    #gemini keeps ignoring instruction to not add moves here
      san = move_data['san']
      transcript = move_data.get('transcript_comment', '')
      ai_note = move_data.get('ai_evaluation', '')

      # Format: { [Transcript] ... } { [%ai ...] }
      full_comment = ""
      if transcript:
        full_comment += f"[Source] {transcript} "
      if ai_note:
        full_comment += f"{{ [%ai {ai_note}] }}"
      print(full_comment)
      print(san)
      test = editor.add_move(san, full_comment)
      if test == False:
        if(err_move):
          many_tries = True
        err_move = san
        break
      else:
        many_tries=False
        err_move = None
  elif action == 'DONE':
    editor.save_game("game.pgn")
    client.caches.delete(name=chess_cache.name)
    break

  else: # removed WAIT option as LLM seems to never actually use it
    print("invalid output")
    break
  current_bookmark = data.get('source_quote', '')

  try:
    data = get_moves(editor, current_bookmark, jumpback, err_move, many_tries)
    print(data)
    print(editor.show_board())
    print()
    print(editor.show_moves())
    print()
    time.sleep(1)
    if(time.time() - start_time > 3400):
      print("hour spend, extend cache")
      client.caches.update(
        name=chess_cache.name,
        config=types.UpdateCachedContentConfig(
        ttl='3600s'  #reset
        )
      )
      start_time = time.time()

  except Exception as e:
    print(e)
    print("potential server error")
    time.sleep(300)
    editor.save_game("crash_recovery.pgn")
    continue

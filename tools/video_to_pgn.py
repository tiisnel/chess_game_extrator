import cv2
import numpy as np
from itertools import combinations
from chessimg2pos import predict_fen
import re
import chess
import chess.pgn

def create_pgn(video_path, board_bbox):
    creator = PGNCreator()
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    last_stable_board = None
    frame_idx = 0
    seen = False

    while cap.isOpened():
        
        ret, frame = cap.read()
        if not ret:
            break
        if not (board_bbox):
            STEP_MS = 1000 # 1 sec
            current_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            print(current_ms)
            board_bbox = find_board(frame)
            cap.set(cv2.CAP_PROP_POS_MSEC, current_ms + STEP_MS)
            continue
        else:
            top, bottom, left, right = board_bbox

        STEP_MS = 100


        current_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        cap.set(cv2.CAP_PROP_POS_MSEC, current_ms + STEP_MS)
        if last_stable_board is not None:
            f = frame[top:bottom, left:right] # board only
            diff = cv2.absdiff(f, last_stable_board)
            motion_pixels = np.count_nonzero(diff > 25)
            if motion_pixels < (f.size * 0.005):#frame is stable(no motion), similar to prev
                if seen == False:
                    cv2.imshow('test', f)
                    cv2.waitKey(1)
                    fen = normalize_fen(f)


                    creator.add_position(fen, current_ms)

                    seen=True
            else:
                seen=False

        last_stable_board = frame[top:bottom, left:right]

    creator.save_game("cv2.pgn")
def find_board(image):
    #find edges:

    b, g, r = cv2.split(image)
    color_diff = cv2.max(cv2.max(cv2.absdiff(r, g), cv2.absdiff(g, b)), cv2.absdiff(r, b))

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.addWeighted(gray, 0.7, color_diff, 0.3, 0)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(enhanced)

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 10, 100)
    
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    morph_gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)
    #convert gray to white:
    normalized_edges = cv2.normalize(morph_gradient, None, 0, 255, cv2.NORM_MINMAX)
    _, morph_edges = cv2.threshold(normalized_edges, 35, 255, cv2.THRESH_TOZERO)

    clean_edges = cv2.Canny(morph_edges, 30, 90)
    #cv2.imshow('Debug 1: Edges', morph_edges)#  - debug only
    #cv2.waitKey(1)
    h, w = clean_edges.shape[:2] #if board is exactly in image corner
    clean_edges[0, :] = 255      # Top edge
    clean_edges[h - 1, :] = 255  # Bottom edge
    clean_edges[:, 0] = 255      # Left edge
    clean_edges[:, w - 1] = 255  # Right edg

    # filter out straight vertial/horizontal lines
    lines = cv2.HoughLinesP(clean_edges, rho=1, theta=np.pi/180, threshold=80, minLineLength=200, maxLineGap=10)
    #debug_lines_img = image.copy()
    h_lines, v_lines = [], []

    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180.0 / np.pi)
            
            if angle ==0 or angle ==180 :  # Horizontal
                h_lines.append((y1 + y2) / 2)
      #          cv2.line(debug_lines_img, (x1, y1), (x2, y2), (0, 0, 255), 2) # Red for horizontal
            elif angle ==90:          # Vertical
                v_lines.append((x1 + x2) / 2)
     #           cv2.line(debug_lines_img, (x1, y1), (x2, y2), (0, 255, 0), 2) # Green for vertical

    #cv2.imshow('Debug 2: Detected Lines (Red=H, Green=V)', debug_lines_img)# - debug only
    #cv2.waitKey(1)
    def cluster_positions(positions, max_diff=15):
        if not positions:
            return []
        positions = sorted(positions)
        clusters = [[positions[0]]]
        for pos in positions[1:]:
            if pos - clusters[-1][-1] < max_diff:
                clusters[-1].append(pos)
            else:
                clusters.append([pos])
        return [int(np.mean(c)) for c in clusters]
    

    h_peaks = cluster_positions(h_lines)
    v_peaks = cluster_positions(v_lines)
   # debug_peaks_img = image.copy()
   # for y in h_peaks:
   #    cv2.line(debug_peaks_img, (0, y), (image.shape[1], y), (255, 0, 0), 1)
   # for x in v_peaks:
   #     cv2.line(debug_peaks_img, (x, 0), (x, image.shape[0]), (255, 255, 0), 1)
    
   # cv2.imshow('Debug 3: Peak Lines (Blue=H, Cyan=V)', debug_peaks_img)
   # cv2.waitKey(0)
    
   # print(f"[DEBUG] Found {len(h_peaks)} horizontal peak lines.")
   # print(f"[DEBUG] Found {len(v_peaks)} vertical peak lines.")

    

    def find_best_9_lines(peaks, target_span=None, max_jitter_ratio=1.5):
        if len(peaks) < 9:
            return None
        best_cand = None
        best_score = float('inf')

        for cand in combinations(peaks, 9):
            spacings = np.diff(cand)
            
            min_sp = np.min(spacings)
            max_sp = np.max(spacings)
            med_sp = np.median(spacings)

            # --- STRICT FILTER 1: Reject Tiny or Huge Squares ---
            if min_sp < 15 or max_sp > 250:
                continue


            if (max_sp / float(min_sp)) > max_jitter_ratio:
                continue

            span = cand[-1] - cand[0]
            if target_span is not None:
                span_error = abs(span - target_span)
                # Total height/width cannot differ by more than 5% of board width
                if span_error > (target_span * 0.05):
                    continue
            #  Normalized Max Absolute Deviation (MAD)
            mad_score = np.max(np.abs(spacings - med_sp)) / med_sp

            # Secondary penalty: Span mismatch against orthogonal axis
            span_penalty = (abs(span - target_span) / target_span) if target_span else 0.0

            total_score = mad_score + (span_penalty * 2.0)

            if total_score < best_score:
                best_score = total_score
                best_cand = cand

        return best_cand

    best_v = find_best_9_lines(v_peaks)
    board_width = (best_v[-1] - best_v[0]) if best_v is not None else None
    #search square shape

    best_h = find_best_9_lines(h_peaks, target_span=board_width)

    if best_h is not None and best_v is not None:
        final_img = image.copy()
        top, bottom = best_h[0], best_h[-1]
        left, right = best_v[0], best_v[-1]
        
        #cv2.rectangle(final_img, (left, top), (right, bottom), (0, 255, 0), 3)
        #cv2.imshow('Debug 4: Final Result', final_img)
        #cv2.imshow('Debug 5: Cropped Board', image[top:bottom, left:right])
        return(top, bottom, left, right)
   # else:
  #      print("[DEBUG] Could not lock onto a valid 9x9 line combination.")
import numpy as np
from PIL import Image, PngImagePlugin
def normalize_fen(frame):
    output_path='temp_board.png'

    inv_gamma = 0.45
    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
    gamma_baked = cv2.LUT(frame, table)

    pil_img = Image.fromarray(gamma_baked)

    pil_img.save( # one test video(g7) did single square misdetection
        #without gamma correction,
        #fix untested on other games, could use cv2.imwrite simply there
        output_path, 
        format="PNG" 
    )
    #cv2.imwrite('temp_board.png', frame)
    fen = predict_fen('temp_board.png')
    ranks = fen.split("/")
    compressed = []
    for rank in ranks:
        compressed.append(re.sub(r"1+", lambda m: str(len(m.group(0))), rank))
    return "/".join(compressed)


class PGNCreator:
    def __init__(self):
        self.game = chess.pgn.Game()
        self.node = self.game
        self.board = self.game.board()
        self.start = False # some games might start(show) from tabiya before main
        self.blackside=False # some present board from black-to-move side
        self.fen_map = {}
    def save_game(self, filename):
        with open(filename, "w") as f:
            exporter = chess.pgn.FileExporter(f)
            self.game.accept(exporter)
            print(f"Saved to {filename}")
    def reverse_fen(self, fen):
        tmp = chess.Board(fen)
        tmp.apply_transform(chess.flip_vertical)
        tmp.apply_transform(chess.flip_horizontal)
        return tmp.board_fen()

    def add_position(self, board_fen, timestamp):
        print(board_fen)

        
        if(self.start == False and board_fen == 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'):
            self.start = True
            print('start')
            return
        if(self.start == False and board_fen == 'RNBKQBNR/PPPPPPPP/8/8/8/8/pppppppp/rnbkqbnr'):
            self.start = True
            self.blackside=True
            print('flip and start')
            return
        if(self.start== False and board_fen == 'rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR'):
            self.start = True
            #self.blackside=True
            print("c4 example")


            self.node = self.node.add_variation(chess.Move.from_uci("e2e4"))
            self.board.push(chess.Move.from_uci("e2e4"))
            self.fen_map[self.board.board_fen()] = (self.node, self.board.copy())

            self.node = self.node.add_variation(chess.Move.from_uci("c7c5"))
            self.board.push(chess.Move.from_uci("c7c5"))
            self.fen_map[self.board.board_fen()] = (self.node, self.board.copy())


            return
        

        if not self.start: # wait for true start
            return
        if(self.blackside):
            board_fen = self.reverse_fen(board_fen)
        if (board_fen == self.board.board_fen()):
            return
        print(board_fen)

        for move in self.board.legal_moves:
            b = self.board.copy()
            b.push(move)
            if(b.board_fen() == board_fen):
                print(move)
                self.node = self.node.add_variation(move)
                self.node.comment = str(int(timestamp/1000))
                self.board.push(move)
                self.fen_map[self.board.board_fen()] = (self.node, self.board.copy())
                return
            for move2 in b.legal_moves:
                b2=b.copy()
                b2.push(move2)
                if(b2.board_fen() == board_fen):
                    print(move,move2)
                    self.node = self.node.add_variation(move)
                    self.node.comment = str(int(timestamp/1000))
                    self.board.push(move)
                    self.fen_map[self.board.board_fen()] = (self.node, self.board.copy())

                    self.node = self.node.add_variation(move2)
                    self.node.comment = str(int(timestamp/1000))

                    self.board.push(move2)
                    self.fen_map[self.board.board_fen()] = (self.node, self.board.copy())
                    return

        original_board = self.board.copy()
        original_node = self.node

        if board_fen in self.fen_map:
            self.node, self.board = self.fen_map[board_fen]
            self.board = self.board.copy()
            print("undo/hop")
        
        while self.node is not None:
            if self.board.board_fen() == board_fen:
                break
            for move in self.board.legal_moves:
                b = self.board.copy()
                b.push(move)
                if(b.board_fen() == board_fen):
                    print(move)
                    self.node = self.node.add_variation(move)
                    self.node.comment = str(int(timestamp/1000))
                    self.board.push(move)
                    self.fen_map[self.board.board_fen()] = (self.node, self.board.copy())
                    return
            if(self.node.parent is not None):
                self.board.pop()
            self.node = self.node.parent


        else: # ignore mid-move misidentified boards
            self.board = original_board
            self.node = original_node
        if(board_fen == self.reverse_fen(self.board.board_fen())):
            print("flip")
            self.blackside = not self.blackside
        print("no action")
            



#create_pgn('images/v1.mp4', board_bbox=(100, 600, 200, 700))

create_pgn('images/v7.mp4', None)



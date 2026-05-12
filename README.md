# chess_game_extrator
This repo includes code and datasets used in masters thesis.

The main goal of the project is to define pipeline, that could extract chess games with multiple variations and included commentary, from a range of instructive videos, using only audio channel.

To recreate, use youtube_dataloader to get transcript file and audio source from any video.
Optionally, use whisper.py or improve_accuracy to get better quality ttranscript.
Run gemini_to_pgn to recreate pgn from video.
Optionally use pgn_accuracy to get initial estimation for convertion quality.

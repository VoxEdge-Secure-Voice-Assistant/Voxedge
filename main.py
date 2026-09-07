"""
main.py — VoxEdge: Voice-controlled fan with speaker verification.

HOW IT WORKS (explain this in your viva):
──────────────────────────────────────────
1. On startup: load the Vosk speech-to-text model and the enrolled speaker
   embedding that was created by enroll.py.

2. Each cycle (triggered by pressing Enter):
   a. Record 3 seconds of audio via the microphone.
   b. SPEECH RECOGNITION: feed the audio to Vosk → get transcribed text.
   c. COMMAND PARSING: check whether the text contains "fan on" or "fan off".
   d. SPEAKER VERIFICATION: generate a Resemblyzer embedding from the same
      recording and compare it to the enrolled embedding using cosine similarity.
      • Cosine similarity = 1 → identical voices
      • Cosine similarity = 0 → completely different voices
      • We accept if similarity ≥ SIMILARITY_THRESHOLD
   e. Decide the outcome and update the GUI accordingly.

VOSK MODEL NOTE:
  Download vosk-model-small-en-us-0.15 from https://alphacephei.com/vosk/models
  Extract it and rename the folder to exactly: model
  Place the model/ folder in the same directory as this file.

Usage:
    python main.py
"""

import json       # Vosk returns JSON strings; we parse them here
import threading  # run the input loop in a background thread while Tkinter runs
from pathlib import Path

import numpy as np
import sounddevice as sd    # microphone recording
import soundfile as sf      # writing/reading WAV files
from resemblyzer import VoiceEncoder, preprocess_wav  # speaker embedding
from vosk import KaldiRecognizer, Model               # offline speech recognition

from fan_simulator import FanSimulator


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION  ← change these values to tune the system
# ══════════════════════════════════════════════════════════════════════════════

# How similar the speaker's voice must be to the enrolled voice (0.0 – 1.0).
# Higher = stricter (fewer false accepts but may reject the real user more).
# Lower  = looser  (more permissive but may accept imposters).
SIMILARITY_THRESHOLD = 0.75

SAMPLE_RATE       = 16_000          # samples per second (16 kHz = Vosk/Resemblyzer standard)
RECORDING_SECONDS = 3               # how long we record each command
MODEL_FOLDER      = Path("model")   # Vosk model directory (must exist before running)
ENROLLED_VOICE    = Path("enrolled_voice.npy")  # created by enroll.py
TEMP_WAV          = Path("command.wav")         # temporary file for each recording

# ══════════════════════════════════════════════════════════════════════════════


def record_command() -> None:
    """Record a 3-second command clip from the microphone and save it as WAV."""
    print(f"\n  ▶  Recording for {RECORDING_SECONDS} seconds — SPEAK YOUR COMMAND...")

    # sd.rec() captures audio; dtype float32 is the sounddevice native format
    audio = sd.rec(
        int(RECORDING_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()  # block until recording is complete

    # Save as WAV so both Vosk and Resemblyzer can read it from disk
    sf.write(TEMP_WAV, audio, SAMPLE_RATE)
    print("  ✔  Recording saved.")


def transcribe_command(model: Model) -> str:
    """
    Use Vosk to transcribe the saved command WAV file.

    Vosk is an offline speech recognition toolkit. It uses a KaldiRecognizer
    which processes audio in chunks (like a stream). We feed the entire file
    at once, then ask for the final result as a JSON string.
    """
    recognizer = KaldiRecognizer(model, SAMPLE_RATE)

    # Read the WAV as int16 — that is the format Vosk's AcceptWaveform expects
    with sf.SoundFile(TEMP_WAV) as wav_file:
        audio_int16 = wav_file.read(dtype="int16")

    # Feed all samples as raw bytes to the recognizer
    recognizer.AcceptWaveform(audio_int16.tobytes())

    # FinalResult() flushes the buffer and returns a JSON string like:
    #   {"text": "fan on"}
    result_json = json.loads(recognizer.FinalResult())
    return result_json.get("text", "").lower().strip()


def parse_command(text: str) -> str | None:
    """
    Check if the transcribed text contains a recognised fan command.

    We use a word-set check so "please turn the fan on" still triggers "on".
    Returns "on", "off", or None (unknown command).
    """
    words = set(text.split())  # split into individual words for flexible matching
    if "fan" in words and "on" in words:
        return "on"
    if "fan" in words and "off" in words:
        return "off"
    return None  # command not recognised


def compute_similarity(encoder: VoiceEncoder, enrolled_embedding: np.ndarray) -> float:
    """
    Generate a speaker embedding from the temporary recording and compute
    cosine similarity against the enrolled (reference) embedding.

    Cosine similarity formula:
        sim = (A · B) / (|A| × |B|)
    Since enrolled_embedding was already normalised in enroll.py (|B| = 1),
    this simplifies to:
        sim = A · B / |A|
    But we keep the full formula here for clarity.
    """
    # preprocess_wav: resamples, removes silence, normalises volume
    waveform = preprocess_wav(TEMP_WAV)

    # embed_utterance → 256-dimensional vector representing this speaker
    command_embedding = encoder.embed_utterance(waveform)

    # Cosine similarity: how aligned are the two vectors?
    similarity = float(
        np.dot(command_embedding, enrolled_embedding)
        / (np.linalg.norm(command_embedding) * np.linalg.norm(enrolled_embedding))
    )
    return similarity


def command_loop(fan: FanSimulator, stop_event: threading.Event) -> None:
    """
    Main command loop — runs in a background thread so that Tkinter's
    mainloop() can run on the main thread without being blocked.

    The threading model:
    • Main thread  → fan.run() → Tkinter event loop (handles GUI redraws)
    • Worker thread → this function → blocks on input(), records, processes
    • GUI updates  → always done via fan.root.after(0, callback) which schedules
                     the update safely on the Tkinter thread
    """

    # ── Pre-flight checks ────────────────────────────────────────────────────
    if not MODEL_FOLDER.is_dir():
        print("\n  ✖  ERROR: model/ folder not found.")
        print("     Download vosk-model-small-en-us-0.15 from:")
        print("     https://alphacephei.com/vosk/models")
        print("     Extract it and rename the folder to: model")
        stop_event.set()
        fan.root.after(0, fan.root.destroy)
        return

    if not ENROLLED_VOICE.is_file():
        print("\n  ✖  ERROR: enrolled_voice.npy not found.")
        print("     Run these two scripts first:")
        print("       python record_enrollment.py")
        print("       python enroll.py")
        stop_event.set()
        fan.root.after(0, fan.root.destroy)
        return

    # ── Load models ──────────────────────────────────────────────────────────
    print("\n  Loading Vosk speech recognition model (may take a moment)...")
    model = Model(str(MODEL_FOLDER))
    print("  ✔  Vosk model loaded.")

    print("  Loading enrolled voice embedding...")
    enrolled_embedding = np.load(ENROLLED_VOICE)
    print("  ✔  Enrolled voice loaded.")

    print("  Loading Resemblyzer voice encoder...")
    encoder = VoiceEncoder()
    print("  ✔  Resemblyzer encoder ready.\n")

    print("═" * 55)
    print("  VoxEdge is READY")
    print(f"  Verification threshold: {SIMILARITY_THRESHOLD}")
    print("  Commands: 'fan on'  |  'fan off'")
    print("  Type 'q' and press Enter to quit.")
    print("═" * 55)

    # ── Main loop ─────────────────────────────────────────────────────────────
    while not stop_event.is_set():
        print()
        user_input = input("  Press Enter to record a command (or 'q' to quit): ").strip().lower()

        if user_input == "q":
            print("  Closing VoxEdge... goodbye!")
            stop_event.set()
            fan.root.after(0, fan.root.destroy)  # close the GUI window
            return

        try:
            # ── Step 1: Record ───────────────────────────────────────────────
            record_command()

            # ── Step 2: Transcribe with Vosk ─────────────────────────────────
            text = transcribe_command(model)
            print(f"\n  [SPEECH]  Transcribed text : \"{text or '[nothing recognised]'}\"")

            # ── Step 3: Parse the command ─────────────────────────────────────
            action = parse_command(text)
            print(f"  [COMMAND] Parsed action    : {action or 'none (say fan on / fan off)'}")

            # ── Step 4: Speaker verification ─────────────────────────────────
            similarity = compute_similarity(encoder, enrolled_embedding)
            verified   = similarity >= SIMILARITY_THRESHOLD
            print(f"  [VOICE]   Similarity score : {similarity:.4f}  "
                  f"(threshold: {SIMILARITY_THRESHOLD})")
            print(f"  [VOICE]   Verification     : {'✔ PASSED' if verified else '✖ FAILED'}")

            # ── Step 5: Decide outcome ────────────────────────────────────────
            print()
            if not verified:
                # Speaker is not recognised — deny access regardless of command
                fan.root.after(0, fan.access_denied)
                print(f"  ══ RESULT: ACCESS DENIED (score {similarity:.4f} < {SIMILARITY_THRESHOLD}) ══")

            elif action == "on":
                fan.root.after(0, fan.turn_on)
                print(f"  ══ RESULT: FAN TURNED ON  (score {similarity:.4f} ✔) ══")

            elif action == "off":
                fan.root.after(0, fan.turn_off)
                print(f"  ══ RESULT: FAN TURNED OFF (score {similarity:.4f} ✔) ══")

            else:
                # Verified speaker but unrecognised command
                print("  ══ RESULT: Speaker verified but command not recognised. ══")
                print("             Try saying: 'fan on'  or  'fan off'")

        except Exception as error:
            print(f"\n  ✖  ERROR during processing: {error}")


def main() -> None:
    """Entry point: create the GUI, start the worker thread, run the event loop."""

    # Create the Tkinter fan window
    fan = FanSimulator()

    # A threading Event that both threads check to know when to stop
    stop_event = threading.Event()

    # Spawn the command loop in a background (daemon) thread.
    # daemon=True means Python will not wait for this thread when the main
    # thread exits (e.g. user closes the Tkinter window directly).
    worker = threading.Thread(
        target=command_loop,
        args=(fan, stop_event),
        daemon=True,
    )
    worker.start()

    # fan.run() blocks here until the window is closed
    fan.run()

    # Signal the worker thread to stop if the window was closed by the user
    stop_event.set()


if __name__ == "__main__":
    main()
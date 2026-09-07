"""
record_enrollment.py — VoxEdge Step 1: Record voice samples for enrollment.

Run this script FIRST. It records 3 short (3-second) clips of your voice
using the default microphone and saves them to the enrollment/ folder.

Usage:
    python record_enrollment.py
"""

from pathlib import Path  # for cross-platform folder/file paths

import sounddevice as sd   # to record audio from the microphone
import soundfile as sf     # to save the audio as a .wav file


# ── Configuration ────────────────────────────────────────────────────────────
SAMPLE_RATE       = 16_000   # 16 kHz — required by both Vosk and Resemblyzer
RECORDING_SECONDS = 3        # length of each enrollment clip
ENROLLMENT_FOLDER = Path("enrollment")  # folder where samples will be saved
# ─────────────────────────────────────────────────────────────────────────────


def record_clip(file_path: Path) -> None:
    """Record one 3-second mono clip from the microphone and save it as WAV."""

    print(f"  ▶  Recording for {RECORDING_SECONDS} seconds — SPEAK NOW...")

    # sd.rec() starts a non-blocking recording; sd.wait() blocks until it ends
    audio = sd.rec(
        int(RECORDING_SECONDS * SAMPLE_RATE),  # total number of samples
        samplerate=SAMPLE_RATE,
        channels=1,       # mono — one microphone channel is enough
        dtype="float32",  # float32 is the native format for sounddevice
    )
    sd.wait()  # wait here until all samples have been captured

    # Write the NumPy array to a WAV file on disk
    sf.write(file_path, audio, SAMPLE_RATE)
    print(f"  ✔  Saved: {file_path}")


def main() -> None:
    # Create the enrollment folder if it does not already exist
    ENROLLMENT_FOLDER.mkdir(exist_ok=True)

    print("=" * 50)
    print("  VoxEdge — Speaker Enrollment (Step 1 of 2)")
    print("=" * 50)
    print("We will record THREE short voice samples.")
    print("Say anything natural, e.g. 'Hello, my name is ...'")
    print("Stay consistent — same tone and distance from mic each time.\n")

    for sample_number in range(1, 4):  # samples 1, 2, 3
        print(f"─── Sample {sample_number} / 3 ───────────────────────────")
        input(f"  Press Enter when you are ready...")  # give the user time to prepare
        output_path = ENROLLMENT_FOLDER / f"sample_{sample_number}.wav"
        record_clip(output_path)
        if sample_number < 3:
            print("  Take a short breath before the next sample.")

    print("\n" + "=" * 50)
    print("  Enrollment recordings COMPLETE.")
    print("  Next step → run:  python enroll.py")
    print("=" * 50)


if __name__ == "__main__":
    main()
"""
enroll.py — VoxEdge Step 2: Build the enrolled speaker voice profile.

Run this AFTER record_enrollment.py. It:
  1. Loads the 3 WAV clips from enrollment/
  2. Uses Resemblyzer to turn each clip into a 256-dimensional "voice embedding"
     (a numeric fingerprint of the speaker's voice)
  3. Averages the three embeddings to get a stable, representative profile
  4. Saves the result to enrolled_voice.npy (loaded by main.py at runtime)

Usage:
    python enroll.py
"""

from pathlib import Path  # cross-platform path handling
import sys

import numpy as np                              # array maths
from resemblyzer import VoiceEncoder, preprocess_wav  # speaker embedding library


def configure_console() -> None:
    """Use UTF-8 where supported so Windows consoles can print status symbols."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


configure_console()


# ── Configuration ────────────────────────────────────────────────────────────
ENROLLMENT_FOLDER = Path("enrollment")   # folder containing sample_1/2/3.wav
OUTPUT_FILE       = Path("enrolled_voice.npy")  # where the embedding is saved
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    # ── 1. Find the three enrollment WAV files ───────────────────────────────
    recording_paths = sorted(ENROLLMENT_FOLDER.glob("sample_*.wav"))
    if len(recording_paths) != 3:
        raise SystemExit(
            f"ERROR: Found {len(recording_paths)} file(s) in {ENROLLMENT_FOLDER}/, "
            "but expected exactly 3.\n"
            "Please run:  python record_enrollment.py"
        )

    # ── 2. Load the Resemblyzer encoder ─────────────────────────────────────
    # VoiceEncoder is a pretrained deep learning model (GE2E).
    # It maps any audio clip to a 256-dimensional embedding vector such that
    # clips from the same speaker land close together in that space.
    print("=" * 50)
    print("  VoxEdge — Speaker Enrollment (Step 2 of 2)")
    print("=" * 50)
    print("\nLoading Resemblyzer voice encoder (may take a moment)...")
    encoder = VoiceEncoder()

    # ── 3. Generate an embedding for each sample ─────────────────────────────
    embeddings = []
    for recording_path in recording_paths:
        print(f"  Processing {recording_path.name}...")
        # preprocess_wav resamples to 16 kHz, removes silence, normalises volume
        waveform = preprocess_wav(recording_path)
        # embed_utterance converts the waveform to a 256-dim numpy vector
        embedding = encoder.embed_utterance(waveform)
        embeddings.append(embedding)
        print(f"    Embedding shape: {embedding.shape}, norm: {np.linalg.norm(embedding):.4f}")

    # ── 4. Average the three embeddings into one representative profile ───────
    # Stacking them into a 2-D array (3 × 256) then averaging along axis 0
    # gives a single 256-dim centroid that represents the speaker's "average" voice.
    enrolled_embedding = np.mean(np.stack(embeddings), axis=0)

    # Normalise to unit length so cosine similarity = simple dot product later
    enrolled_embedding /= np.linalg.norm(enrolled_embedding)

    # ── 5. Save the profile to disk ──────────────────────────────────────────
    np.save(OUTPUT_FILE, enrolled_embedding)

    print(f"\n  ✔  Average embedding saved to: {OUTPUT_FILE}")
    print(f"     Embedding dimensions: {enrolled_embedding.shape}")
    print("\n" + "=" * 50)
    print("  Enrollment COMPLETE.")
    print("  Next step → run:  python main.py")
    print("=" * 50)


if __name__ == "__main__":
    main()

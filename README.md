# VoxEdge — Voice-Controlled Fan with Speaker Verification

A college mini project demo that combines **offline speech recognition** (Vosk)
with **speaker verification** (Resemblyzer) to control a simulated fan GUI.

## How It Works

`
Microphone → record 3s audio → Vosk (speech-to-text) → parse command
                            ↓
                  Resemblyzer (speaker embedding)
                            ↓
              cosine similarity vs enrolled voice
                            ↓
         ≥ 0.75 threshold?  YES → execute command (FAN ON/OFF)
                            NO  → ACCESS DENIED
`

## Project Structure

| File | Purpose |
|------|---------|
| ecord_enrollment.py | Records 3 voice samples to enrollment/ |
| enroll.py | Builds average voice embedding → enrolled_voice.npy |
| an_simulator.py | Tkinter GUI (fan blade animation + status label) |
| main.py | Main pipeline: record → transcribe → verify → act |
| equirements.txt | All Python dependencies |

## Setup (One-Time)

### 1. Download the Vosk model
Go to: https://alphacephei.com/vosk/models
Download: **vosk-model-small-en-us-0.15**
Extract it and rename the folder to model, place it here:
`
Voxedge/
  model/          ← put it here
  main.py
  ...
`

### 2. Create the virtual environment (Python 3.11)
`powershell
python -m venv .venv311
.venv311\Scripts\activate
pip install -r requirements.txt
`

### 3. Enroll your voice
`powershell
python record_enrollment.py   # records 3 samples
python enroll.py              # builds enrolled_voice.npy
`

## Run the Demo
`powershell
.venv311\Scripts\activate
python main.py
`

Say **"fan on"** or **"fan off"** after pressing Enter. Watch the GUI update!

## Key Concepts (for Viva)

- **Vosk**: Offline speech recognition using a Kaldi acoustic model
- **Resemblyzer**: Deep learning model (GE2E) → 256-dim voice embedding
- **Cosine similarity**: dot product of unit vectors — how "aligned" two embeddings are
- **Threshold 0.75**: Tunable constant at top of main.py
- **Threading**: Tkinter needs the main thread; input loop runs in a daemon thread

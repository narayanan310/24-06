# Edge Auto Assistant

An edge-native, local LLM-powered virtual assistant for vehicles. Runs entirely on-device (e.g., Raspberry Pi) using LLaMA.cpp, Faster-Whisper, and a local FAISS RAG database, with zero reliance on cloud services.

## Architecture
- **Local LLM**: Llama-3.2-1B-Instruct quantized via `llama.cpp`
- **Speech-to-Text**: Offline inference using `faster-whisper`
- **RAG**: FAISS and `fastembed` using ONNX for the owner's manual
- **Vehicle Interface**: Virtual CAN bus for interacting with vehicle modules (HVAC, Windows, Lights)
- **Safety Gatekeeper**: Dynamic rule supervisor to prevent unsafe operations (e.g., sunroof block at high speeds)

## Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running the Project
The project uses a bash wrapper to handle process lifecycle.
```bash
./start.sh
```
In a separate terminal, to view the simulation dashboard:
```bash
./start_dashboard.sh
```

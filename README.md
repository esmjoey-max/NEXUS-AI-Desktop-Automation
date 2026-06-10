NEXUS AI CORE
Project Overview
NEXUS is a local AI agent designed for autonomous multi-monitor desktop automation. It uses PyQt6 for the GUI, Ollama for local inference, and MSS/OpenCV for real-time screen capture and spatial coordinate mapping.

The goal of this project is to allow a user to issue natural language commands (e.g., "Open calculator," "Add a tab in Edge") that the AI translates into OS-level mouse and keyboard actions.

🛠 Tech Stack
Language: Python 3.12+

GUI: PyQt6

Vision: MSS (Multi-monitor capture), OpenCV (Image processing & scaling)

AI: Ollama (Local Vision Language Models)

Automation: PyAutoGUI

Voice: SpeechRecognition, Whisper (Transcription), pyttsx3 (TTS)

🚀 How to get NEXUS running
To test this locally, follow these steps:

Install Ollama: Download and install it from ollama.com.

Pull the required Vision Model:

Bash
ollama pull llava
Clone this repository:

Bash
git clone https://github.com/YOUR-USERNAME/NEXUS-AI-Desktop-Automation.git
cd NEXUS-AI-Desktop-Automation
Setup Virtual Environment:

Bash
python -m venv venv
.\venv\Scripts\activate
Install dependencies:

Bash
pip install -r requirements.txt
Launch the app:

Bash
python main_software.py
🐛 Current Development Challenges
I am currently seeking help with the following issues:

Inference Parsing: I am having trouble forcing the VLM to act as an operator. It frequently hallucinates conversational descriptions of the screen instead of outputting the requested THOUGHT and COMMAND structure.

500 Internal Server Errors: I am experiencing intermittent 500 errors when passing screenshot payloads to Ollama, likely related to model architecture or payload size.

Coordinate Mapping: I need to verify that my coordinate math for stitched, multi-monitor setups (1440p + 1080p) is mapping correctly to the active desktop resolution.
<img width="1296" height="880" alt="image" src="https://github.com/user-attachments/assets/375150b6-7e52-492e-a76e-76293bf3cbca" />
<img width="1303" height="879" alt="image" src="https://github.com/user-attachments/assets/05d7f0ac-fe37-412f-b638-d32c1b7ecada" />
<img width="1290" height="882" alt="image" src="https://github.com/user-attachments/assets/da1f6bde-0345-42ab-8aa5-16a22edfc4a7" />
<img width="1296" height="881" alt="image" src="https://github.com/user-attachments/assets/b9b1e5c6-957b-448b-982e-8c1ae3d50e2d" />




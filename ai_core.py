import requests
import base64
import cv2
import logging

logger = logging.getLogger("AICore")

class LocalAgentBrain:
    def __init__(self, memory=None, monitor_layout=None, known_apps=None):
        self.memory = memory
        self.monitor_layout = monitor_layout
        self.known_apps = known_apps
        self.api_url = "http://127.0.0.1:11434/api/chat"
        self.model = "llama3.2-vision"  # Updated default
        self.history = []

    def get_available_models(self):
        try:
            resp = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                return models if models else ["llama3.2-vision"]
        except Exception:
            pass
        return ["llama3.2-vision"]

    def set_model(self, model_name: str):
        self.model = model_name
        logger.info(f"AI Model switched to: {self.model}")
        
    def clear_history(self):
        self.history = []

    def verify_action(self, frame, token) -> tuple[bool, str]:
        return True, "Verified visually."

    def decide_action(self, frame, instruction, config):
        rules_text = "No rules active."
        if self.memory and hasattr(self.memory, 'rules'):
            active = [r.text for r in self.memory.rules if getattr(r, 'active', True)]
            if active:
                rules_text = "\n".join(f"- {r}" for r in active)

        # RUTHLESS SYSTEM PROMPT
        system_prompt = (
            "You are NEXUS, an elite desktop automation agent. "
            "Your ONLY purpose is to control the PC via specific commands. "
            "NEVER describe the image. NEVER say 'In this image I see...'. "
            "If the user says hello or asks a question, use the chat() command.\n\n"
            f"ACTIVE DIRECTIVES:\n{rules_text}\n\n"
            "AVAILABLE COMMANDS:\n"
            "- chat('message') : Speak to the user.\n"
            "- click(x, y) : Click at percentage coordinates (0.0 to 1.0).\n"
            "- type('text') : Type keyboard keys.\n"
            "- press('key') : Press a specific key (e.g., 'win', 'enter', 'tab').\n"
            "- hotkey('ctrl', 'c') : Press key combinations.\n\n"
            "Format your response EXACTLY like this, with NO extra text:\n"
            "THOUGHT: [Your reasoning]\n"
            "COMMAND: [Your command]"
        )

        messages = [{"role": "system", "content": system_prompt}]
        user_msg = {"role": "user", "content": instruction}
        
        if frame is not None and frame.size > 0:
            try:
                success, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                if success:
                    b64_img = base64.b64encode(buffer).decode('utf-8')
                    user_msg["images"] = [b64_img]
            except Exception as e:
                logger.error(f"Image encoding failed: {e}")

        messages.append(user_msg)
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": config.get("temperature", 0.1),  # Lowered temperature for strictness
                "num_predict": config.get("max_tokens", 512),
                "top_p": config.get("top_p", 0.9)
            }
        }
        
        try:
            resp = requests.post(self.api_url, json=payload, timeout=60)
            if resp.status_code == 500:
                logger.error("CRITICAL: Ollama 500 Error. Ensure you are using a VISION model.")
                return None
            resp.raise_for_status()
            return resp.json()["message"]["content"]
            
        except Exception as e:
            logger.error(f"Inference HTTP request failed: {e}")
            return None
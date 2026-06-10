import pyautogui
import time
import re
import logging
import random
import mss
from dataclasses import dataclass
from typing import Optional, Callable

logger = logging.getLogger("ActionCore")
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

@dataclass
class ActionConfig:
    move_duration_min: float = 0.15
    move_duration_max: float = 0.35
    type_interval: float = 0.02
    max_retries: int = 3

class InputAutomationSystem:
    def __init__(self, voice_sys=None, config: ActionConfig = None, verifier: Callable = None):
        self.voice = voice_sys
        self.cfg = config if config else ActionConfig()
        self.verifier = verifier
        self.sct = mss.MSS()

    def execute_action(self, action_string: str, verify_token: str = None, instruction: str = "") -> dict:
        cleaned = action_string.replace("```python", "").replace("```", "").strip()
        commands = [c.strip() for c in cleaned.split(";") if c.strip()]
        
        for cmd in commands:
            if not self._execute_single(cmd):
                return {"success": False, "error": f"Failed to execute: {cmd}"}
            time.sleep(0.3)
            
        return {"success": True}

    def _resolve_coords(self, percent_x: float, percent_y: float):
        mon = self.sct.monitors[0] 
        canvas_x = percent_x * mon["width"]
        canvas_y = percent_y * mon["height"]
        abs_x = int(mon["left"] + canvas_x)
        abs_y = int(mon["top"] + canvas_y)
        return abs_x, abs_y

    def _execute_single(self, cmd: str) -> bool:
        cmd_lower = cmd.lower()
        if not cmd_lower or cmd_lower == "none":
            return True
            
        try:
            if "click(" in cmd_lower: return self._do_click(cmd)
            if "move(" in cmd_lower: return self._do_move(cmd)
            if "type(" in cmd_lower: return self._do_type(cmd)
            if "press(" in cmd_lower: return self._do_press(cmd)
            if "hotkey(" in cmd_lower: return self._do_hotkey(cmd)
            if "chat(" in cmd_lower: return True 
            
            # FIX: If the AI spits out conversational garbage, reject it gently
            # instead of returning a massive error block to the UI.
            if len(cmd.split()) > 4 and "(" not in cmd:
                logger.warning("AI hallucinated text inside the command block. Ignored.")
                return True 

            logger.error(f"Unrecognized command syntax: {cmd}")
            return False
        except Exception as e:
            logger.error(f"Execution error on {cmd}: {e}")
            return False

    def _do_click(self, cmd: str) -> bool:
        coords = re.findall(r"[-+]?\d*\.?\d+", cmd)
        if len(coords) < 2: return False
        x, y = self._resolve_coords(float(coords[0]), float(coords[1]))
        pyautogui.moveTo(x, y, duration=random.uniform(self.cfg.move_duration_min, self.cfg.move_duration_max))
        pyautogui.click(x, y)
        return True

    def _do_move(self, cmd: str) -> bool:
        coords = re.findall(r"[-+]?\d*\.?\d+", cmd)
        if len(coords) < 2: return False
        x, y = self._resolve_coords(float(coords[0]), float(coords[1]))
        pyautogui.moveTo(x, y, duration=random.uniform(self.cfg.move_duration_min, self.cfg.move_duration_max))
        return True

    def _do_type(self, cmd: str) -> bool:
        text = re.search(r"type\(['\"](.+?)['\"]\)", cmd, re.DOTALL)
        if not text: return False
        pyautogui.write(text.group(1), interval=self.cfg.type_interval)
        return True

    def _do_press(self, cmd: str) -> bool:
        key = re.search(r"press\(['\"](.+?)['\"]\)", cmd)
        if not key: return False
        k = key.group(1).lower().replace("win", "winleft")
        pyautogui.press(k)
        return True
        
    def _do_hotkey(self, cmd: str) -> bool:
        keys = re.findall(r"['\"](.+?)['\"]", cmd)
        if not keys: return False
        pyautogui.hotkey(*keys)
        return True
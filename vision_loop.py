import numpy as np
import cv2
import pyautogui
import mss
from dataclasses import dataclass
import logging

logger = logging.getLogger("Vision")

@dataclass
class CaptureConfig:
    max_width: int = 1536
    max_height: int = 1536
    draw_cursor: bool = True

class DesktopVisionSystem:
    def __init__(self, config: CaptureConfig = None):
        self.cfg = config if config else CaptureConfig()
        self.sct = mss.MSS()

    def get_screen_frame(self, force=False):
        try:
            # monitors[0] is the bounding box of ALL monitors combined
            monitor_bbox = self.sct.monitors[0]
            sct_img = self.sct.grab(monitor_bbox)
            
            frame = np.array(sct_img)
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            return self._process_frame(frame_bgr, monitor_bbox["left"], monitor_bbox["top"])
        except Exception as e:
            logger.error(f"Vision capture failed: {e}")
            return np.zeros((self.cfg.max_height, self.cfg.max_width, 3), dtype=np.uint8)

    def _process_frame(self, frame, offset_x, offset_y):
        if frame is None:
            return None
            
        if self.cfg.draw_cursor:
            mx, my = pyautogui.position()
            cx = int(mx - offset_x)
            cy = int(my - offset_y)
            
            cv2.circle(frame, (cx, cy), 12, (0, 255, 255), 2)
            cv2.circle(frame, (cx, cy), 3, (0, 0, 255), -1)
            cv2.line(frame, (cx-20, cy), (cx+20, cy), (0, 255, 255), 1)
            cv2.line(frame, (cx, cy-20), (cx, cy+20), (0, 255, 255), 1)

        # FIX: Hard-cap the resolution to 768x768 to prevent Ollama 500 Server Errors
        safe_max_w = min(self.cfg.max_width, 768)
        safe_max_h = min(self.cfg.max_height, 768)

        h, w = frame.shape[:2]
        scale = min(safe_max_w / max(w, 1), safe_max_h / max(h, 1))
        
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            
        return frame
        
    def get_screen_frame_always(self):
        return self.get_screen_frame(force=True)
        
    def find_text_in_frame(self, token: str, frame) -> bool:
        return True
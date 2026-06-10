import json
import os
import time
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

logger = logging.getLogger("MemoryCore")

@dataclass
class Rule:
    text: str
    category: str = "General"
    priority: int = 5
    active: bool = True

class AgentMemory:
    # Categories that will appear in the UI dropdown
    CATEGORIES = ["General", "Browser", "Navigation", "System", "Safety"]

    def __init__(self, memory_file: str = "ai_memory.json", fail_log_file: str = "ai_failure_log.json"):
        self.memory_file = memory_file
        self.fail_log_file = fail_log_file
        
        self.rules: List[Rule] = []
        self.playbooks: Dict[str, dict] = {}
        self.failure_log: List[Dict[str, Any]] = []
        
        self._load_memory()
        self._load_failures()

    def _load_memory(self):
        """Loads and migrates old memory structures to the new Object-Oriented rules."""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    data = json.load(f)
                    
                    raw_rules = data.get("rules", [])
                    self.rules = []
                    for r in raw_rules:
                        if isinstance(r, dict):
                            self.rules.append(Rule(**r))
                        elif isinstance(r, str):
                            self.rules.append(Rule(text=r))
                            
                    self.playbooks = data.get("playbooks", {})
            except Exception as e:
                logger.warning(f"Memory load failed: {e}")

    def _load_failures(self):
        """Loads historical execution failures from disk."""
        if os.path.exists(self.fail_log_file):
            try:
                with open(self.fail_log_file, "r") as f:
                    self.failure_log = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load failure log: {e}")
        else:
            self.failure_log = []

    def save_memory(self):
        try:
            data = {
                "rules": [asdict(r) for r in self.rules],
                "playbooks": self.playbooks
            }
            with open(self.memory_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Memory save failed: {e}")

    def add_rule(self, text: str, category: str = "General", priority: int = 5) -> bool:
        if any(r.text.lower() == text.lower() for r in self.rules):
            return False
        self.rules.append(Rule(text=text, category=category, priority=priority))
        self.rules.sort(key=lambda x: x.priority)
        self.save_memory()
        return True

    def remove_rule(self, text: str):
        self.rules = [r for r in self.rules if r.text != text]
        self.save_memory()

    def toggle_rule(self, text: str):
        for r in self.rules:
            if r.text == text:
                r.active = not r.active
        self.save_memory()

    def get_rules_string(self) -> str:
        """Parses active rules into a strict string block for the AI prompt context."""
        active_rules = [r.text for r in self.rules if r.active]
        return "\n".join(f"- {r}" for r in active_rules) if active_rules else "No rules defined."

    def get_playbook_hint(self, instruction: str) -> str:
        instruction_lower = instruction.lower()
        for app, hints in self.playbooks.items():
            if app.lower() in instruction_lower:
                return json.dumps(hints)
        return ""

    def log_failure(self, instruction: str, command: str, error_type: str, resolution: str):
        """Stores execution/verification failures with a Unix timestamp for the UI Timeline."""
        entry = {
            "ts": time.time(),
            "instruction": instruction,
            "command": command,
            "error_type": error_type,
            "resolution": resolution
        }
        self.failure_log.append(entry)
        try:
            with open(self.fail_log_file, "w") as f:
                json.dump(self.failure_log, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save failure log: {e}")

    def export_config(self, path: str):
        try:
            data = {
                "rules": [asdict(r) for r in self.rules],
                "playbooks": self.playbooks
            }
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to export config: {e}")

    def import_config(self, path: str):
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    self.rules = [Rule(**r) if isinstance(r, dict) else Rule(text=r) for r in data.get("rules", [])]
                    self.playbooks = data.get("playbooks", {})
                self.save_memory()
            except Exception as e:
                logger.error(f"Failed to import config: {e}")
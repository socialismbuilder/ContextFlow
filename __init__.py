# -*- coding: utf-8 -*-

import sys
import os

# Add lib/ to sys.path for bundled dependencies (edge-tts, aiohttp, etc.)
_lib_path = os.path.join(os.path.dirname(__file__), "lib")
if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)

# Import necessary functions/classes from the refactored modules
# Use relative imports for modules within the same addon package
from .ui import ui_manager
from . import main_logic
from . import api_client
from .card.card_template_manager import update_card_templates
from aqt import gui_hooks

# Initialize the addon:
# 1. Register the configuration menu item
ui_manager.register_menu_item()

# 2. Register the necessary hooks (e.g., card rendering)
main_logic.register_hooks()

# 3. Update saved sentence card templates after profile loads
gui_hooks.profile_did_open.append(lambda: update_card_templates())


print("AI Example Sentences Addon Loaded Successfully (Refactored with Task Queue)")

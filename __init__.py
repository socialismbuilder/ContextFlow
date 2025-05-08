# -*- coding: utf-8 -*-

# -*- coding: utf-8 -*-

# Import necessary functions/classes from the refactored modules
# Use relative imports for modules within the same addon package
from . import ui_manager
from . import main_logic
from . import api_client # Import the task manager

# Initialize the addon:
# 1. Register the configuration menu item
ui_manager.register_menu_item()

# 2. Register the necessary hooks (e.g., card rendering)
main_logic.register_hooks()


print("AI Example Sentences Addon Loaded Successfully (Refactored with Task Queue)")

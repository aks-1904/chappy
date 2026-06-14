import logging

from modules.vision import VisionModule

log = logging.getLogger(__name__)

class WirelessVisionModule(VisionModule):
    def __init__(self, wireless_bridge=None):
        super().__init__()
        self._wireless = wireless_bridge

# Auto-Fallback if no frames after WIRELESS_TIMEOUT    
class AutoVisionModule(WirelessVisionModule):
    pass
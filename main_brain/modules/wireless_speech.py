import logging

from modules.speech import SpeechModule

log = logging.getLogger(__name__)

class WirelessSpeechModule(SpeechModule):
    def __init__(self, wireless_bridge=None):
        super().__init__()
        self._wireless = wireless_bridge
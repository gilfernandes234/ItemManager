from abc import ABC, abstractmethod
from PyQt6.QtCore import QThread, pyqtSignal


class AIThread(QThread):

    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, ai_provider, prompt):
        super().__init__()
        self.ai_provider = ai_provider
        self.prompt = prompt
    
    def run(self):
        try:
            response = self.ai_provider.generate_response(self.prompt)
            self.response_ready.emit(response)
        except Exception as e:
            self.error_occurred.emit(f"Erro: {str(e)}")


class BaseAI(ABC):

    def __init__(self):
        self.api_key = None
        self.model = None
        self.is_connected = False
    
    @abstractmethod
    def connect(self, api_key: str) -> tuple[bool, str]:

        pass
    
    @abstractmethod
    def generate_response(self, prompt: str) -> str:

        pass
    
    @abstractmethod
    def get_available_models(self) -> list[str]:

        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:

        pass
    
    def disconnect(self):
        self.api_key = None
        self.model = None
        self.is_connected = False

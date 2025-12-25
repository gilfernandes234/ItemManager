import google.generativeai as genai
from .base_ai import BaseAI


class GeminiAI(BaseAI):
    """Provedor de IA Google Gemini"""
    
    def __init__(self):
        super().__init__()
        self.model_name = None
    
    def get_provider_name(self) -> str:
        return "Google Gemini"
    
    def connect(self, api_key: str) -> tuple[bool, str]:
        """Conecta ao Google Gemini"""
        try:
            self.api_key = api_key
            genai.configure(api_key=api_key)
            
            # Listar modelos disponíveis
            available_models = self.get_available_models()
            
            if not available_models:
                return False, "Nenhum modelo disponível para generateContent"
            
            # Usar o primeiro modelo disponível
            self.model_name = available_models[0]
            self.model = genai.GenerativeModel(self.model_name)
            self.is_connected = True
            
            return True, f"Conectado ao {self.model_name}"
            
        except Exception as e:
            self.is_connected = False
            return False, f"Erro ao conectar: {str(e)}"
    
    def generate_response(self, prompt: str) -> str:
        """Gera resposta usando o Gemini"""
        if not self.is_connected or not self.model:
            raise Exception("Não conectado ao Gemini. Use connect() primeiro.")
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            raise Exception(f"Erro ao gerar resposta: {str(e)}")
    
    def get_available_models(self) -> list[str]:
        """Retorna modelos Gemini disponíveis"""
        try:
            models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    models.append(m.name)
            return models
        except:
            return []
    
    def set_model(self, model_name: str) -> bool:
        """Troca o modelo sendo usado"""
        try:
            self.model_name = model_name
            self.model = genai.GenerativeModel(model_name)
            return True
        except:
            return False

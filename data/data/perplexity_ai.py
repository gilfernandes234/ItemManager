import os
from openai import OpenAI
from .base_ai import BaseAI

class PerplexityAI(BaseAI):

    def __init__(self):
        super().__init__()
        self.model_name = None
        self.client = None
        
    def get_provider_name(self) -> str:
        return "Perplexity AI"
    
    def connect(self, api_key: str) -> tuple[bool, str]:
        """Conecta ao Perplexity"""
        try:
            self.api_key = api_key
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.perplexity.ai"
            )
            
            # Listar modelos disponíveis
            available_models = self.get_available_models()
            if not available_models:
                return False, "Nenhum modelo disponível"
            
            # Usar o primeiro modelo disponível (sonar)
            self.model_name = available_models[0]
            self.is_connected = True
            
            return True, f"Conectado ao {self.model_name}"
            
        except Exception as e:
            self.is_connected = False
            return False, f"Erro ao conectar: {str(e)}"
    
    def generate_response(self, prompt: str) -> str:

        if not self.is_connected or not self.client:
            raise Exception("Não conectado ao Perplexity. Use connect() primeiro.")
        
        try:
            messages = [
                {
                    "role": "user",
                    "content": prompt,
                }
            ]
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            raise Exception(f"Erro ao gerar resposta: {str(e)}")
    
    def get_available_models(self) -> list[str]:
        return [
            "sonar",
            "sonar-pro",
        ]

    
    def set_model(self, model_name: str) -> bool:
        try:
            available = self.get_available_models()
            if model_name in available:
                self.model_name = model_name
                return True
            return False
        except:
            return False
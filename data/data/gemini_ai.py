from google import genai
from .base_ai import BaseAI


class GeminiAI(BaseAI):
    """Provedor de IA Google Gemini"""
    
    def __init__(self):
        super().__init__()
        self.model_name = None
        self.client = None
    
    def get_provider_name(self) -> str:
        return "Google Gemini"
    
    def connect(self, api_key: str) -> tuple[bool, str]:
        """Conecta ao Google Gemini"""
        try:
            self.api_key = api_key
            self.client = genai.Client(api_key=api_key)
            
            # Listar modelos disponíveis
            available_models = self.get_available_models()
            
            if not available_models:
                # Fallback se a listagem falhar ou retornar vazio
                available_models = ["gemini-1.5-flash", "gemini-1.5-pro"]
                self.model_name = available_models[0]
                self.is_connected = True
                return True, f"Conectado (Fallback: {self.model_name})"
            
            # Usar o primeiro modelo disponível
            self.model_name = available_models[0]
            self.is_connected = True
            
            return True, f"Conectado ao {self.model_name}"
            
        except Exception as e:
            self.is_connected = False
            return False, f"Erro ao conectar: {str(e)}"
    
    def generate_response(self, prompt: str) -> str:
        """Gera resposta usando o Gemini"""
        if not self.is_connected or not self.client:
            raise Exception("Não conectado ao Gemini. Use connect() primeiro.")
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            raise Exception(f"Erro ao gerar resposta: {str(e)}")
    
    def get_available_models(self) -> list[str]:
        """Retorna modelos Gemini disponíveis"""
        try:
            if not self.client:
                return []

            models = []
            # Tenta listar os modelos
            for m in self.client.models.list():
                # Dependendo da versão, a propriedade pode mudar, mas 'name' é comum
                # Filtra apenas modelos 'gemini' e que suportam geração de conteúdo
                full_name = getattr(m, 'name', '')
                display_name = getattr(m, 'display_name', '')
                
                # Simplificação: aceitar qualquer um que tenha 'gemini' no nome
                # O ideal seria verificar supported_generation_methods se disponível
                name_to_check = full_name if full_name else display_name
                if 'gemini' in name_to_check.lower():
                    # Remove 'models/' prefixo se existir para uso na API
                    clean_name = full_name.replace('models/', '')
                    models.append(clean_name)
                    
            return models
        except Exception:
            # Se falhar a listagem, retorna uma lista padrão segura
            return ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro"]
    
    def set_model(self, model_name: str) -> bool:
        """Troca o modelo sendo usado"""
        try:
            self.model_name = model_name
            return True
        except:
            return False

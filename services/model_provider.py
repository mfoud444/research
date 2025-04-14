import os
import g4f
import requests
import openai
from typing import List, Dict, Optional
from datetime import datetime
from config import Config
from utils.retry_decorator import retry
import logging
import time
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseAIService:
    """Base class for AI services with standardized request handling"""
    def __init__(self, config: Dict):
        self.config = config
        self.session = requests.Session()  # Reuse session for all requests
        self._cached_models = None
        self._cache_time = None

    def _make_request(self, method: str, url: str, **kwargs) -> Dict:
        """Standardized request handler with error handling"""
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"API request failed: {str(e)}")
            raise

    def generate_content(self, model: str, prompt: str) -> str:
        raise NotImplementedError

    def get_available_models(self) -> List[str]:
        raise NotImplementedError


class G4FService(BaseAIService):
    """Service for g4f provider with primary model fallback"""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self._available_models = None  # Cache for available models

    def generate_content(self, model: str, prompt: str) -> str:
        """
        Generate content trying the specified model first,
        then fall back to others if needed
        
        Args:
            model: The preferred model to try first
            prompt: The prompt to generate content for
            
        Returns:
            Generated content as string
            
        Raises:
            Exception: If all model attempts fail
        """
        # First try with the requested model
        try:
            response = g4f.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
                timeout=190
            )
            if response:
                return str(response)
            logger.warning(f"Empty response from primary model {model}")
        except Exception as e:
            logger.warning(f"Primary model {model} failed: {str(e)}")

        # If primary model fails, try other available models
        fallback_models = [
            m for m in self.get_available_models() 
            if m != model  # Exclude already-tried primary model
        ]

        for fallback_model in fallback_models:
            try:
                response = g4f.ChatCompletion.create(
                    model=fallback_model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=False,
                    # timeout=30
                )
                if response:
                    logger.info(f"Successfully generated with fallback model {fallback_model}")
                    return str(response)
                logger.warning(f"Empty response from fallback model {fallback_model}")
            except Exception as e:
                logger.warning(f"Fallback model {fallback_model} failed: {str(e)}")
                continue

        raise Exception(f"Failed to generate content after trying {model} and {len(fallback_models)} fallback models")

    def get_available_models(self) -> List[str]:
        """Get available models with caching and priority order"""
        if self._available_models is None:
            try:
                models = sorted(g4f.models._all_models)
                # Prioritize certain models
                for preferred in ['gpt-4o', 'gpt-4', 'claude-2']:
                    if preferred in models:
                        models.remove(preferred)
                        models.insert(0, preferred)
                self._available_models = models
            except Exception as e:
                logger.error(f"Failed to get G4F models, using defaults: {str(e)}")
                self._available_models = ['gpt-4o', 'gpt-4', 'gpt-3.5-turbo', 'llama2-70b', 'claude-2']
        return self._available_models.copy()

class G4FServiceAPI(BaseAIService):
    """Service for local G4F API endpoint"""
    def __init__(self, config: Dict):
        super().__init__(config)
        self.base_url = self.config.get('base_url', "http://localhost:1337/v1")
        self.default_model = self.config.get('default_model', "gpt-4o-mini")
        logger.error(f"G4F API error: {self.base_url}")

    def generate_content(self, model: str, prompt: str) -> str:
        payload = {
            "model": model or self.default_model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}]
        }

        try:
            response = self._make_request(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload
            )
            choices = response.get('choices', [])
            if choices:
                return choices[0].get('message', {}).get('content', '[Empty response]')
            return '[No response content]'
        except Exception as e:
            logger.error(f"G4F API error: {str(e)}")
            raise

    def get_available_models(self) -> List[str]:
        try:
            response = self._make_request("GET", f"{self.base_url}/models")
            return sorted(response.get('data', []))
        except Exception as e:
            logger.error(f"Failed to get G4F API models: {str(e)}")
            return ['gpt-4o-mini', 'gpt-4', 'gpt-3.5-turbo']
        
class HuggingFaceService(BaseAIService):
    """Service for HuggingFace Inference API"""
    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_key = self.config.get('api_key', os.getenv('HUGGINGFACE_API_KEY'))
        self.base_url = self.config.get('api_url', "https://api-inference.huggingface.co/models")

    def generate_content(self, model: str, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": self.config.get('max_tokens', 1000),
                "temperature": self.config.get('temperature', 0.7)
            }
        }

        response = self._make_request(
            "POST",
            f"{self.base_url}/{model}",
            headers=headers,
            json=payload
        )
        return response[0]['generated_text']

    def get_available_models(self) -> List[str]:
        # Maintain your own list or implement pagination for the API
        return [
            "meta-llama/Llama-2-70b-chat-hf",
            "mistralai/Mixtral-8x7B-Instruct-v0.1",
            "google/gemma-7b-it"
        ]


class TogetherAIService(BaseAIService):
    """Service for Together AI API"""
    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_key = self.config.get('api_key', os.getenv('TOGETHER_API_KEY'))
        self.base_url = self.config.get('api_url', "https://api.together.xyz/v1/completions")

    def generate_content(self, model: str, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": self.config.get('max_tokens', 1000),
            "temperature": self.config.get('temperature', 0.7),
            "top_p": self.config.get('top_p', 0.9),
            "stop": self.config.get('stop_sequences', ["</s>"])
        }

        response = self._make_request(
            "POST",
            self.base_url,
            headers=headers,
            json=payload
        )
        return response['choices'][0]['text']

    def get_available_models(self) -> List[str]:
        return [
            "togethercomputer/llama-2-70b-chat",
            "mistralai/Mixtral-8x7B-Instruct-v0.1",
            "togethercomputer/CodeLlama-34b-Instruct"
        ]


class OpenAIService(BaseAIService):
    """Service for OpenAI API with custom base URL support"""
    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_key = self.config.get('api_key', os.getenv('OPENAI_API_KEY'))
        self.base_url = self.config.get('base_url', "https://api.openai.com/v1")
        
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def generate_content(self, model: str, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.get('temperature', 0.7),
                max_tokens=self.config.get('max_tokens', 1000),
                top_p=self.config.get('top_p', 0.9)
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            raise

    def get_available_models(self) -> List[str]:
        if self._should_use_cache():
            return self._cached_models
            
        try:
            models = self.client.models.list()
            self._update_cache([m.id for m in models.data if m.id.startswith('gpt-')])
            return self._cached_models
        except Exception:
            return self._get_fallback_models()

    def _should_use_cache(self) -> bool:
        return self._cached_models and (datetime.now() - self._cache_time).seconds < 3600

    def _update_cache(self, models: List[str]) -> None:
        self._cached_models = sorted(models)
        self._cache_time = datetime.now()

    def _get_fallback_models(self) -> List[str]:
        try:
            models = sorted(g4f.models._all_models)
            if 'gpt-4o' in models:
                models.remove('gpt-4o')
                models.insert(0, 'gpt-4o')
            return models
        except Exception:
            return ['gpt-4o', 'gpt-4', 'gpt-3.5-turbo']


class ModelProvider:
    """Main provider class that routes requests to the configured service"""
    def __init__(self):
        self.service = self._initialize_service()

    def _initialize_service(self) -> BaseAIService:
        provider = Config.AI_PROVIDER.lower()
        provider_config = Config.AI_PROVIDER_CONFIG.get(provider, {})

        service_map = {
            'g4f': G4FService,
            'g4f-api': G4FServiceAPI,
            'huggingface': HuggingFaceService,
            'together': TogetherAIService,
            'openai': OpenAIService
        }

        if provider not in service_map:
            raise ValueError(f"Unsupported AI provider: {provider}")
        
        return service_map[provider](provider_config)

    @retry()
    def generate_content(self, model: str, prompt: str) -> str:
        return self.service.generate_content(model, prompt)

    def generate_index_content(self, model: str, research_subject: str, manual_chapters: List[str] = None) -> str:
        prompt = (f"Generate a detailed index for a research paper about {research_subject} "
                 f"with chapters: {', '.join(manual_chapters)}" if manual_chapters else
                 f"Generate a detailed index for a research paper about {research_subject}")
        return self.generate_content(model, prompt + ". Use markdown format.")

    def get_available_models(self) -> List[str]:
        return self.service.get_available_models()
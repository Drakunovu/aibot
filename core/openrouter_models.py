import os
import time
from typing import Any, Dict, Optional, Set

import aiohttp
from openai import AsyncOpenAI, OpenAIError

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

class OpenRouterModelInfo:
    _instance = None
    _cache: Optional[Dict[str, Any]] = None
    _cache_timestamp: float = 0
    _cache_duration_seconds: int = 3600 * 24
    _system_prompt_support_cache: Dict[str, bool] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OpenRouterModelInfo, cls).__new__(cls)
        return cls._instance

    async def _fetch_models_from_api(self) -> None:
        print("Fetching latest model data from OpenRouter API...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://openrouter.ai/api/v1/models") as response:
                    if response.status == 200:
                        data = await response.json()
                        self._cache = {model['id']: model for model in data.get('data', [])}
                        self._cache_timestamp = time.time()
                        print("Successfully fetched and cached model data.")
        except Exception as e:
            print(f"An exception occurred while fetching model data: {e}")

    async def get_all_models(self) -> Optional[Dict[str, Any]]:
        is_cache_expired = (time.time() - self._cache_timestamp) > self._cache_duration_seconds
        if self._cache is None or is_cache_expired:
            await self._fetch_models_from_api()
        return self._cache

    async def get_model_details(self, model_id: str) -> Optional[Dict[str, Any]]:
        models = await self.get_all_models()
        return models.get(model_id) if models else None

    async def test_system_prompt_support(self, model_id: str) -> bool:
        if model_id in self._system_prompt_support_cache:
            return self._system_prompt_support_cache[model_id]

        print(f"Performing live system prompt test for model: {model_id}...")
        
        test_client = AsyncOpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )
        
        try:
            await test_client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": "Test prompt."},
                    {"role": "user", "content": "Hello."}
                ],
                max_tokens=5
            )
            print(f"Test PASSED for {model_id}. System prompt is supported.")
            self._system_prompt_support_cache[model_id] = True
            return True
        except OpenAIError as e:
            print(f"Test FAILED for {model_id}. System prompt is not supported. Error: {e.status_code}")
            self._system_prompt_support_cache[model_id] = False
            return False
        except Exception as e:
            print(f"An unexpected error occurred during system prompt test for {model_id}: {e}")
            self._system_prompt_support_cache[model_id] = False
            return False

model_info_manager = OpenRouterModelInfo()
import asyncio
import time
import aiohttp
from typing import Dict, Any, Optional, Set

from openai import AsyncOpenAI, OpenAIError
import os

# --- API Credentials ---
# The test call needs its own client and API key.
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

class OpenRouterModelInfo:
    """
    A singleton class to fetch, cache, and provide information about models
    available on OpenRouter.ai. It now performs a live test to check for
    system prompt support.
    """
    _instance = None
    _cache: Optional[Dict[str, Any]] = None
    _cache_timestamp: float = 0
    _cache_duration_seconds: int = 3600 * 24  # Cache model list for 24 hours
    _system_prompt_support_cache: Dict[str, bool] = {} # Caches the result of the live test

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OpenRouterModelInfo, cls).__new__(cls)
        return cls._instance

    async def _fetch_models_from_api(self) -> None:
        """Fetches the complete list of models from the OpenRouter API."""
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
        """Retrieves all models, using a cached version if available."""
        is_cache_expired = (time.time() - self._cache_timestamp) > self._cache_duration_seconds
        if self._cache is None or is_cache_expired:
            await self._fetch_models_from_api()
        return self._cache

    async def get_model_details(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the details for a specific model ID."""
        models = await self.get_all_models()
        return models.get(model_id) if models else None

    async def test_system_prompt_support(self, model_id: str) -> bool:
        """
        Performs a live API call to definitively check if a model supports the
        'system' role. Caches the result.
        """
        # Return cached result if we've already tested this model
        if model_id in self._system_prompt_support_cache:
            return self._system_prompt_support_cache[model_id]

        print(f"Performing live system prompt test for model: {model_id}...")
        
        # Create a temporary client for the test
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
            # If the call succeeds (no exception), it supports system prompts
            print(f"Test PASSED for {model_id}. System prompt is supported.")
            self._system_prompt_support_cache[model_id] = True
            return True
        except OpenAIError as e:
            # If the API returns a 400 error, it likely doesn't support it
            print(f"Test FAILED for {model_id}. System prompt is not supported. Error: {e.status_code}")
            self._system_prompt_support_cache[model_id] = False
            return False
        except Exception as e:
            # For any other error, assume it's not supported to be safe
            print(f"An unexpected error occurred during system prompt test for {model_id}: {e}")
            self._system_prompt_support_cache[model_id] = False
            return False

# Global instance
model_info_manager = OpenRouterModelInfo()
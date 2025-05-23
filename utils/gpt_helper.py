import httpx
from config import YANDEX_FOLDER_ID, YANDEX_API_KEY, AI_PROMPT_STR
from utils import setup_logger

logger = setup_logger(__name__)


async def analyze_text_description(description: str) -> str:
    """Анализирует текстовое описание проблемы через Yandex GPT API."""
    try:
        model_uri = f"gpt://{YANDEX_FOLDER_ID}/yandexgpt"
        logger.info(f"Sending request to Yandex GPT with modelUri: {model_uri}")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                headers={
                    "Authorization": f"Bearer {YANDEX_API_KEY}",
                    "x-folder-id": YANDEX_FOLDER_ID
                },
                json={
                    "modelUri": model_uri,
                    "completionOptions": {
                        "stream": False,
                        "temperature": 0.6,
                        "maxTokens": 500
                    },
                    "messages": [
                        {
                            "role": "user",
                            "text": (
                                f"{AI_PROMPT_STR}"
                                f"Описание: {description}"
                            )
                        }
                    ]
                }
            )
            if response.status_code == 200:
                result = response.json()["result"]["alternatives"][0]["message"]["text"]
                logger.info(f"Yandex GPT response: {result[:100]}")
                return result[:500]  # Ограничиваем длину ответа
            else:
                logger.error(f"Yandex GPT API error: {response.status_code} - {response.text}")
                return f"Анализ текста недоступен (ошибка {response.status_code}). Описание: {description}"
    except Exception as e:
        logger.error(f"Ошибка Yandex GPT API: {str(e)}")
        return f"Анализ текста недоступен. Описание: {description}"
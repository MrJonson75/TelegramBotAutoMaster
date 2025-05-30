import httpx
import base64
import json
from config import YANDEX_FOLDER_ID, YANDEX_API_KEY, AI_PROMPT
from utils import setup_logger

logger = setup_logger(__name__)

async def analyze_images(image_data_list: list, user_comment: str) -> str:
    """Анализирует изображения с помощью Yandex Vision и комментарий с помощью Yandex GPT."""
    if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
        logger.error("YANDEX_API_KEY or YANDEX_FOLDER_ID is missing")
        return await analyze_with_gpt_only(user_comment, "Ошибка: Yandex ключи не настроены.")

    # Шаг 1: Извлечение текста с изображений через Yandex Vision
    text_results = []
    auth_header = {
        "Authorization": f"Api-Key {YANDEX_API_KEY.strip()}",
        "x-folder-id": YANDEX_FOLDER_ID,
        "Content-Type": "application/json"
    }
    logger.info(f"Использование ключа API Yandex: {YANDEX_API_KEY[:4]}...{YANDEX_API_KEY[-4:]}")
    for image_data in image_data_list:
        try:
            logger.info("Обработка изображения с API Yandex Vision")
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            request_body = {
                "folderId": YANDEX_FOLDER_ID,
                "analyze_specs": [
                    {
                        "content": image_base64,
                        "features": [
                            {
                                "type": "TEXT_DETECTION",
                                "text_detection_config": {
                                    "language_codes": ["en", "ru"]
                                }
                            }
                        ]
                    }
                ]
            }
            logger.debug(f"Vision API -запрос тела: {json.dumps(request_body)[:200]}...")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze",
                    headers=auth_header,
                    json=request_body
                )
                logger.debug(f"Статус ответа API Vision: {response.status_code}")
                if response.status_code == 200:
                    result = response.json()
                    logger.debug(f"Ответ API Vision: {json.dumps(result)[:200]}...")
                    text = ""
                    for spec in result.get("results", [])[0].get("results", []):
                        for block in spec.get("textDetection", {}).get("pages", [])[0].get("blocks", []):
                            for line in block.get("lines", []):
                                text += " ".join([entity["text"] for entity in line["words"]]) + " "
                    if text.strip():
                        text_results.append(text.strip())
                        logger.info(f"Обнаруженный текст: {text[:100]}")
                    else:
                        logger.info("Нет текста, обнаруженного на изображении")
                        text_results.append("Текст не распознан")
                else:
                    logger.error(f"Ошибка API API Yandex Vision: {response.status_code} - {response.text}")
                    text_results.append(f"Ошибка Vision API: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Ошибка обработки изображения: {str(e)}")
            text_results.append(f"Ошибка обработки изображения: {str(e)}")

    # Объединяем текст с изображений
    extracted_text = " ".join(text_results)[:200] if text_results else "Текст на изображениях не распознан"

    # Шаг 2: Анализ текста с изображений и комментария через Yandex GPT
    return await analyze_with_gpt_only(user_comment, extracted_text)

async def analyze_with_gpt_only(user_comment: str, extracted_text: str) -> str:
    """Анализирует комментарий и извлечённый текст через Yandex GPT."""
    try:
        if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
            logger.error("Yandex_api_key или yandex_folder_id отсутствует")
            return f"Распознанное фото: {extracted_text}\nАнализ недоступен: Yandex ключи не настроены."
        logger.info("Отправка извлеченного текста и комментария пользователя в Yandex GPT")
        auth_header = {
            "Authorization": f"Api-Key {YANDEX_API_KEY.strip()}",
            "x-folder-id": YANDEX_FOLDER_ID,
            "Content-Type": "application/json"
        }
        prompt = (
            f"{AI_PROMPT}\n"
            f"Текст с изображений: {extracted_text}\n"
            f"Комментарий пользователя: {user_comment if user_comment else 'Нет комментария'}"
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                headers=auth_header,
                json={
                    "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt",
                    "completionOptions": {
                        "stream": False,
                        "temperature": 0.6,
                        "maxTokens": 500
                    },
                    "messages": [
                        {
                            "role": "user",
                            "text": prompt
                        }
                    ]
                }
            )
            if response.status_code == 200:
                gpt_result = response.json()["result"]["alternatives"][0]["message"]["text"]
                logger.info(f"Yandex GPT response: {gpt_result[:100]}")
                combined_result = f"Распознанное фото: {extracted_text}\nАнализ: {gpt_result}"
                return combined_result[:700]
            else:
                logger.error(f"Yandex GPT API error: {response.status_code} - {response.text}")
                return f"Распознанное фото: {extracted_text}\nАнализ недоступен (ошибка {response.status_code})"
    except Exception as e:
        logger.error(f"Ошибка Yandex GPT API: {str(e)}")
        return f"Распознанное фото: {extracted_text}\nАнализ недоступен: {str(e)}"
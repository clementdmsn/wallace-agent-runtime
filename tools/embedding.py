from openai import OpenAI

from config import SETTINGS


# Embedding calls are isolated here because FAISS indexing and future retrieval
# code should not need to know how the OpenAI-compatible backend is configured.
def embed_texts(texts: list[str]) -> list[list[float]]:
    if not isinstance(texts, list) or not texts:
        raise ValueError('texts must be a non-empty list of strings')
    if not all(isinstance(text, str) and text.strip() for text in texts):
        raise ValueError('each text must be a non-empty string')

    client = OpenAI(
            base_url=SETTINGS.base_url,
            api_key=SETTINGS.api_key,
            )
    embedding_model_name = getattr(SETTINGS, 'embedding_model_name', SETTINGS.model_name)
    response = client.embeddings.create(
            model=embedding_model_name,
            input=texts,
            )
    return [item.embedding for item in response.data]

from __future__ import annotations

import pytest

from tools import embedding


def test_embed_texts_rejects_bad_inputs():
    with pytest.raises(ValueError, match='texts must be a non-empty list'):
        embedding.embed_texts([])

    with pytest.raises(ValueError, match='each text must be a non-empty string'):
        embedding.embed_texts(['ok', '   '])


def test_embed_texts_calls_openai_compatible_client(monkeypatch):
    calls = []

    class Item:
        def __init__(self, values):
            self.embedding = values

    class Embeddings:
        def create(self, **kwargs):
            calls.append(kwargs)
            return type('Response', (), {'data': [Item([1.0, 2.0]), Item([3.0, 4.0])]})()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls.append({'client': kwargs})
            self.embeddings = Embeddings()

    monkeypatch.setattr(embedding, 'OpenAI', FakeOpenAI)

    result = embedding.embed_texts(['alpha', 'beta'])

    assert result == [[1.0, 2.0], [3.0, 4.0]]
    assert calls[0]['client']['base_url'] == embedding.SETTINGS.base_url
    assert calls[1]['model'] == embedding.SETTINGS.embedding_model_name
    assert calls[1]['input'] == ['alpha', 'beta']

import pytest

from knowledge_app.reranking import CrossEncoderReranker, validate_scores
from knowledge_app.settings import Settings


def test_reranker_pinning_and_lazy_empty():
    with pytest.raises(ValueError, match="Pin"):
        CrossEncoderReranker(Settings(_env_file=None, reranker_revision="main"))
    model = CrossEncoderReranker(Settings(_env_file=None))
    assert model.score("q", []) == []
    assert model._model is None


@pytest.mark.parametrize(
    "values,count", [([float("nan")], 1), ([float("inf")], 1), ([-0.1], 1), ([1.1], 1), ([], 1)]
)
def test_bad_scores(values, count):
    with pytest.raises(ValueError):
        validate_scores(values, count)

import asyncio
import math
from uuid import UUID

import pytest

from scripts.evaluate_knowledge import Case, aggregate, evaluate, metrics, percentile


def ref(n):
    return {"knowledge_id": str(UUID(int=n)), "revision_id": str(UUID(int=n + 100))}


def case(expected):
    return Case.model_validate(
        {
            "id": "q1",
            "search": {"query": "질문"},
            "expected": expected,
            "forbidden": [ref(9)],
            "split": "dev",
            "origin": "test",
        }
    )


def key(n):
    return tuple(ref(n).values())


def test_rank_metrics_and_revision_identity():
    c = case([ref(1), ref(2)])
    got = metrics(c, [key(8), key(1), key(1), key(9), (key(2)[0], key(8)[1])])
    assert got["recall_at_5"] == 0.5
    assert got["mrr_at_5"] == 0.5
    assert got["ndcg_at_5"] == pytest.approx((1 / math.log2(3)) / (1 + 1 / math.log2(3)))
    assert got["forbidden_hit"] == 1
    ranked = [key(i) for i in range(3, 9)] + [key(1)]
    assert metrics(c, ranked)["recall_at_20"] == 0.5
    assert metrics(c, ranked)["recall_at_5"] == 0


def test_negative_denominators_and_percentile():
    a, b = metrics(case([]), []), metrics(case([ref(1)]), [key(1)])
    report = aggregate([{"metrics": a}, {"metrics": b}])
    assert report["denominators"]["recall_at_5"] == 1
    assert report["metrics"]["no_answer_accuracy"] == 1
    assert metrics(case([]), [key(2)])["false_positive_rate"] == 1
    assert percentile([10, 20], 0.95) == 19.5


class FakeAPI:
    def __init__(self, stale=False, fail=False):
        self.stale, self.fail = stale, fail
        self.searches = 0

    async def request(self, method, path, **kwargs):
        if method == "GET":
            return {
                "revision_id": ref(1)["revision_id"],
                "status": "READY",
                "lifecycle_status": "RETIRED" if self.stale else "ACTIVE",
            }
        if self.fail:
            raise RuntimeError("provider error")
        assert kwargs["json"]["top_k"] == 20
        self.searches += 1
        return {"profile_id": "p1", "min_similarity": 0.28, "items": [ref(1)]}


def test_evaluation_read_only_warmup_and_repeats():
    api = FakeAPI()
    report = asyncio.run(evaluate(api, [case([ref(1)])], 2, 1))
    assert api.searches == 3
    assert report["overall"]["cases"] == 1
    assert len(report["cases"][0]["samples"]) == 2
    assert report["overall"]["metrics"]["recall_at_5"] == 1


@pytest.mark.parametrize("options", [{"stale": True}, {"fail": True}])
def test_failures_are_not_scored_as_empty_results(options):
    with pytest.raises((ValueError, RuntimeError)):
        asyncio.run(evaluate(FakeAPI(**options), [case([ref(1)])], 1, 0))


def test_unlabeled_forbidden_is_not_reported_as_pass():
    c = case([])
    c.forbidden = []
    assert "forbidden_hit" not in metrics(c, [])


class RerankerAPI(FakeAPI):
    async def request(self, method, path, **kwargs):
        result = await super().request(method, path, **kwargs)
        if method == "POST":
            result.update(
                score_type="reranker_sigmoid",
                min_similarity=None,
                reranker={"model": "test", "min_score": 0.5, "candidate_count": 1},
            )
        return result


def test_reranker_report_preserves_config_and_nullable_cosine():
    report = asyncio.run(evaluate(RerankerAPI(), [case([ref(1)])], 1, 0))
    assert report["thresholds"] == [None]
    assert report["ranking_config"]["score_type"] == "reranker_sigmoid"
    assert "candidate_count" not in report["ranking_config"]["reranker"]


def test_cutoff_selection_uses_dev_only():
    from scripts.tune_reranker import tune

    positive, negative = case([ref(1)]), case([])
    negative.id = "negative"
    positive.forbidden = negative.forbidden = []
    report = {
        "ranking_config": {"score_type": "reranker_sigmoid", "reranker": {"min_score": 0}},
        "thresholds": [None],
        "cases": [
            {"id": "q1", "samples": [{"ranked": [key(1)], "scores": [0.02]}]},
            {"id": "negative", "samples": [{"ranked": [key(2)], "scores": [0.0005]}]},
        ],
    }
    result = tune([positive, negative], report)
    assert result["selected_cutoff"] == 0.001
    assert result["test"]["cases"] == 0
    report["ranking_config"]["reranker"]["min_score"] = 0.5
    with pytest.raises(ValueError, match="zero cutoff"):
        tune([positive, negative], report)

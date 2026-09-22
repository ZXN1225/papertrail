import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval_metrics import metrics, reciprocal_rank_fusion  # noqa: E402


class RetrievalMetricsTest(unittest.TestCase):
    def test_metrics_use_first_relevant_rank_and_graded_relevance(self):
        result = metrics(["TEST-X", "TEST-A", "TEST-B"], {"TEST-A": 3, "TEST-B": 1}, 3)
        self.assertEqual(result["hit"], 1.0)
        self.assertEqual(result["mrr"], 0.5)
        self.assertGreater(result["ndcg"], 0.0)
        self.assertLessEqual(result["ndcg"], 1.0)

    def test_rrf_rewards_documents_ranked_by_both_retrievers(self):
        result = reciprocal_rank_fusion([["TEST-A", "TEST-B"], ["TEST-B", "TEST-A"]], constant=0)
        self.assertEqual(result[0][0], "TEST-A")
        self.assertEqual(result[0][1], result[1][1])

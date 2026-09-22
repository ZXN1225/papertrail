import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval_metrics import metrics


class RetrievalMetricsTest(unittest.TestCase):
    def test_metrics_use_first_relevant_rank_and_graded_relevance(self):
        result = metrics(["TEST-X", "TEST-A", "TEST-B"], {"TEST-A": 3, "TEST-B": 1}, 3)
        self.assertEqual(result["hit"], 1.0)
        self.assertEqual(result["mrr"], 0.5)
        self.assertGreater(result["ndcg"], 0.0)
        self.assertLessEqual(result["ndcg"], 1.0)

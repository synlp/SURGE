import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOMEPAGE = ROOT / "docs" / "index.html"


class HomeCaseStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HOMEPAGE.read_text(encoding="utf-8")

    def test_case_study_uses_released_event_series(self):
        self.assertIn("FIFA World Cup 2022", self.html)
        self.assertIn("22,071", self.html)
        self.assertIn("20,783", self.html)
        self.assertIn("243", self.html)
        self.assertIn("16,304", self.html)
        self.assertIn(
            'fetch("live/data/event-details-v1/fifa_world_cup_2022.json")',
            self.html,
        )

    def test_processed_excerpts_are_presented_without_social_chrome(self):
        start = self.html.index('<aside class="case-excerpts"')
        end = self.html.index("</aside>", start)
        excerpts = self.html[start:end]
        self.assertIn("de-identified", excerpts)
        self.assertNotIn("twitter.com", excerpts.lower())
        self.assertNotIn("x.com", excerpts.lower())
        self.assertNotIn("@FIFAWorldCup", excerpts)

    def test_full_event_analysis_is_linked(self):
        self.assertIn(
            "live/event.html?id=fifa_world_cup_2022&amp;return=index.html",
            self.html,
        )


if __name__ == "__main__":
    unittest.main()

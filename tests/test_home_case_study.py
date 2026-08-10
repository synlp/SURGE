import unittest
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOMEPAGE = ROOT / "docs" / "index.html"


class HomeCaseStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HOMEPAGE.read_text(encoding="utf-8")

    def test_carousel_uses_three_released_event_series(self):
        for event_id, title in (
            ("hotset-001", "Copa América 2024 Final"),
            ("hotset-005", "iPhone 16 Launch"),
            ("hotset-049", "Jake Paul vs Mike Tyson"),
        ):
            self.assertIn(f'id: "{event_id}"', self.html)
            self.assertIn(title, self.html)
        self.assertIn("case-carousel-track", self.html)
        self.assertIn("perspective: 1500px", self.html)
        self.assertIn("event-story-card.is-prev", self.html)
        self.assertIn("event-story-card.is-next", self.html)
        self.assertIn("Example event analyses.", self.html)
        self.assertIn("window.setInterval(() => goTo(activeIndex + 1), 10000)", self.html)
        self.assertIn("post-media-link", self.html)
        self.assertIn("assets/event-examples/copa-positive.jpg", self.html)

    def test_each_event_has_sourced_positive_neutral_and_negative_media(self):
        self.assertEqual(self.html.count('tone: "positive"'), 3)
        self.assertEqual(self.html.count('tone: "neutral"'), 3)
        self.assertEqual(self.html.count('tone: "negative"'), 3)
        self.assertEqual(self.html.count('mediaUrl: "https://pbs.twimg.com/'), 9)
        self.assertIn("Positive, neutral, and negative examples", self.html)
        self.assertIn("each thumbnail links to its source post", self.html)

    def test_demo_events_each_exceed_100k_collected_posts(self):
        demo_posts = [int(value) for value in re.findall(r"^\s+posts: (\d+),$", self.html, re.MULTILINE)]
        self.assertEqual(len(demo_posts), 3)
        self.assertTrue(all(value >= 100_000 for value in demo_posts))

    def test_full_event_analysis_is_linked(self):
        self.assertIn(
            'href="live/event.html?id=${encodeURIComponent(demo.id)}&amp;return=index.html"',
            self.html,
        )


if __name__ == "__main__":
    unittest.main()

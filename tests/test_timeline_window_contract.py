import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs/live/event.html"


class TimelineWindowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = PAGE.read_text(encoding="utf-8")

    def test_range_is_anchored_to_event_end_not_selected_point(self):
        self.assertIn("const lastObservedIndex = (event) =>", self.page)
        self.assertIn("const visibleBounds = (event) =>", self.page)
        self.assertIn("const end = fullEvent ? event.points.length : lastObservedIndex(event) + 1;", self.page)
        self.assertNotIn("const end = Math.min(state.index + 1, event.points.length);", self.page)
        self.assertNotIn("const end = Math.min(state.index + 1, replayEvent.points.length);", self.page)

    def test_range_change_resets_selection_to_latest_visible_interval(self):
        handler = self.page.split('document.querySelectorAll("[data-range]")', 1)[1]
        self.assertIn("state.index = lastObservedIndex(event);", handler)

    def test_full_event_label_is_unambiguous(self):
        self.assertIn('data-range="all" aria-pressed="true">Full event</button>', self.page)

    def test_slider_is_limited_to_visible_window(self):
        self.assertIn("els.slider.min = visibleStart;", self.page)
        self.assertIn("els.slider.max = visibleEnd - 1;", self.page)


if __name__ == "__main__":
    unittest.main()

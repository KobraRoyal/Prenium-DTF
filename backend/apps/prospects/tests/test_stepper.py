from django.test import SimpleTestCase

from apps.prospects.stepper import stepper_items_for_step


class ProspectStepperTests(SimpleTestCase):
    def test_step2_marks_prior_complete_and_current(self) -> None:
        items = stepper_items_for_step(2, 4)
        self.assertEqual(len(items), 4)
        self.assertTrue(items[0]["is_complete"])
        self.assertFalse(items[0]["is_current"])
        self.assertTrue(items[1]["is_current"])
        self.assertFalse(items[1]["is_complete"])
        self.assertFalse(items[2]["is_complete"])
        self.assertFalse(items[3]["is_complete"])

    def test_clamps_current_step(self) -> None:
        items = stepper_items_for_step(99, 4)
        self.assertTrue(items[3]["is_current"])

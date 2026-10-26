import unittest


class WorkflowSelectionTest(unittest.TestCase):
    def test_text_only_defaults_to_text2image(self):
        from app.services.workflows import select_workflow

        self.assertEqual(select_workflow(None, None), "text2image")

    def test_image_defaults_to_image2image(self):
        from app.services.workflows import select_workflow

        self.assertEqual(select_workflow(None, "img_abc.png"), "image2image")

    def test_explicit_valid_workflow_wins(self):
        from app.services.workflows import select_workflow

        self.assertEqual(select_workflow("text2image", "img_abc.png"), "text2image")

    def test_rejects_unknown_workflow(self):
        from app.services.workflows import select_workflow

        with self.assertRaises(ValueError):
            select_workflow("bad", None)

    def test_inpaint_no_longer_valid(self):
        from app.services.workflows import select_workflow

        with self.assertRaises(ValueError):
            select_workflow("inpaint", None)


if __name__ == "__main__":
    unittest.main()

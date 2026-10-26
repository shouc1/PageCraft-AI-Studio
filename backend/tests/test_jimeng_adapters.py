import unittest


class JimengAdaptersTest(unittest.TestCase):
    def test_text2image_request_uses_text_generation_action(self):
        from app.services.jimeng_adapters import build_jimeng_request

        request = build_jimeng_request("text2image", "fresh poster", None, "1024 x 1024", 0.6)

        self.assertEqual(request.action, "CVSync2AsyncSubmitTask")
        self.assertEqual(request.version, "2022-08-31")
        self.assertEqual(request.body["req_key"], "t2i_v40_jimeng")
        self.assertEqual(request.body["prompt"], "fresh poster")
        self.assertNotIn("binary_data_base64", request.body)

    def test_image2image_request_requires_input_image(self):
        from app.services.jimeng_adapters import build_jimeng_request

        with self.assertRaises(ValueError):
            build_jimeng_request("image2image", "fresh poster", None, "1024 x 1024", 0.6)

    def test_image2image_request_contains_one_input_image(self):
        from app.services.jimeng_adapters import build_jimeng_request

        request = build_jimeng_request("image2image", "fresh poster", ["abc"], "1024 x 1024", 0.4)

        self.assertEqual(request.body["req_key"], "jimeng_i2i_v30")
        self.assertEqual(request.body["binary_data_base64"], ["abc"])
        self.assertEqual(request.body["scale"], 0.4)

    def test_image2image_request_supports_multiple_reference_images(self):
        from app.services.jimeng_adapters import build_jimeng_request

        request = build_jimeng_request("image2image", "fresh poster", ["a", "b", "c"], "1024 x 1024", 0.4)

        self.assertEqual(request.body["binary_data_base64"], ["a", "b", "c"])

    def test_inpaint_workflow_rejected(self):
        from app.services.jimeng_adapters import build_jimeng_request

        with self.assertRaises(ValueError):
            build_jimeng_request("inpaint", "replace logo", ["abc"], "1024 x 1024", 0.6)


if __name__ == "__main__":
    unittest.main()

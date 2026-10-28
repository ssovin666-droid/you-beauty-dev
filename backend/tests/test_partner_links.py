import unittest
from urllib.parse import parse_qs, urlsplit

from app.services.partner_links import with_telegram_sub1


class PartnerLinksTests(unittest.TestCase):
    def test_adds_telegram_id_to_plain_product_url(self):
        self.assertEqual(
            with_telegram_sub1("https://shop.example/product", 9876543210),
            "https://shop.example/product?sub1=9876543210",
        )

    def test_preserves_encoded_deeplink_and_other_tracking_parameters(self):
        url = (
            "https://track.example/click?campaign=123&"
            "dl=https%3A%2F%2Fshop.example%2Fp%3Fx%3D1%26sub1%3Dnested"
            "&tag=a+b&empty="
        )
        self.assertEqual(with_telegram_sub1(url, 42), url + "&sub1=42")

    def test_replaces_placeholder_and_duplicate_sub1_parameters(self):
        url = "https://track.example/click?sub1={sub1}&a=1&sub1=old"
        result = with_telegram_sub1(url, 42)
        self.assertEqual(parse_qs(urlsplit(result).query), {"a": ["1"], "sub1": ["42"]})

    def test_replaces_encoded_parameter_name(self):
        self.assertEqual(
            with_telegram_sub1("https://track.example/?%73ub1=old", 42),
            "https://track.example/?sub1=42",
        )

    def test_preserves_fragment(self):
        self.assertEqual(
            with_telegram_sub1("https://shop.example/p?a=1#reviews", 42),
            "https://shop.example/p?a=1&sub1=42#reviews",
        )

    def test_reusing_url_does_not_keep_previous_users_id(self):
        first = with_telegram_sub1("https://track.example/click", 42)
        self.assertEqual(
            with_telegram_sub1(first, 99),
            "https://track.example/click?sub1=99",
        )


if __name__ == "__main__":
    unittest.main()

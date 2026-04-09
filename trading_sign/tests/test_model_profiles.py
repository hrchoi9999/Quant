import unittest

from trading_sign.model_profiles import get_model_profile


class ModelProfileTests(unittest.TestCase):
    def test_known_model_uses_expected_profile(self) -> None:
        profile = get_model_profile("S3")
        self.assertEqual(profile.profile_code, "trend_following")
        self.assertEqual(profile.signal_refresh_frequency, "daily_eod")

    def test_unknown_model_falls_back_to_default_profile(self) -> None:
        profile = get_model_profile("UNKNOWN")
        self.assertEqual(profile.profile_code, "fundamental_slow")


if __name__ == "__main__":
    unittest.main()

import unittest

from backend.core.config import settings


class ConfigurationTests(unittest.TestCase):
    def test_current_provider_settings_are_declared(self):
        for name in (
            "GROQ_API_KEY",
            "GROQ_MODEL",
            "DEEPGRAM_API_KEY",
            "ELEVENLABS_API_KEY",
            "ELEVENLABS_VOICE_ID",
            "DEBUG",
        ):
            self.assertTrue(hasattr(settings, name), f"Missing setting: {name}")

    def test_provider_neutral_settings_have_safe_defaults(self):
        from backend.core.config import Settings

        defaults = Settings(_env_file=None)
        self.assertEqual(defaults.LLM_PROVIDER, "groq")
        self.assertEqual(defaults.active_llm_model, defaults.GROQ_MODEL)
        self.assertGreater(defaults.WS_MAX_MESSAGE_BYTES, 0)
        self.assertEqual(defaults.AUDIO_SAMPLE_RATE, 16_000)
        self.assertFalse(defaults.DEBUG)
        self.assertTrue(defaults.MICROSOFT_OAUTH_AUTHORIZE_URL.startswith("https://"))

    def test_production_debug_mode_is_rejected(self):
        from backend.core.config import Settings

        with self.assertRaises(ValueError):
            Settings(_env_file=None, ENVIRONMENT="production", DEBUG=True)

    def test_provider_keys_are_not_emitted_by_baseline_tests(self):
        self.assertIsInstance(settings.GROQ_API_KEY, str)
        self.assertIsInstance(settings.DEEPGRAM_API_KEY, str)
        self.assertIsInstance(settings.ELEVENLABS_API_KEY, str)


if __name__ == "__main__":
    unittest.main()

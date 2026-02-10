"""config/settings.py testleri."""
import os
from unittest.mock import patch


class TestSettings:
    def test_defaults(self):
        """Ortam değişkeni yoksa varsayılan değerler kullanılmalı."""
        with patch.dict(os.environ, {}, clear=True):
            # Re-import to pick up patched env
            import importlib
            import config.settings as mod
            importlib.reload(mod)
            s = mod.Settings()
            assert s.telegram_token == ""
            assert s.anthropic_api_key == ""
            assert "postgresql" in s.database_url

    def test_env_override(self):
        """Ortam değişkenleri ayarlandığında onlar kullanılmalı."""
        env = {
            "TELEGRAM_TOKEN": "test-token-123",
            "ANTHROPIC_API_KEY": "sk-test-key",
            "DATABASE_URL": "postgresql://test/db",
        }
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config.settings as mod
            importlib.reload(mod)
            s = mod.Settings()
            assert s.telegram_token == "test-token-123"
            assert s.anthropic_api_key == "sk-test-key"
            assert s.database_url == "postgresql://test/db"

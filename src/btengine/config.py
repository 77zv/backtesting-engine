"""Configuration loaded from environment / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Oanda v20 REST hosts.
_HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


@dataclass(frozen=True)
class Config:
    """Runtime configuration for data access and caching."""

    api_token: Optional[str]
    account_id: Optional[str]
    environment: str  # "practice" or "live"
    data_dir: Path

    @property
    def host(self) -> str:
        return _HOSTS[self.environment]

    def require_credentials(self) -> None:
        """Raise a clear error if API access is attempted without credentials."""
        if not self.api_token:
            raise RuntimeError(
                "OANDA_API_TOKEN is not set. Copy .env.example to .env and add your "
                "practice-account token (https://www.oanda.com/demo-account/tpa/personal_token)."
            )


def load_config(dotenv_path: Optional[str] = None) -> Config:
    """Load configuration from the environment, reading a .env file if present."""
    load_dotenv(dotenv_path)

    env = os.getenv("OANDA_ENV", "practice").strip().lower()
    if env not in _HOSTS:
        raise ValueError(f"OANDA_ENV must be one of {sorted(_HOSTS)}, got {env!r}")

    data_dir = Path(os.getenv("BT_DATA_DIR", "data")).expanduser()

    return Config(
        api_token=os.getenv("OANDA_API_TOKEN") or None,
        account_id=os.getenv("OANDA_ACCOUNT_ID") or None,
        environment=env,
        data_dir=data_dir,
    )

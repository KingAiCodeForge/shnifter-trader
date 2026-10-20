"""Credentials model and its utilities (ShnifterBB version)."""

import json
from pathlib import Path
from typing import Dict, Optional

from core import constants

class CredentialsLoader:
    """Handles loading and saving credentials for ShnifterBB."""

    @staticmethod
    def load_credentials() -> Optional[Dict[str, str]]:
        settings_path = Path(constants.USER_SETTINGS_PATH)
        if settings_path.exists():
            with settings_path.open('r', encoding='utf-8') as f:
                return json.load(f).get('credentials', {})
        return None

    @staticmethod
    def save_credentials(credentials: Dict[str, str]) -> None:
        settings_path = Path(constants.USER_SETTINGS_PATH)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        data = {'credentials': credentials}
        with settings_path.open('w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

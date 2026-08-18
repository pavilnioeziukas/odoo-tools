from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class OdooConfig:
    url: str
    database: str
    username: str
    api_key: str

    @classmethod
    def from_env(cls) -> "OdooConfig":
        load_dotenv()
        config = cls(
            url=os.getenv("ODOO_URL", "").strip().rstrip("/"),
            database=(os.getenv("ODOO_DATABASE") or os.getenv("ODOO_DB", "")).strip(),
            username=(os.getenv("ODOO_USERNAME") or os.getenv("ODOO_LOGIN", "")).strip(),
            api_key=os.getenv("ODOO_API_KEY", "").strip(),
        )
        missing = [
            name
            for name, value in {
                "ODOO_URL": config.url,
                "ODOO_DATABASE": config.database,
                "ODOO_USERNAME": config.username,
                "ODOO_API_KEY": config.api_key,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError("Trūksta aplinkos parametrų: " + ", ".join(missing))
        return config

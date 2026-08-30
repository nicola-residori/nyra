from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os
import yaml


@dataclass
class RouterSettings:
    host: str = "0.0.0.0"
    port: int = 8090
    database_path: Path = Path("data/logs.db")
    version: str = "0.1.0"
    clarification_timeout_seconds: int = 120
    websocket_queue_size: int = 100
    websocket_heartbeat_seconds: int = 30
    ingress_token: str | None = None

    @classmethod
    def load(cls, config_file: str | None = None):
        data = {}
        if config_file and Path(config_file).exists():
            raw = yaml.safe_load(Path(config_file).read_text()) or {}
            data = raw.get("router", {})
        return cls(
            host=os.getenv("NYRA_ROUTER_HOST", data.get("host", "0.0.0.0")),
            port=int(os.getenv("NYRA_ROUTER_PORT", data.get("port", 8090))),
            database_path=Path(os.getenv("NYRA_ROUTER_DB", data.get("database_path", "data/logs.db"))),
            version=os.getenv("NYRA_ROUTER_VERSION", data.get("version", "0.1.0")),
            clarification_timeout_seconds=int(os.getenv(
                "NYRA_CLARIFICATION_TIMEOUT_SECONDS", data.get("clarification_timeout_seconds", 120)
            )),
            websocket_queue_size=int(os.getenv(
                "NYRA_WEBSOCKET_QUEUE_SIZE", data.get("websocket_queue_size", 100)
            )),
            websocket_heartbeat_seconds=int(os.getenv(
                "NYRA_WEBSOCKET_HEARTBEAT_SECONDS", data.get("websocket_heartbeat_seconds", 30)
            )),
            ingress_token=os.getenv("NYRA_ROUTER_INGRESS_TOKEN", data.get("ingress_token")),
        )

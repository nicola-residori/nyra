from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os, yaml

@dataclass
class RouterSettings:
    host: str="0.0.0.0"
    port: int=8090
    database_path: Path=Path("data/logs.db")
    version: str="0.1.0"

    @classmethod
    def load(cls, config_file: str | None=None):
        data={}
        if config_file and Path(config_file).exists():
            raw=yaml.safe_load(Path(config_file).read_text()) or {}; data=raw.get("router",{})
        return cls(host=os.getenv("NYRA_ROUTER_HOST",data.get("host","0.0.0.0")),
                   port=int(os.getenv("NYRA_ROUTER_PORT",data.get("port",8090))),
                   database_path=Path(os.getenv("NYRA_ROUTER_DB",data.get("database_path","data/logs.db"))),
                   version=os.getenv("NYRA_ROUTER_VERSION",data.get("version","0.1.0")))

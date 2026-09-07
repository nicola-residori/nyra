from dataclasses import dataclass
import os
@dataclass
class AdminSettings:
    host:str="0.0.0.0"; port:int=80; router_url:str="http://127.0.0.1:8090"; version:str="0.1.0"; router_token:str|None=None
    @classmethod
    def load(cls):
        return cls(
            host=os.getenv("NYRA_ADMIN_HOST","0.0.0.0"),
            port=int(os.getenv("NYRA_ADMIN_PORT","80")),
            router_url=os.getenv("NYRA_ROUTER_URL","http://127.0.0.1:8090"),
            version=os.getenv("NYRA_ADMIN_VERSION","0.1.0"),
            router_token=os.getenv("NYRA_ROUTER_INGRESS_TOKEN") or None,
        )

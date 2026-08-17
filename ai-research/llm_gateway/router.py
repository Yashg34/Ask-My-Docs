import os
import logging
import warnings
import os

logging.getLogger('LiteLLM').setLevel(logging.ERROR)
os.environ["LITELLM_LOG"] = "ERROR"

warnings.filterwarnings("ignore", category=DeprecationWarning)

import yaml
from litellm import Router

with open("llm_gateway/litellm_config.yaml", "r") as file:
    config = yaml.safe_load(file)

llm_router = Router(
    model_list=config["model_list"],
    fallbacks=config.get("router_settings", {}).get("fallbacks", [])
)

print("🚀 LiteLLM Gateway Initialized with Fallbacks (Caching Disabled)!")
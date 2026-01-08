#!usr/bin/env python
# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

load_dotenv()


# 大模型配置
LLM_CONFIG = {
    "model_name": os.getenv("model_name"),
    "api_key": os.getenv("model_api_key"),
    "base_url": os.getenv("model_api_base"),
    "model_type":os.getenv("model_type")
}
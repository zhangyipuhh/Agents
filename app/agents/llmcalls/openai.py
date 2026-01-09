#!usr/bin/env python
# -*- coding: utf-8 -*-
from langchain_openai import ChatOpenAI

def create_model(model_name: str, api_key: str, temperature: float = 0,base_url: str = None):
    return ChatOpenAI(model_name=model_name, api_key=api_key, temperature=temperature,base_url=base_url)

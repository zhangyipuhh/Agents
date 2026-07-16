# -*- coding:utf-8 -*-
"""
邮件系统共享模块。

包含：
- ``email_models``：Pydantic 模型（SMTP 配置 / 策略 / 发送请求）
- ``email_config_service``：配置服务层（SMTP 配置 CRUD + 策略 CRUD + Fernet 加解密）
- ``email_service``：核心发送服务层（与 FastAPI 解耦，脚本可直接调用）
"""

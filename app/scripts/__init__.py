# -*- coding:utf-8 -*-
"""
脚本调度系统包。

提供 ``@register_script`` 装饰器与 ``ScriptContext`` 契约，
让普通 Python 异步函数能被定时任务调度器复用。

设计要点：
    * 脚本元数据由代码定义（``@register_script``），扫描时反射加载到内存 registry
    * 脚本契约：``async def run(context: ScriptContext) -> str``
    * 与智能体任务共用 ``agent_task_schedules`` 表，通过 ``target_type='script'`` 区分
"""

"""临时测试 MapTools 模块中 set_map_center 的实际类型"""
from app.shared.tools.skills.map_agent import MapTools

print("=== set_map_center ===")
print("type:", type(MapTools.set_map_center).__name__)
print("has name:", hasattr(MapTools.set_map_center, "name"))
print("has description:", hasattr(MapTools.set_map_center, "description"))
print("repr:", repr(MapTools.set_map_center)[:300])
print()
print("=== save_business_info ===")
print("type:", type(MapTools.save_business_info).__name__)
print("has description:", hasattr(MapTools.save_business_info, "description"))
if hasattr(MapTools.save_business_info, "description"):
    print("description:", repr(MapTools.save_business_info.description)[:200])

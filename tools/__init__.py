import importlib
import pkgutil

def load_tools():
    tool_registry = {}

    # Dynamically import all modules in the 'tools' package
    for _, module_name, _ in pkgutil.iter_modules(__path__):
        mod = importlib.import_module(f".{module_name}", package=__name__)
        if hasattr(mod, "tool"):
            tool_func_name = mod.tool['function'].__name__
            tool_registry[tool_func_name] = mod.tool

    return tool_registry

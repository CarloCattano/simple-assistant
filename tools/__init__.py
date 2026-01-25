import importlib
import pkgutil

def load_tools():
    tool_registry = {}

    for _, module_name, _ in pkgutil.iter_modules(__path__):
        mod = importlib.import_module(f".{module_name}", package=__name__)

        if not hasattr(mod, "tool"):
            continue

        # Check if tool is a dictionary
        if isinstance(mod.tool, dict) and "function" in mod.tool:
            # Use the 'name' field as the registry key if present
            tool_name = mod.tool.get('name') or mod.tool['function'].__name__
            tool_registry[tool_name] = mod.tool
        elif callable(mod.tool):
            # If the tool is just a function, wrap it in a dict
            func_name = mod.tool.__name__
            tool_registry[func_name] = {
                "name": func_name,
                "function": mod.tool,
                "triggers": []
            }
        else:
            print(f"Warning: {module_name}.tool is neither dict nor function, skipping.")

    return tool_registry


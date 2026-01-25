
import services.ollama_tools as ollama_tools
import asyncio

async def run_tool_direct_async(tool_identifier, parameters=None, tldr_separate=False, history=None):
	if history is None:
		history = []
	# call_tool_with_tldr expects: (tool_name, tool_callable, history, tldr_separate, **arguments)
	# We need to resolve the tool entry and callable
	resolved = ollama_tools.resolve_tool_identifier(tool_identifier)
	if not resolved:
		return None
	tool_name, entry = resolved
	tool_callable = entry.get("function")
	if not tool_callable:
		return None
	# call_tool_with_tldr is sync, so run in executor
	loop = asyncio.get_event_loop()
	return await loop.run_in_executor(
		None,
		lambda: ollama_tools.call_tool_with_tldr(
			tool_name, tool_callable, history, tldr_separate, **(parameters or {})
		),
	)

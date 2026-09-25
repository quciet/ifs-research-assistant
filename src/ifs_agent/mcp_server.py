from __future__ import annotations
import asyncio
import json
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from .tools import ToolService, CATALOG


async def serve(config, artifacts):
    service=ToolService(config,artifacts)
    server=Server('ifs-research-assistant')

    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in CATALOG]

    @server.call_tool()
    async def call_tool(name, arguments):
        # Only trusted, registered Python functions; no eval/exec or arbitrary paths.
        result=await asyncio.to_thread(service.call,name,arguments)
        return [TextContent(type='text',text=json.dumps(result,ensure_ascii=False,default=str,allow_nan=False))]

    async with stdio_server() as (read,write):
        await server.run(read,write,server.create_initialization_options())

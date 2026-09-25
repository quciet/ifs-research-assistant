from __future__ import annotations
import argparse
import asyncio
from pathlib import Path


def main(argv=None):
    p=argparse.ArgumentParser(description='Local IFs chat and MCP tools; does not execute IFs')
    p.add_argument('--project',default=str(Path(__file__).resolve().parents[2]))
    sub=p.add_subparsers(dest='command',required=True)
    ui=sub.add_parser('ui'); ui.add_argument('--port',type=int,default=8765)
    mcp=sub.add_parser('mcp'); mcp.add_argument('--config')
    index=sub.add_parser('index');index.add_argument('--config');index.add_argument('--semantic',action='store_true');index.add_argument('--download-model',action='store_true')
    args=p.parse_args(argv); project=Path(args.project).resolve()
    if args.command=='index':
        import json
        from ifs_research.service import Research
        from ifs_research.structure import StructureStore
        from ifs_research.retrieval import RetrievalStore
        r=Research(args.config or project/'resources/research.json')
        print(json.dumps(r.code.index(r.config.code_root)))
        print(json.dumps(StructureStore(r.code).build()))
        store=RetrievalStore(r)
        print(json.dumps(store.prepare(download=args.download_model,progress=lambda x:print(json.dumps(x),flush=True)) if args.semantic else {'corpus':store.build()}))
    elif args.command=='mcp':
        from .mcp_server import serve
        asyncio.run(serve(args.config or project/'resources/research.json',project/'workspace/agent/mcp-artifacts'))
    else:
        from .webapp import Application,make_server
        app=Application(project); server=make_server(app,args.port)
        print(f'IFs Research Assistant: http://127.0.0.1:{server.server_port}',flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: app.cancel('Application closed'); server.server_close()
    return 0

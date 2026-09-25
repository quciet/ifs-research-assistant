# Source package

`ifs_analysis` contains the results reader, local Parquet compatibility worker, deterministic analyses, provenance jobs, and CLI. It is installed editable into the project `.venv`.

Core Python functions are independent of model providers, UI, and MCP. The compatibility worker is an internal data-decoding process, not an arbitrary-code execution service.

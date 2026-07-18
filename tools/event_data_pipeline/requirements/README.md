# Dependency profiles

The core conversion, aggregation and validation pipeline uses only Python 3.11+
standard-library modules. Install the project with `pip install -e .`.

- Remote SSH/SFTP tools: `pip install -e .[remote]`.
- GPU sentiment worker: use Linux and the project-specific CUDA environment,
  then install/verify the exact versions in `gpu-server.lock.txt`.

The GPU lock records the environment that produced the validated 441,631-row
run. It is not a request to modify a shared model directory or system Python.

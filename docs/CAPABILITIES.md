# Optional prerequisite discovery

Run this diagnostic in the environment where you intend to run SpatialMind:

```sh
python -m spatialmind.capabilities --json
```

The command prints one JSON object and exits 0 if discovery completes.
`--json` is optional; JSON is the only output format. Missing prerequisites
are diagnostic results, not command failures. Unknown CLI arguments exit 2.

This is a read-only discovery check of the **current execution runtime**, not
a scan of your personal computer or a model benchmark. It does not save a report.
It uses the Python standard library and does not import PyTorch or OpenCV,
execute GPU utilities, allocate model/GPU memory, download weights, inspect
private media, or access the network.

| Field | Interpretation |
| --- | --- |
| `python_version` | Python version running this command |
| `logical_cpu_count` | OS-reported logical CPU count, or null if unavailable; not a performance estimate or guaranteed CPU quota |
| `platform` | OS family and machine architecture; no hostname |
| `total_ram_bytes` | OS-reported physical RAM, or null when unavailable; not free memory or a container limit |
| `module_discovery` | `torch` and `cv2`: `found`, `missing`, or `unknown` if import-spec discovery fails |
| `nvidia_smi_on_path` | Whether the command name is discoverable on PATH; it is not executed |
| `inference_readiness` | Always `unverified`; discovery cannot establish model feasibility |
| `checkpoint_authorization` | Always `unverified`; no checkpoint is accessed |
| `model_revision`, `input_resolution`, `throughput_fps` | Null: no model selected, input inspected or throughput measured |

The RAM figure may describe host physical memory rather than the container's
usable allocation. Do not use it as a model-fit guarantee.

A discoverable Python package might fail to import or have incompatible native
dependencies. A discoverable `nvidia-smi` command does not prove that it runs,
that a GPU is accessible, or that CUDA works. Its absence does not prove no GPU
hardware exists: other GPU vendors, missing tools and container restrictions
remain possible. Search paths, executable paths and discovery exception details
are intentionally omitted from output.

## Model feasibility gate

This utility checks only prerequisite discoverability. Model integration still
requires independently verified runtime/device access, sufficient available
memory, an authorized checkpoint with a pinned revision, compatible dependencies,
and an approved input clip. Checkpoint permissions, available VRAM, resolution,
throughput and numerical results are not established by this command.

Do not interpret `found` as a passed inference gate. Record actual blockers and
future measured results in the project tracker, not as invented benchmark output.
The offline replay, storage and synthetic test paths remain useful without the
optional inference stack.

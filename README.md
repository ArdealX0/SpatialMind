# SpatialMind

Where was the blue bottle last seen? SpatialMind is a workbench video-memory project. Its first release stores timestamped observations and retrieves the latest sighting of an object with a video reference. Later milestones will derive those observations from video and test how well identity survives occlusions.

## Run the first slice

From this directory, using Python 3.11 or newer, no dependencies or GPU required:

```sh
python -m spatialmind --db workbench.sqlite ingest examples/workbench.jsonl
python -m spatialmind --db workbench.sqlite last-seen bottle_01
python -m spatialmind --db workbench.sqlite history bottle_01 --video workbench_demo
python -m unittest discover -s tests -v
```

The JSONL fixture is synthetic: object IDs, labels, zones and timestamps are supplied as input. The result describes the last recorded observation, not a prediction of the object's current position. No camera, learned detector or re-identification model is wired in yet.

See [30-day roadmap](docs/ROADMAP.md), [observation contract](docs/OBSERVATIONS.md), and [security checklist](SECURITY.md).

from typing import Callable, List, Dict, Any, Optional
import threading
import json
import traceback
import numpy as np
from pydantic import BaseModel
from fastapi import FastAPI, Query
from collections import deque
from tempfile import TemporaryDirectory
from iohub.ngff import open_ome_zarr
import uvicorn
import os 
app = FastAPI()

class WorkflowContext:
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.should_stop = False
        self.current_step_index = 0
        self.event_listeners: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self.objects: Dict[str, Any] = {}  # Storage for arbitrary objects
    
    def set_object(self, key: str, obj: Any):
        self.objects[key] = obj
    
    def get_object(self, key: str) -> Any:
        return self.objects.get(key)
    
    def remove_object(self, key: str):
        if key in self.objects:
            del self.objects[key]

    def store_step_result(self, step_id: str, metadata: Dict[str, Any]):
        self.data[step_id] = metadata

    def get_step_result(self, step_id: str) -> Optional[Dict[str, Any]]:
        return self.data.get(step_id)

    def update_metadata(self, step_id: str, key: str, value: Any):
        if step_id not in self.data:
            self.data[step_id] = {}
        self.data[step_id][key] = value

    def on(self, event_name: str, callback: Callable[[Dict[str, Any]], None]):
        self.event_listeners.setdefault(event_name, []).append(callback)

    def emit_event(self, event_name: str, payload: Dict[str, Any]):
        for cb in self.event_listeners.get(event_name, []):
            cb(payload)

    def request_stop(self):
        self.should_stop = True


class WorkflowStep:
    def __init__(
        self,
        name: str,
        main_func: Callable[..., Any],
        main_params: Dict[str, Any],
        step_id: str,
        pre_funcs: Optional[List[Callable[..., Any]]] = None,
        pre_params: Optional[Dict[str, Any]] = None,
        post_funcs: Optional[List[Callable[..., Any]]] = None,
        post_params: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.main_func = main_func
        self.main_params = main_params
        self.step_id = step_id
        self.pre_funcs = pre_funcs or []
        self.pre_params = pre_params or {}
        self.post_funcs = post_funcs or []
        self.post_params = post_params or {}
        # Allowing retries handling (if provided in main_params)
        self.max_retries = self.main_params.pop("max_retries", 0)

    def run(self, context: WorkflowContext):
        if context.should_stop:
            return None  # Don't run if stop requested

        # Merge params for pre and post functions
        # We'll pass metadata and context, plus pre/post_params
        # This lets pre/post funcs accept flexible arguments
        metadata = {
            "step_id": self.step_id,
            **self.main_params,
        }

        # Emit event before step starts
        context.emit_event("progress", {"status": "started", "step_id": self.step_id, "name": self.name})

        # Run pre-processing functions
        metadata["pre_result"] = []
        for f in self.pre_funcs:
            # Merge context, metadata and pre_params
            merged_pre_params = {**self.pre_params, "context": context, "metadata": metadata}
            result = f(**merged_pre_params)
            metadata["pre_result"].append(result)
            if context.should_stop:
                return None

        # Run main function with error handling and retries
        retries = self.max_retries
        while True:
            try:
                result = self.main_func(**self.main_params)
                metadata["result"] = result
                break
            except Exception as e:
                metadata["error"] = str(e)
                metadata["traceback"] = traceback.format_exc()
                if retries > 0:
                    retries -= 1
                    # Optionally emit event about retry
                    context.emit_event("progress", {"status": "retrying", "step_id": self.step_id})
                else:
                    # No more retries, stop workflow or handle gracefully
                    context.should_stop = True
                    context.store_step_result(self.step_id, metadata)
                    context.emit_event("progress", {"status": "failed", "step_id": self.step_id})
                    return None

        # Run post-processing functions
        metadata["post_result"] = []
        for f in self.post_funcs:
            merged_post_params = {**self.post_params, "context": context, "metadata": metadata}
            result = f(**merged_post_params)
            metadata["post_result"].append(result)
            if context.should_stop:
                return None

        # Store final metadata in the context
        context.store_step_result(self.step_id, metadata)

        # Emit event that step completed
        context.emit_event("progress", {"status": "completed", "step_id": self.step_id, "name": self.name})
        return metadata["result"]

class Workflow:
    def __init__(self, steps: List[WorkflowStep]):
        self.steps = steps

    def run(self, context: Optional[WorkflowContext] = None):
        # Either use the given context or create a new one
        context = context or WorkflowContext()

        # Resume from current_step_index if previously stopped
        for i in range(context.current_step_index, len(self.steps)):
            step = self.steps[i]
            if context.should_stop:
                break
            step.run(context)
            context.current_step_index = i + 1  # Update progress for resume

        return context

    def run_in_background(self, context: Optional[WorkflowContext] = None):
        # Run workflow in a background thread
        t = threading.Thread(target=self.run, args=(context,))
        t.start()
        return t

# Example device functions
def move_stage(x: float, y: float, z: float = 0.0):
    print(f"Moving stage to X={x}, Y={y}, Z={z}")
    return (x, y, z)

def autofocus(context: WorkflowContext, metadata: Dict[str, Any]):
    print("Performing autofocus...")
    metadata["autofocus_done"] = True

def save_data(context: WorkflowContext, metadata: Dict[str, Any]):
    print(f"Saving data for step {metadata['step_id']}")
    context.update_metadata(metadata["step_id"], "saved", True)

def set_laser_power(power: float, channel: str):
    print(f"Setting laser power to {power} for channel {channel}")
    return power

def acquire_frame(channel: str):
    print(f"Acquiring frame on channel {channel}")
    frame = np.random.rand(512, 512)
    return frame

def process_data(context: WorkflowContext, metadata: Dict[str, Any]):
    print(f"Processing data for step {metadata['step_id']}...")
    metadata["processed"] = True

def save_frame(context: WorkflowContext, metadata: Dict[str, Any]):
    print(f"Saving frame for step {metadata['step_id']}...")
    metadata["frame_saved"] = True
    
def save_frame_zarr(context: "WorkflowContext", metadata: Dict[str, Any]):
    # Retrieve the Zarr writer and write the tile
    zarr_writer = context.get_object("zarr_writer")
    if zarr_writer is None:
        print("No Zarr writer found in context!")
        return
    img = metadata["result"]
    # Compute tile indices (row/col) from metadata
    # This depends on how we map x,y coordinates to grid indices
    col = context.data.get("global", {}).get("last_col")
    row = context.data.get("global", {}).get("last_row")
    if col is not None and row is not None:
        metadata["IndexX"] = col
        metadata["IndexY"] = row    
    print(f"Saving frame tile at row={row}, column={col}")
    zarr_writer["tiles"].write_tile(img, row, col)
    metadata["frame_saved"] = True
    
def wait_time(seconds: int, context: WorkflowContext, metadata: Dict[str, Any]):
    import time
    time.sleep(seconds)
    metadata["waited"] = seconds
    
def addFrametoFile(frame:np.ndarray, context: WorkflowContext, metadata: Dict[str, Any]):
    print(f"Adding frame to file for step {metadata['step_id']}...")
    metadata["frame_added"] = True
    
def append_data(context: WorkflowContext, metadata: Dict[str, Any]):
    obj = context.get_object("data_buffer")
    if obj is not None:
        obj.append(metadata["result"])

def compute_scan_positions(x_min, x_max, y_min, y_max, x_step, y_step):
    # Compute a grid of (x,y) positions
    xs = [x_min + i * x_step for i in range(int((x_max - x_min) / x_step) + 1)]
    ys = [y_min + j * y_step for j in range(int((y_max - y_min) / y_step) + 1)]
    return xs, ys

def close_zarr(context: WorkflowContext, metadata: Dict[str, Any]):
    zarr_writer = context.get_object("zarr_writer")
    if zarr_writer is not None:
        zarr_writer.close()
        context.remove_object("zarr_writer")
        metadata["zarr_closed"] = True

########################################
# Histo-Slide Scanner Interface
########################################

class ScanParameters(BaseModel):
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    x_step: float = 100.0
    y_step: float = 100.0
    autofocus: bool = False
    channel: str = "Mono"
    tile_shape: List[int] = [512, 512]
    dtype: str = "uint16"
    

@app.get("/start_histo_scan")
def start_histo_scan(
    x_min: float = Query(...),
    x_max: float = Query(...),
    y_min: float = Query(...),
    y_max: float = Query(...),
    x_step: float = Query(100.0),
    y_step: float = Query(100.0),
    autofocus_on: bool = Query(False),
    channel: str = Query("Mono")
):
    # Compute the scan positions
    xs, ys = compute_scan_positions(x_min, x_max, y_min, y_max, x_step, y_step)

    # Setup Zarr store
    tmp_dir = TemporaryDirectory()
    store_path = os.path.join(tmp_dir.name, "tiled.zarr")
    print("Zarr store path", store_path)
    
    # Let's assume single channel "Mono" for simplicity, but can adapt for more.
    dataset = open_ome_zarr(store_path, layout="tiled", mode="a", channel_names=[channel])
    # Calculate grid shape based on the number of xy positions
    grid_shape = (len(ys), len(xs))
    tile_shape = (512, 512)  # or from query
    dtype = "uint16"
    tiles = dataset.make_tiles("tiled_raw", grid_shape=grid_shape, tile_shape=tile_shape, dtype=dtype)

    # Create workflow steps
    # Autofocus mode:
    # if autofocus_on == True: run autofocus before every XY move
    # else no autofocus pre-func
    pre_for_xy = [autofocus] if autofocus_on else []

    workflowSteps = []
    step_id = 0
    # We'll add a small function that updates metadata with tile indices for saving
    def update_tile_indices(context: WorkflowContext, metadata: Dict[str, Any]):
        # Based on metadata["x"] and metadata["y"], find their indices in xs, ys
        x_val = metadata["x"]
        y_val = metadata["y"]
        col = xs.index(x_val)
        row = ys.index(y_val)
        # Store indices so save_frame can use them
        metadata["IndexX"] = col
        metadata["IndexY"] = row
        context.update_metadata("global", "last_col", col)
        context.update_metadata("global", "last_row", row)

    # In this simplified example, we only do a single Z position (z=0)
    # and a single frame per position. You can easily extend this.
    z = 0
    frames = [0]  # single frame index for simplicity

    for y_i, y_pos in enumerate(ys):
        for x_i, x_pos in enumerate(xs):
            # Move XY
            workflowSteps.append(WorkflowStep(
                name=f"Move XY to ({x_pos}, {y_pos})",
                main_func=move_stage,
                main_params={"x": x_pos, "y": y_pos, "z": 0},
                step_id=str(step_id),
                pre_funcs=pre_for_xy,
                post_funcs=[update_tile_indices]
            ))
            step_id += 1

            # Move Z (we keep fixed z=0 here for simplicity)
            workflowSteps.append(WorkflowStep(
                name=f"Move Z to {z}",
                step_id=str(step_id),
                main_func=move_stage,
                main_params={"x": x_pos, "y": y_pos, "z": z},
                pre_funcs=[],
                post_funcs=[update_tile_indices]
            ))
            step_id += 1

            # Set laser power (arbitrary, could be parameterized)
            workflowSteps.append(WorkflowStep(
                name=f"Set laser power",
                step_id=str(step_id),
                main_func=set_laser_power,
                main_params={"power": 10, "channel": channel},
                pre_funcs=[],
                post_funcs=[]
            ))
            step_id += 1

            for fr in frames:
                # Acquire frame with a short wait, process data, and save frame
                workflowSteps.append(WorkflowStep(
                    name=f"Acquire frame {channel}",
                    step_id=str(step_id),
                    main_func=acquire_frame,
                    main_params={"channel": channel},
                    pre_funcs=[wait_time],
                    pre_params={"seconds": .1},
                    post_funcs=[process_data, save_frame_zarr],
                ))
                step_id += 1
    
    # Close Zarr dataset at the end
    workflowSteps.append(WorkflowStep(
        name="Close Zarr dataset",
        step_id=str(step_id),
        main_func=close_zarr,
        main_params={},
    ))

    # Create a workflow and context
    wf = Workflow(workflowSteps)
    context = WorkflowContext()
    # Insert the zarr writer object into context so `save_frame` can use it
    context.set_object("zarr_writer", {"tiles": tiles})
    context.set_object("data_buffer", deque())  # example if needed
    context.on("progress", lambda payload: print("Progress:", payload))
    # Run the workflow
    context = wf.run_in_background(context)

    # questions
    # How can I pause a running thread? 
    # we would need a handle on the running thread to pause it
    # We should not run yet another workflow and wait for the first one to finish
    

    # Return the store path to the client so they know where data is stored
    return {"status": "completed", "zarr_store_path": store_path}#, "results": context.data}

uvicorn.run(app, host="localhost", port=8000)

# With a properly structured JSON config, you can load various workflows dynamically. 
# This addresses automating workflow generation for different imaging applications.

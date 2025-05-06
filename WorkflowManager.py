from typing import Callable, List, Dict, Any, Optional
import threading
import json
import traceback
import numpy as np

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
    row = metadata.get("IndexY", 0)
    column = metadata.get("IndexX", 0)
    print(f"Saving frame tile at row={row}, column={column}")
    zarr_writer["tiles"].write_tile(img, row, column)
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

# Example: Dynamically generate a workflow
x_positions = [0, 10]
y_positions = [0, 10]
z_positions = [0, 5]
channels = ["Brightfield", "GFP"]
frames = range(2)
workflowSteps = []

mFile = []

for x in x_positions:
    for y in y_positions:
        # Move XY with autofocus pre and save_data post
        workflowSteps.append(WorkflowStep(
            name=f"Move XY to ({x}, {y})",
            main_func=move_stage,
            main_params={"x": x, "y": y, "z": 0},
            step_id=str(len(workflowSteps)),
            pre_funcs=[autofocus],
            post_funcs=[save_data]
        ))

        for z in z_positions:
            workflowSteps.append(WorkflowStep(
                name=f"Move Z to {z}",
                step_id=str(len(workflowSteps)),
                main_func=move_stage,
                main_params={"x": x, "y": y, "z": z},
                pre_funcs=[],
                post_funcs=[]
            ))
            for ch in channels:
                workflowSteps.append(WorkflowStep(
                    name=f"Set laser power for {ch}",
                    step_id=str(len(workflowSteps)),
                    main_func=set_laser_power,
                    main_params={"power": 10, "channel": ch},
                    pre_funcs=[],
                    post_funcs=[]
                ))
                for fr in frames:
                    workflowSteps.append(WorkflowStep(
                        name=f"Acquire frame {ch}",
                        step_id=str(len(workflowSteps)),
                        main_func=acquire_frame,
                        main_params={"channel": ch},
                        pre_funcs=[wait_time],
                        pre_params={"seconds": 1},
                        post_funcs=[process_data, save_frame, append_data]
                    ))

# Example event listener: print progress events
def progress_listener(event_data):
    print(f"EVENT: {event_data}")

wf = Workflow(workflowSteps)
context = WorkflowContext()
context.on("progress", progress_listener)

# Set a generic object (like a list) into context
context.set_object("data_buffer", [])

# Running normally
context = wf.run(context)
print("Workflow results:", context.data)

all_frames = context.get_object("data_buffer")
# Example: If we wanted to stop the workflow halfway:
# context.request_stop()

# Example: Running in the background:
# background_thread = wf.run_in_background(context)


# Example of automating workflow creation from a config file:
function_registry = {
    "move_stage": move_stage,
    "autofocus": autofocus,
    "save_data": save_data,
    "set_laser_power": set_laser_power,
    "acquire_frame": acquire_frame,
    "process_data": process_data,
    "save_frame": save_frame
}

def load_workflow_from_config(config_path: str) -> Workflow:
    with open(config_path, 'r') as f:
        config = json.load(f)

    steps = []
    for step_def in config["steps"]:
        pre_funcs = [function_registry[p] for p in step_def.get("pre_funcs", [])]
        post_funcs = [function_registry[p] for p in step_def.get("post_funcs", [])]
        steps.append(WorkflowStep(
            name=step_def["name"],
            main_func=function_registry[step_def["main_func"]],
            main_params=step_def["main_params"],
            step_id=step_def["step_id"],
            pre_funcs=pre_funcs,
            post_funcs=post_funcs
        ))
    return Workflow(steps)

# With a properly structured JSON config, you can load various workflows dynamically. 
# This addresses automating workflow generation for different imaging applications.

import requests

# The URL to your FastAPI app (adjust host/port/path as needed)
BASE_URL = "https://0.0.0.0:8001"

# The workflow JSON body
workflow_definition = {
  "steps": [
    {
      "id": "step_1",
      "stepName": "Set LED Power",
      "mainFuncName": "set_laser_power",
      "mainParams": { "power": 10, "channel": "LED" },
      "preFuncs": [],
      "postFuncs": []
    },
    {
      "id": "step_2",
      "stepName": "Acquire Frame",
      "mainFuncName": "acquire_frame",
      "mainParams": { "channel": "Mono" },
      "preFuncs": [],
      "postFuncs": ["process_data"]
    }
  ]
}


# 1) Create the workflow definition
create_resp = requests.post(f"{BASE_URL}/WorkflowController/create_workflow_definition_api", json=workflow_definition, verify=False)
create_resp.raise_for_status()
create_data = create_resp.json()
workflow_id = create_data["workflow_id"]
print("Created workflow with ID:", workflow_id)

# 2) Start the workflow
start_resp = requests.post(f"{BASE_URL}/WorkflowController/start_workflow_api", json={"workflow_id": workflow_id}, verify=False)
start_resp.raise_for_status()
print("Started workflow:", start_resp.json())

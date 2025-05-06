import requests

def start_scan():
    url = "https://localhost:8001/WorkflowController/start_xyz_histo_workflow_by_list"

    # Example body:
    # - Two coordinates: (0,0,0) and (100,100,0)
    # - Two illuminations: LED=100, Laser=50
    # - Storing output in /tmp/histotest.zarr
    # - Enabling autofocus
    payload = {
        "coords": [
            [0, 0, 0],
            [100, 100, 0]
        ],
        "illuminations": [
            {"LED": 100},
            {"Laser": 50}
        ],
        "file_name": "histotest.zarr",
        "autofocus_on": True
    }

    try:
        # Send the request, ignore SSL certificate errors
        resp = requests.post(url, json=payload, verify=False)
        resp.raise_for_status()
        # If the response is JSON, parse it
        data = resp.json()
        print("Scan started successfully:", data)
    except requests.HTTPError as e:
        print("Failed to start scan:", e)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    start_scan()

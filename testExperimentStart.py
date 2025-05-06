from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import uuid
import requests

app = FastAPI()

class NeighborPoint(BaseModel):
    x: float
    y: float

class Point(BaseModel):
    id: uuid.UUID
    name: str
    x: float
    y: float
    neighborPointList: List[NeighborPoint]

class ParameterValue(BaseModel):
    illumination: str
    brightfield: bool
    darkfield: bool
    laserWaveLength: int
    differentialPhaseContrast: bool
    timeLapsePeriod: float
    numberOfImages: int
    autoFocus: bool
    autoFocusMin: float
    autoFocusMax: float
    autoFocusStepSize: float
    zStack: bool
    zStackMin: float
    zStackMax: float
    zStackStepSize: float

class Experiment(BaseModel):
    name: str
    parameterValue: ParameterValue
    pointList: List[Point]

@app.post("/start-experiment/")
def start_experiment(experiment: Experiment):
    return {"message": "Experiment received", "experiment": experiment}

# Test script to send a POST request
def test_api():
    url = "https://imswitch.openuc2.com/ExperimentController/startWellplateExperiment"
    payload = {
        "name": "experiment",
        "parameterValue": {
            "illumination": "Brightfield",
            "brightfield": True,
            "darkfield": False,
            "laserWaveLength": 488,
            "differentialPhaseContrast": False,
            "timeLapsePeriod": 0.1,
            "numberOfImages": 5,
            "autoFocus": True,
            "autoFocusMin": 0,
            "autoFocusMax": 10,
            "autoFocusStepSize": 0.5,
            "zStack": True,
            "zStackMin": 0,
            "zStackMax": 10,
            "zStackStepSize": 0.5
        },
        "pointList": [
            {
                "id": str(uuid.uuid4()),
                "name": "Point 1",
                "x": 100.0,
                "y": 200.0,
                "neighborPointList": [
                    {"x": 120.0, "y": 220.0},
                    {"x": 130.0, "y": 230.0}
                ]
            }
        ]
    }
    response = requests.post(url, json=payload)
    print(response.json())

if __name__ == "__main__":
    test_api()

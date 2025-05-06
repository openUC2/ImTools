import cv2
import threading
import requests
import numpy as np
import matplotlib.pyplot as plt
import time

class MJPEGStreamReceiver:
    def __init__(self, stream_url):
        self.stream_url = stream_url
        self.frame = None
        self.streaming = False
        self.thread = None
        self.lock = threading.Lock()

    def startStream(self):
        if not self.streaming:
            self.streaming = True
            self.thread = threading.Thread(target=self._pull_frames, daemon=True)
            self.thread.start()

    def _pull_frames(self):
        # Continuously pull frames from the MJPEG stream
        with requests.get(self.stream_url, stream=True, verify=False) as response:
            if response.status_code == 200:
                bytes_stream = bytes()
                for chunk in response.iter_content(chunk_size=1024):
                    bytes_stream += chunk
                    a = bytes_stream.find(b'\xff\xd8')  # Start of JPEG
                    b = bytes_stream.find(b'\xff\xd9')  # End of JPEG
                    if a != -1 and b != -1:
                        jpg_data = bytes_stream[a:b+2]
                        bytes_stream = bytes_stream[b+2:]

                        # Decode the image and store it
                        image = cv2.imdecode(np.frombuffer(jpg_data, np.uint8), cv2.IMREAD_COLOR)
                        if image is not None:
                            with self.lock:
                                self.frame = image

    def stopStream(self):
        if self.streaming:
            self.streaming = False
            self.thread.join()

    def getFrame(self) -> np.ndarray:
        # Retrieve the most recent frame
        with self.lock:
            if self.frame is not None:
                return self.frame.copy()  # Return a copy to avoid race conditions
            else:
                return None

# Example usage with FastAPI
stream_url = "https://localhost:8001/RecordingController/video_feeder"
mjpeg_receiver = MJPEGStreamReceiver(stream_url)
mjpeg_receiver.startStream()
time.sleep(3)
frame = mjpeg_receiver.getFrame()
plt.imshow(frame), plt.show()
mjpeg_receiver.stopStream()
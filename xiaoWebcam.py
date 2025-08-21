import imageio as iio
import matplotlib.pyplot as plt



import imageio as iio
import matplotlib.pyplot as plt

camera = iio.get_reader("<video0>")
screenshot = camera.get_data(0)
camera.close()

plt.imshow(screenshot)


def get_available_cameras(max_index=5):
    available = []
    for cam_index in range(max_index):
        try:
            # Attempt to open this camera
            with iio.get_reader(f"<video{cam_index}>") as cam:
                _ = cam.get_data(0)  # read first frame
            available.append(cam_index)
        except Exception:
            pass
    return available


if __name__ == "__main__":
    myCameras = get_available_cameras(max_index=5)
    print("Available camera indices:", myCameras)

    
    for iCamera in myCameras:
    #  camera = iio.get_reader("<video2>")
        camera = iio.get_reader("<video"+str(iCamera)+">")
        screenshot = camera.get_data(0)
        camera.close()

        print(screenshot)
        plt.imshow(screenshot)
        plt.show()

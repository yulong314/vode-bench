import os
import sys
import numpy as np
import cv2


def load_intrinsics_raw(dataset_dir, date, cam_id):
    calib_file = os.path.join(dataset_dir, date, 'calib_cam_to_cam.txt')
    filedata = read_raw_calib_file(calib_file)
    P_rect = np.reshape(filedata['P_rect_' + cam_id], (3, 4))
    intrinsics = P_rect[:3, :3]
    return intrinsics


def read_raw_calib_file(filepath):
    # From https://github.com/utiasSTARS/pykitti/blob/master/pykitti/utils.py
    """Read in a calibration file and parse into a dictionary."""
    data = {}

    with open(filepath, 'r') as f:
        for line in f.readlines():
            key, value = line.split(':', 1)
            # The only non-float values in these files are dates, which
            # we don't care about anyway
            try:
                data[key] = np.array([float(x) for x in value.split()])
            except ValueError:
                pass
    return data


def read_file_data(data_root, filename):
    date, drive, cam, _, frame_id = filename.split("/")
#         camera_id = filename[-1]   # 2 is left, 3 is right
    vel = '{}/{}/velodyne_points/data/{}.bin'.format(date, drive, frame_id[:10])
    img_file = os.path.join(data_root, filename)
    num_probs = 0

    if os.path.isfile(img_file):
        gt_file = os.path.join(data_root, vel)
        gt_calib = os.path.join(data_root, date)
        im_size = cv2.imread(img_file).shape[:2]
        cam_id = cam[-2:]
        return gt_file, gt_calib, im_size, cam_id
    else:
        num_probs += 1
        print('{} missing'.format(img_file))
        return [], [], [], [], []

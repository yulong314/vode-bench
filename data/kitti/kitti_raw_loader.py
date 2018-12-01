# Mostly based on the code written by Tinghui Zhou: 
# https://github.com/tinghuiz/SfMLearner/blob/master/data/kitti/kitti_raw_loader.py
import sys
import numpy as np
from glob import glob
import os
import scipy.misc

module_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if module_path not in sys.path: sys.path.append(module_path)
from abstracts import DataLoader
from data.kitti.depth_evaluation_utils import read_file_data, generate_depth_map


class KittiRawLoader(DataLoader):
    def __init__(self, 
                 dataset_dir,
                 split,
                 img_height=128,
                 img_width=416,
                 seq_length=3,
                 remove_static=True):
        super().__init__()
        self.dataset_dir = dataset_dir
        self.img_height = img_height
        self.img_width = img_width
        self.seq_length = seq_length
        self.remove_static = remove_static
        self.cam_ids = ['02', '03']
        self.date_list = ['2011_09_26', '2011_09_28', '2011_09_29', '2011_09_30', '2011_10_03']
        self.test_scenes = self.read_test_scenes(split)
        if self.remove_static:
            self.static_frames = self.collect_static_frames()

        self.collect_frames()

    @staticmethod
    def read_test_scenes(split):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        test_scene_file = os.path.join(dir_path, 'test_scenes_{}.txt'.format(split))
        with open(test_scene_file, 'r') as f:
            test_scenes = f.readlines()
        test_scenes = [t[:-1] for t in test_scenes]
        return test_scenes

    def collect_static_frames(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        static_frames_file = os.path.join(dir_path, 'static_frames.txt')
        with open(static_frames_file, 'r') as f:
            frames = f.readlines()
        static_frames = []
        for fr in frames:
            if fr == '\n':
                continue
            date, drive, frame_id = fr.split(' ')
            curr_fid = '%.10d' % (np.int(frame_id[:-1]))
            for cid in self.cam_ids:
                static_frames.append(drive + ' ' + cid + ' ' + curr_fid)
        return static_frames


        
    def collect_frames(self):
        # collect train frames
        for date in self.date_list:
            drive_set = os.listdir(os.path.join(self.dataset_dir, date))
            for dr in drive_set:
                drive_dir = os.path.join(self.dataset_dir, date, dr)
                if dr[:-5] not in self.test_scenes and os.path.isdir(drive_dir):
                    new_frames = self.collect_drive_frames(drive_dir, dr)
                    self.train_frames.extend(new_frames)

        self.num_train = len(self.train_frames)
        print("train frames", self.num_train, self.train_frames[0])
        self.train_gts = self.load_depth_maps(self.train_frames)
        # TODO: intrinsic 불러오기
        # self.intrinsics[seq] = self.load_intrinsics('{:02d}'.format(seq), 0)

        # collect test frames
        self.test_frames = self.collect_test_frames()
        if self.remove_static:
            self.remove_static_frames()
        self.num_test = len(self.test_frames)



    def collect_drive_frames(self, drive_dir, dr):
        new_frames = []
        for cam in self.cam_ids:
            img_dir = os.path.join(drive_dir, 'image_' + cam, 'data')
            N = len(glob(img_dir + '/*.png'))
            for n in range(N):
                frame_id = '%.10d' % n
                # dr(e.g. 2011_09_26_drive_0001_sync), cam(e.g. 02), frame_id(e.g. 0000000001)
                new_frames.append(dr + ' ' + cam + ' ' + frame_id)
        return new_frames

    @staticmethod
    def collect_test_frames(split):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        test_file_txt = os.path.join(dir_path, 'test_files_{}.txt'.format(split))
        test_frames = []
        with open(test_file_txt, 'r') as f:
            test_file = f.readlines()
            test_file = [t[:-1] for t in test_file]
            for line in test_file:
                dirs = line.split("/")
                dr = dirs[1]
                cam = dirs[2][6:]
                frame_id = dirs[4][:-4]
                test_frames.append(dr + ' ' + cam + ' ' + frame_id)
        return test_frames

    def remove_static_frames(self):
        for s in self.static_frames:
            try:
                self.train_frames.remove(s)
                self.test_frames.remove(s)
            except:
                pass

    def load_depth_maps(self, frames):
        depth_files = self.frames_to_files(frames)
        gt_files, gt_calib, im_sizes, im_files, cams = read_file_data(depth_files, self.dataset_dir)
        num_test = len(im_files)
        gt_depths = []
        for t_id in range(num_test):
            camera_id = cams[t_id]  # 2 is left, 3 is right
            depth = generate_depth_map(gt_calib[t_id], gt_files[t_id], im_sizes[t_id],
                                       camera_id, False, True)
            if t_id < 5:
                print("depth shape", depth.shape)
            gt_depths.append(depth.astype(np.float32))
        return gt_depths

    @staticmethod
    def frames_to_files(frames):
        files = []
        for frame in frames:
            drive, cam, frame_id = frame.split(' ')
            file = "{}/{}/image_{}/data/{}.png".format(drive[:10], drive, cam, frame_id)
            files.append(file)
        return files


    # ===================================================
    def get_train_example_with_idx(self, tgt_idx):
        if not self.is_valid_sample(self.train_frames, tgt_idx):
            return False
        example = self.load_example(self.train_frames, tgt_idx)
        return example

    def get_test_example_with_idx(self, tgt_idx):
        if not self.is_valid_sample(self.test_frames, tgt_idx):
            return False
        example = self.load_example(self.test_frames, tgt_idx)
        return example

    def is_valid_sample(self, frames, tgt_idx):
        N = len(frames)
        tgt_drive, cid, _ = frames[tgt_idx].split(' ')
        half_offset = int((self.seq_length - 1)/2)
        min_src_idx = tgt_idx - half_offset
        max_src_idx = tgt_idx + half_offset
        if min_src_idx < 0 or max_src_idx >= N:
            return False
        min_src_drive, min_src_cid, _ = frames[min_src_idx].split(' ')
        max_src_drive, max_src_cid, _ = frames[max_src_idx].split(' ')
        if tgt_drive == min_src_drive and tgt_drive == max_src_drive and cid == min_src_cid and cid == max_src_cid:
            return True
        return False

    def load_example(self, frames, tgt_idx):
        image_seq, zoom_x, zoom_y = self.load_image_sequence(frames, tgt_idx, self.seq_length)
        # dirname(e.g. 2011_09_26_drive_0001_sync), camera_id(e.g. 02), frame_id(e.g. 0000000001)
        tgt_drive, tgt_cid, tgt_frame_id = frames[tgt_idx].split(' ')
        intrinsics = self.load_intrinsics_raw(tgt_drive, tgt_cid, tgt_frame_id)
        intrinsics = self.scale_intrinsics(intrinsics, zoom_x, zoom_y)
        example = {}
        example['intrinsics'] = intrinsics
        example['image_seq'] = image_seq
        example['folder_name'] = tgt_drive + '_' + tgt_cid
        example['file_name'] = tgt_frame_id
        return example

    def load_image_sequence(self, frames, tgt_idx, seq_length):
        half_offset = int((seq_length - 1)/2)
        image_seq = []
        for o in range(-half_offset, half_offset + 1):
            curr_idx = tgt_idx + o
            curr_drive, curr_cid, curr_frame_id = frames[curr_idx].split(' ')
            curr_img = self.load_image_raw(curr_drive, curr_cid, curr_frame_id)
            if o == 0:
                zoom_y = self.img_height/curr_img.shape[0]
                zoom_x = self.img_width/curr_img.shape[1]
            curr_img = scipy.misc.imresize(curr_img, (self.img_height, self.img_width))
            image_seq.append(curr_img)
        return image_seq, zoom_x, zoom_y

    def load_image_raw(self, drive, cid, frame_id):
        date = drive[:10]
        img_file = os.path.join(self.dataset_dir, date, drive, 'image_' + cid, 'data', frame_id + '.png')
        img = scipy.misc.imread(img_file)
        return img

    def load_intrinsics_raw(self, drive, cid, frame_id):
        date = drive[:10]
        calib_file = os.path.join(self.dataset_dir, date, 'calib_cam_to_cam.txt')

        filedata = self.read_raw_calib_file(calib_file)
        P_rect = np.reshape(filedata['P_rect_' + cid], (3, 4))
        intrinsics = P_rect[:3, :3]
        return intrinsics

    def read_raw_calib_file(self,filepath):
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

    def scale_intrinsics(self, mat, sx, sy):
        out = np.copy(mat)
        out[0,0] *= sx
        out[0,2] *= sx
        out[1,1] *= sy
        out[1,2] *= sy
        return out



# TODO: code reference
import os
import random
import numpy as np
import tensorflow as tf
import scipy.io as sio

from models.geonet.geonet_model import GeoNetModel
from models.geonet.geonet_feeder import dataset_feeder
from model_operator import GeoNetOperator
from constants import InputShape
from data.kitti.pose_evaluation_utils import format_pose_seq_TUM


flags = tf.app.flags
flags.DEFINE_string("model",                        "",    "geonet or sfmlearner")
flags.DEFINE_string("mode",                         "",    "(train_rigid, train_flow) or (test_depth, test_pose, test_flow)")
flags.DEFINE_string("dataset_dir",                  "",    "Dataset directory")
flags.DEFINE_string("tfrecords_dir",                "",    "tfrecords directory")
flags.DEFINE_string("init_ckpt_file",             None,    "Specific checkpoint file to initialize from")
flags.DEFINE_integer("batch_size",                   4,    "The size of of a sample batch")
flags.DEFINE_integer("num_threads",                 32,    "Number of threads for data loading")
flags.DEFINE_integer("img_height",                 128,    "Image height")
flags.DEFINE_integer("img_width",                  416,    "Image width")
flags.DEFINE_integer("seq_length",                   3,    "Sequence length for each example")

# #### Training Configurations #####
flags.DEFINE_string("checkpoint_dir",               "",    "Directory name to save the checkpoints")
flags.DEFINE_float("learning_rate",             0.0002,    "Learning rate for adam")
flags.DEFINE_integer("max_to_keep",                 20,    "Maximum number of checkpoints to save")
flags.DEFINE_integer("train_epochs",                50,    "number of epochs for training")
# flags.DEFINE_integer("max_steps",             300000,    "Maximum number of training iterations")
# flags.DEFINE_integer("save_ckpt_freq",          5000,    "Save the checkpoint model every save_ckpt_freq iterations")
flags.DEFINE_float("alpha_recon_image",           0.85,    "Alpha weight between SSIM and L1 in reconstruction loss")

# #### Configurations about DepthNet & PoseNet of GeoNet #####
flags.DEFINE_string("dispnet_encoder",      "resnet50",    "Type of encoder for dispnet, vgg or resnet50")
flags.DEFINE_boolean("scale_normalize",          False,    "Spatially normalize depth prediction")
flags.DEFINE_float("rigid_warp_weight",            1.0,    "Weight for warping by rigid flow")
flags.DEFINE_float("disp_smooth_weight",           0.5,    "Weight for disp smoothness")

# #### Configurations about ResFlowNet of GeoNet (or DirFlowNetS) #####
flags.DEFINE_string("flownet_type",         "residual",    "type of flownet, residual or direct")
flags.DEFINE_float("flow_warp_weight",             1.0,    "Weight for warping by full flow")
flags.DEFINE_float("flow_smooth_weight",           0.2,    "Weight for flow smoothness")
flags.DEFINE_float("flow_consistency_weight",      0.2,    "Weight for bidirectional flow consistency")
flags.DEFINE_float("flow_consistency_alpha",       3.0,    "Alpha for flow consistency check")
flags.DEFINE_float("flow_consistency_beta",       0.05,    "Beta for flow consistency check")

# #### Testing Configurations #####
flags.DEFINE_string("output_dir",                 None,    "Test result output directory")
flags.DEFINE_string("depth_test_split",        "eigen",    "KITTI depth split, eigen or stereo")
# flags.DEFINE_integer("pose_test_seq",                9,    "KITTI Odometry Sequence ID to test")


# #### Additional Configurations #####
flags.DEFINE_integer("num_source",                   0,    "number of sources")
flags.DEFINE_integer("num_scales",                   0,    "number of scales")
flags.DEFINE_integer("add_flownet",                  0,    "whether flownet is included in model")
flags.DEFINE_integer("add_dispnet",                  0,    "whether dispnet is included in model")
flags.DEFINE_integer("add_posenet",                  0,    "whether posenet is included in model")

opt = flags.FLAGS


def train():
    set_random_seed()
    if not os.path.exists(opt.checkpoint_dir):
        os.makedirs(opt.checkpoint_dir)
    geonet = GeoNetModel(opt)
    model_op = GeoNetOperator(opt, geonet)
    model_op.train()


def set_random_seed():
    seed = 8964
    tf.set_random_seed(seed)
    np.random.seed(seed)
    random.seed(seed)


def test_pose():
    # tf.enable_eager_execution()
    geonet = GeoNetModel(opt)
    input_uint8 = tf.placeholder(tf.uint8, [opt.batch_size, InputShape.HEIGHT, InputShape.WIDTH,
                                            opt.seq_length * 3], name='raw_input')
    tgt_image = input_uint8[:, :, :, :3]
    src_image_stack = input_uint8[:, :, :, 3:]
    geonet.build_model(tgt_image, src_image_stack, None)
    fetches = {"pose": geonet.pred_poses}
    saver = tf.train.Saver([var for var in tf.model_variables()])
    dataset_iter = dataset_feeder(opt, "test", opt.seq_length)

    gt_poses = []
    pred_poses = []
    target_ind = (opt.seq_length - 1)//2

    with tf.Session() as sess:
        saver.restore(sess, opt.init_ckpt_file)
        for i in range(1000000):
            try:
                inputs = sess.run(dataset_iter)
                pred = sess.run(fetches, feed_dict={tgt_image: inputs["target"],
                                                    src_image_stack: inputs["sources"]})
                gt_poses.append(inputs["gt"])
                pred_pose_batch = pred["pose"]
                pred_pose_batch = np.insert(pred_pose_batch, target_ind, np.zeros((1, 6)), axis=1)
                for b in range(opt.batch_size):
                    # insert the target pose [0, 0, 0, 0, 0, 0] into the middle 
                    pred_pose_tum = format_pose_seq_TUM(pred_pose_batch[b, :, :])
                    pred_poses.append(pred_pose_tum)
            except tf.errors.OutOfRangeError:
                break

    gt_poses = np.concatenate(gt_poses, axis=0)
    pred_poses = np.stack(pred_poses, axis=0)
    print("poses shape (gt, pred)", gt_poses.shape, pred_poses.shape)
    filename = os.path.join(opt.output_dir, "gt_pose_seq_{}".format(opt.seq_length))
    np.save(filename, gt_poses)
    filename = os.path.join(opt.output_dir, "pred_pose_seq_{}".format(opt.seq_length))
    np.save(filename, pred_poses)
    filename = os.path.join(opt.output_dir, "pose_seq_{}".format(opt.seq_length))
    sio.savemat(filename, {"gt_pose": gt_poses, "pred_pose": pred_poses})
    print("test finished")


def test_depth():
    pass


def main(_):
    opt.num_source = opt.seq_length - 1
    opt.num_scales = 4

    opt.add_flownet = opt.mode in ['train_flow', 'test_flow']
    opt.add_dispnet = opt.add_flownet and opt.flownet_type == 'residual' \
                      or opt.mode in ['train_rigid', 'test_depth']
    opt.add_posenet = opt.add_flownet and opt.flownet_type == 'residual' \
                      or opt.mode in ['train_rigid', 'test_pose']

    print("important opts", "\ndataset", opt.dataset_dir, "\ntfrecord", opt.tfrecords_dir,
          "\ncheckpoint", opt.checkpoint_dir, "\nbatch", opt.batch_size)

    if opt.mode == 'train_rigid':
        train()
    elif opt.mode == 'test_depth':
        test_depth()
    elif opt.mode == 'test_pose':
        test_pose()


if __name__ == '__main__':
    tf.app.run()

import numpy as np

import mxnet as mx
from mxnet.gluon import nn
from mxnet import nd,symbol,gluon,init

from network.resnet import RoentgenResnet
from network.rpn import ProposalNetwork, ProposalLayer, ROIAlignmentLayer

from network.anchor import AnchorTargetLayer


class RoentgenFasterRCNN(gluon.nn.HybridBlock):
	def __init__(self, num_classes=2, is_training=False, rpn_output=False, Nt=0.7, scales=[0.25,0.15,0.05], ratios=[2,1,0.5]):
		super(RoentgenFasterRCNN, self).__init__()
		self.is_training = is_training
		self.rpn_output = rpn_output

		self.resnet = RoentgenResnet(64, conv_arch=[(2, 64), (2, 128), (2, 256), (2, 512)])

		self.rpn = ProposalNetwork(512, num_anchors=9, anchor_points=(32,32))
		self.proposals = ProposalLayer(scales, ratios, output_layer=rpn_output, rpn_post_nms_top_n=1)

		if is_training:
			self.anchor_target = AnchorTargetLayer(32, scales=scales, ratios=ratios)

		if not rpn_output:
			self.alignment = ROIAlignmentLayer((8,8), spatial_scale=0.03125)

			self.fc = nn.HybridSequential() 
			self.fc.add(nn.Dense(2048, activation='relu'))
			self.fc.add(nn.Dense(1024, activation='relu'))

			self.bbox_offset = nn.Dense(4)
			self.class_pred= nn.Dense(num_classes)


	def hybrid_forward(self, F, X, im_info, gtboxes=None):
		feature_map = self.resnet(X)

		cls_prob, bbox_pred = self.rpn(feature_map)
		rois = self.proposals(cls_prob, bbox_pred, im_info)

		if self.rpn_output:
			bboxes = F.slice_axis(rois[0], axis=1, begin=1, end=None)
			classes = rois[1]
		else:
			# rpn_post_nms_top_n>1 -> flatten=False
			regions = self.alignment(feature_map, rois)
			roi_features = self.fc(mx.symbol.flatten(regions))

			bboxes = F.slice_axis(rois, axis=1, begin=1, end=None) + self.bbox_offset(roi_features)
			classes = self.class_pred(roi_features)
		
		if self.is_training:
			rpn_label, rpn_bbox_target = self.anchor_target(cls_prob, gtboxes, im_info)
			return bboxes, classes, rpn_label, rpn_bbox_target
		else:
			return bboxes, classes
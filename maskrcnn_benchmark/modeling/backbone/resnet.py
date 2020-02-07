# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved.
"""
Variant of the resnet module that takes cfg as an argument.
Example usage. Strings may be specified in the config file.
    model = ResNet(
        "StemWithFixedBatchNorm",
        "BottleneckWithFixedBatchNorm",
        "ResNet50StagesTo4",
    )
OR:
    model = ResNet(
        "StemWithGN",
        "BottleneckWithGN",
        "ResNet50StagesTo4",
    )
Custom implementations may be written in user code and hooked in via the
`register_*` functions.
"""
from collections import namedtuple

import torch
import torch.nn.functional as F
from torch import nn

from maskrcnn_benchmark.layers import FrozenBatchNorm2d
from maskrcnn_benchmark.layers import Conv2d
from maskrcnn_benchmark.layers import DFConv2d
from maskrcnn_benchmark.modeling.make_layers import group_norm
from maskrcnn_benchmark.utils.registry import Registry


# ResNet stage specification
StageSpec = namedtuple(
    "StageSpec",
    [
        "index",  # Index of the stage, eg 1, 2, ..,. 5
        "block_count",  # Number of residual blocks in the stage
        "return_features",  # True => return the last feature map from this stage
    ],
)

# -----------------------------------------------------------------------------
# Standard ResNet models
# -----------------------------------------------------------------------------
# ResNet-50 (including all stages)
ResNet50StagesTo5 = tuple(
    StageSpec(index=i, block_count=c, return_features=r)
    for (i, c, r) in ((1, 3, False), (2, 4, False), (3, 6, False), (4, 3, True))
)
# ResNet-50 up to stage 4 (excludes stage 5)
ResNet50StagesTo4 = tuple(
    StageSpec(index=i, block_count=c, return_features=r)
    for (i, c, r) in ((1, 3, False), (2, 4, False), (3, 6, True))
)
# ResNet-101 (including all stages)
ResNet101StagesTo5 = tuple(
    StageSpec(index=i, block_count=c, return_features=r)
    for (i, c, r) in ((1, 3, False), (2, 4, False), (3, 23, False), (4, 3, True))
)
# ResNet-101 up to stage 4 (excludes stage 5)
ResNet101StagesTo4 = tuple(
    StageSpec(index=i, block_count=c, return_features=r)
    for (i, c, r) in ((1, 3, False), (2, 4, False), (3, 23, True))
)
# ResNet-50-FPN (including all stages)
ResNet50FPNStagesTo5 = tuple(
    StageSpec(index=i, block_count=c, return_features=r)
    for (i, c, r) in ((1, 3, True), (2, 4, True), (3, 6, True), (4, 3, True))
)
# ResNet-101-FPN (including all stages)
ResNet101FPNStagesTo5 = tuple(
    StageSpec(index=i, block_count=c, return_features=r)
    for (i, c, r) in ((1, 3, True), (2, 4, True), (3, 23, True), (4, 3, True))
)
# ResNet-152-FPN (including all stages)
ResNet152FPNStagesTo5 = tuple(
    StageSpec(index=i, block_count=c, return_features=r)
    for (i, c, r) in ((1, 3, True), (2, 8, True), (3, 36, True), (4, 3, True))
)

# -----------------------------------------------------------------------------
# Custom ResNet models
# -----------------------------------------------------------------------------
ResNet50_3_4_2 = tuple(
    StageSpec(index=i, block_count=c, return_features=r)
    for (i, c, r) in ((1, 3, False), (2, 4, False), (3, 2, True))
)

ResNet50_3_4_8 = tuple(
    StageSpec(index=i, block_count=c, return_features=r)
    for (i, c, r) in ((1, 3, False), (2, 4, False), (3, 8, True))
)

ResNet50_3_4_14 = tuple(
    StageSpec(index=i, block_count=c, return_features=r)
    for (i, c, r) in ((1, 3, False), (2, 4, False), (3, 14, True))
)

ResNet50_3_4_20 = tuple(
    StageSpec(index=i, block_count=c, return_features=r)
    for (i, c, r) in ((1, 3, False), (2, 4, False), (3, 20, True))
)


################################################################################
### ResNet Stage -- EWAdaptive
################################################################################
#class ResNet_Stem(nn.Module):
#    def __init__(self, cfg, freeze=True):
#        super(ResNet_Stem, self).__init__()
#        # Translate string names to implementations
#        stem_module = _STEM_MODULES[cfg.MODEL.RESNETS.STEM_FUNC]
#        # Construct the stem module
#        self.stem = stem_module(cfg)
#        # Optionally freeze (requires_grad=False)
#        if freeze:
#            self._freeze()
#
#    def _freeze(self):
#        m = self.stem
#        for p in m.parameters():
#            p.requires_grad = False
#
#    def forward(self, x):
#        x = self.stem(x)
#        return x
#
## This class represents one ResNet stage.
#class ResNet_Stage(nn.Module):
#    def __init__(self, cfg, stage, in_channels):
#        super(ResNet_Stage, self).__init__()
#
#        # If we want to use the cfg in forward(), then we should make a copy
#        # of it and store it for later use:
#        # self.cfg = cfg.clone()
#
#        assert(stage >= 2 and stage <= 4, "Error: stage argument out of bounds.")
#
#        # Translate string names to implementations
#        stage_specs = _STAGE_SPECS[cfg.MODEL.BACKBONE.CONV_BODY]
#        transformation_module = _TRANSFORMATION_MODULES[cfg.MODEL.RESNETS.TRANS_FUNC]
#        stage_spec = stage_specs[stage - 2]
#
#        # Channel stuff
#        num_groups = cfg.MODEL.RESNETS.NUM_GROUPS
#        width_per_group = cfg.MODEL.RESNETS.WIDTH_PER_GROUP
#        #in_channels = cfg.MODEL.RESNETS.STEM_OUT_CHANNELS
#        stage2_bottleneck_channels = num_groups * width_per_group
#        stage2_out_channels = cfg.MODEL.RESNETS.RES2_OUT_CHANNELS
#        stage2_relative_factor = 2 ** (stage_spec.index - 1)
#        bottleneck_channels = stage2_bottleneck_channels * stage2_relative_factor
#        stage_with_dcn = cfg.MODEL.RESNETS.STAGE_WITH_DCN[stage_spec.index -1]
#
#        self.out_channels = stage2_out_channels * stage2_relative_factor
#        
#        # Build stage according to cfg.MODEL.EWADAPTIVE.C-
#        if stage == 2:
#            ewa_spec = cfg.MODEL.EWADAPTIVE.C2
#        elif stage == 3:
#            ewa_spec = cfg.MODEL.EWADAPTIVE.C3
#        elif stage == 4:
#            ewa_spec = cfg.MODEL.EWADAPTIVE.C4
#
#        self.branches = []
#        for branch_idx in range(len(ewa_spec)):
#            name = "branch" + str(branch_idx)
#            module = _make_stage(
#                transformation_module,
#                in_channels,
#                bottleneck_channels,
#                self.out_channels,
#                stage_spec.block_count,
#                num_groups,
#                cfg.MODEL.RESNETS.STRIDE_IN_1X1,
#                first_stride=ewa_spec[branch_idx][0],
#                dilation=ewa_spec[branch_idx][1],
#                dcn_config={
#                    "stage_with_dcn": stage_with_dcn,
#                    "with_modulated_dcn": cfg.MODEL.RESNETS.WITH_MODULATED_DCN,
#                    "deformable_groups": cfg.MODEL.RESNETS.DEFORMABLE_GROUPS,
#                },
#            )
#            self.add_module(name, module)
#            self.branches.append(name)
#        # Optionally freeze (requires_grad=False) the module
#        if (stage <= cfg.MODEL.BACKBONE.FREEZE_CONV_BODY_AT):
#            self._freeze()
#
#    def _freeze(self):
#        for b in range(len(self.branches)):
#            m = getattr(self, "branch" + str(b))
#            for p in m.parameters():
#                p.requires_grad = False
#
#    def forward(self, x, branch=0):
#        branch_name = self.branches[branch]
#        x = getattr(self, branch_name)(x)
#        return x


################################################################################
### DDPP Stages
################################################################################
class DDPP_Stem(nn.Module):
    """
    2x downsample, group norm
    """
    def __init__(self, cfg, norm_func):
        super(DDPPStem, self).__init__()

        out_channels = cfg.MODEL.RESNETS.STEM_OUT_CHANNELS

        # 2x downsample
        self.conv1 = Conv2d(
            3, out_channels, kernel_size=3, stride=2, padding=1, bias=False
        )
        self.bn1 = group_norm(out_channels)

        for l in [self.conv1,]:
            nn.init.kaiming_uniform_(l.weight, a=1)

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = F.relu_(x)
        return x


# This class represents one ResNet stage.
class DDPP_Stage(nn.Module):
    def __init__(self, cfg, stage, in_channels):
        super(ResNet_Stage, self).__init__()

        # If we want to use the cfg in forward(), then we should make a copy
        # of it and store it for later use:
        # self.cfg = cfg.clone()

        assert(stage >= 2 and stage <= 4, "Error: stage argument out of bounds.")

        # Translate string names to implementations
        stage_specs = _STAGE_SPECS[cfg.MODEL.BACKBONE.CONV_BODY]
        transformation_module = _TRANSFORMATION_MODULES[cfg.MODEL.RESNETS.TRANS_FUNC]
        stage_spec = stage_specs[stage - 2]

        # Channel stuff
        num_groups = cfg.MODEL.RESNETS.NUM_GROUPS
        width_per_group = cfg.MODEL.RESNETS.WIDTH_PER_GROUP
        #in_channels = cfg.MODEL.RESNETS.STEM_OUT_CHANNELS
        stage2_bottleneck_channels = num_groups * width_per_group
        stage2_out_channels = cfg.MODEL.RESNETS.RES2_OUT_CHANNELS
        stage2_relative_factor = 2 ** (stage_spec.index - 1)
        bottleneck_channels = stage2_bottleneck_channels * stage2_relative_factor
        stage_with_dcn = cfg.MODEL.RESNETS.STAGE_WITH_DCN[stage_spec.index -1]

        self.out_channels = stage2_out_channels * stage2_relative_factor
        
        # Build stage according to cfg.MODEL.EWADAPTIVE.C-
        if stage == 2:
            ewa_spec = cfg.MODEL.EWADAPTIVE.C2
        elif stage == 3:
            ewa_spec = cfg.MODEL.EWADAPTIVE.C3
        elif stage == 4:
            ewa_spec = cfg.MODEL.EWADAPTIVE.C4

        self.branches = []
        for branch_idx in range(len(ewa_spec)):
            name = "branch" + str(branch_idx)
            module = _make_stage(
                transformation_module,
                in_channels,
                bottleneck_channels,
                self.out_channels,
                stage_spec.block_count,
                num_groups,
                cfg.MODEL.RESNETS.STRIDE_IN_1X1,
                first_stride=ewa_spec[branch_idx][0],
                dilation=ewa_spec[branch_idx][1],
                dcn_config={
                    "stage_with_dcn": stage_with_dcn,
                    "with_modulated_dcn": cfg.MODEL.RESNETS.WITH_MODULATED_DCN,
                    "deformable_groups": cfg.MODEL.RESNETS.DEFORMABLE_GROUPS,
                },
            )
            self.add_module(name, module)
            self.branches.append(name)
        # Optionally freeze (requires_grad=False) the module
        if (stage <= cfg.MODEL.BACKBONE.FREEZE_CONV_BODY_AT):
            self._freeze()

    def _freeze(self):
        for b in range(len(self.branches)):
            m = getattr(self, "branch" + str(b))
            for p in m.parameters():
                p.requires_grad = False

    def forward(self, x, branch=0):
        branch_name = self.branches[branch]
        x = getattr(self, branch_name)(x)
        return x


################################################################################
### Full ResNet
################################################################################
class ResNet(nn.Module):
    def __init__(self, cfg):
        super(ResNet, self).__init__()

        # If we want to use the cfg in forward(), then we should make a copy
        # of it and store it for later use:
        # self.cfg = cfg.clone()

        # Translate string names to implementations
        stem_module = _STEM_MODULES[cfg.MODEL.RESNETS.STEM_FUNC]
        stage_specs = _STAGE_SPECS[cfg.MODEL.BACKBONE.CONV_BODY]
        transformation_module = _TRANSFORMATION_MODULES[cfg.MODEL.RESNETS.TRANS_FUNC]

        # Construct the stem module
        self.stem = stem_module(cfg)

        # Set strides according to cfg.RPN.ANCHOR_STRIDE
        # NOTE: this is only valid for ResNet__StagesTo4
        if not cfg.MODEL.RPN.USE_FPN and cfg.MODEL.BACKBONE.RESREG == 0:
            if cfg.MODEL.RPN.ANCHOR_STRIDE[0] == 4:
                strides = [1, 1, 1]
            elif cfg.MODEL.RPN.ANCHOR_STRIDE[0] == 8:
                strides = [1, 1, 2]
            elif cfg.MODEL.RPN.ANCHOR_STRIDE[0] == 16:
                strides = [1, 2, 2]
            elif cfg.MODEL.RPN.ANCHOR_STRIDE[0] == 32:
                strides = [2, 2, 2]
            else:
                print("ERROR: Invalid cfg.MODEL.RPN.ANCHOR_STRIDE setting:", cfg.MODEL.RPN.ANCHOR_STRIDE)
                exit()

        # Check to make sure the cfg.MODEL.RESNETS.DILATIONS length
        # matches the stage_specs length
        assert(len(cfg.MODEL.RESNETS.DILATIONS) == len(stage_specs), "ERROR: cfg.MODEL.RESNETS.DILATIONS length does not match length of stage_spec")

        # Constuct the specified ResNet stages
        num_groups = cfg.MODEL.RESNETS.NUM_GROUPS
        width_per_group = cfg.MODEL.RESNETS.WIDTH_PER_GROUP
        in_channels = cfg.MODEL.RESNETS.STEM_OUT_CHANNELS
        stage2_bottleneck_channels = num_groups * width_per_group
        stage2_out_channels = cfg.MODEL.RESNETS.RES2_OUT_CHANNELS
        self.stages = []
        self.return_features = {}
        for stage_idx, stage_spec in enumerate(stage_specs):
            name = "layer" + str(stage_spec.index)
            stage2_relative_factor = 2 ** (stage_spec.index - 1)
            bottleneck_channels = stage2_bottleneck_channels * stage2_relative_factor
            out_channels = stage2_out_channels * stage2_relative_factor
            stage_with_dcn = cfg.MODEL.RESNETS.STAGE_WITH_DCN[stage_spec.index -1]

            if cfg.MODEL.RESNETS.MIDDLE_KERNEL_SIZES:
                middle_ks = cfg.MODEL.RESNETS.MIDDLE_KERNEL_SIZES[stage_idx]
            else:
                middle_ks = [3 for _ in range(stage_spec.block_count)]
            assert(len(middle_ks) == stage_spec.block_count), "Length of middle_ks does not match block count at stage: {}".format(stage_idx)

            use_unfixed_bn = False
            if name in cfg.MODEL.DONT_LOAD and cfg.MODEL.RESNETS.TRANS_FUNC == "BottleneckWithFixedBatchNorm":
                use_unfixed_bn = True

            if cfg.MODEL.RPN.USE_FPN or cfg.MODEL.BACKBONE.RESREG != 0:
                first_stride = int(stage_spec.index > 1) + 1
                dilation = 1
            else:
                first_stride = strides[stage_idx]
                dilation = cfg.MODEL.RESNETS.DILATIONS[stage_idx] # Choose stride based on ANCHOR_STRIDE


            module = _make_stage(
                transformation_module,
                in_channels,
                bottleneck_channels,
                out_channels,
                stage_spec.block_count,
                num_groups,
                cfg.MODEL.RESNETS.STRIDE_IN_1X1,
                first_stride=first_stride, 
                dilation=dilation,
                dcn_config={
                    "stage_with_dcn": stage_with_dcn,
                    "with_modulated_dcn": cfg.MODEL.RESNETS.WITH_MODULATED_DCN,
                    "deformable_groups": cfg.MODEL.RESNETS.DEFORMABLE_GROUPS,
                },
                middle_ks=middle_ks,
                use_unfixed_bn=use_unfixed_bn
            )
            in_channels = out_channels
            self.add_module(name, module)
            self.stages.append(name)
            self.return_features[name] = stage_spec.return_features

        # Optionally freeze (requires_grad=False) parts of the backbone
        self._freeze_backbone(cfg.MODEL.BACKBONE.FREEZE_CONV_BODY_AT)

    def _freeze_backbone(self, freeze_at):
        if freeze_at < 0:
            return
        for stage_index in range(freeze_at):
            if stage_index == 0:
                m = self.stem  # stage 0 is the stem
            else:
                m = getattr(self, "layer" + str(stage_index))
            for p in m.parameters():
                p.requires_grad = False

    def forward(self, x):
        outputs = []
        #print("input:", x, x.size())
        x = self.stem(x)
        #print("stem:", x, x.size())
        for stage_name in self.stages:
            x = getattr(self, stage_name)(x)
            #print(stage_name, x, x.size())
            if self.return_features[stage_name]:
                outputs.append(x)
        return outputs


class ResNetHead(nn.Module):
    def __init__(
        self,
        cfg,
        block_module,
        stages,
        num_groups=1,
        width_per_group=64,
        stride_in_1x1=True,
        stride_init=None,
        res2_out_channels=256,
        dilation=1,
        dcn_config={}
    ):
        super(ResNetHead, self).__init__()

        stage2_relative_factor = 2 ** (stages[0].index - 1)
        stage2_bottleneck_channels = num_groups * width_per_group
        out_channels = res2_out_channels * stage2_relative_factor
        in_channels = out_channels // 2
        bottleneck_channels = stage2_bottleneck_channels * stage2_relative_factor

        block_module = _TRANSFORMATION_MODULES[block_module]

        self.stages = []
        stride = stride_init
        for stage in stages:
            name = "layer" + str(stage.index)

            use_unfixed_bn = False
            if name in cfg.MODEL.DONT_LOAD and cfg.MODEL.RESNETS.TRANS_FUNC == "BottleneckWithFixedBatchNorm":
                use_unfixed_bn = True

            if not stride:
                stride = int(stage.index > 1) + 1

            module = _make_stage(
                block_module,
                in_channels,
                bottleneck_channels,
                out_channels,
                stage.block_count,
                num_groups,
                stride_in_1x1,
                first_stride=stride,
                dilation=dilation,
                dcn_config=dcn_config,
                use_unfixed_bn=use_unfixed_bn
            )
            stride = None
            self.add_module(name, module)
            self.stages.append(name)
        self.out_channels = out_channels

    def forward(self, x):
        for stage in self.stages:
            x = getattr(self, stage)(x)
        return x


def _make_stage(
    transformation_module,
    in_channels,
    bottleneck_channels,
    out_channels,
    block_count,
    num_groups,
    stride_in_1x1,
    first_stride,
    dilation=1,
    dcn_config={},
    middle_ks=[],
    use_unfixed_bn=False
):
    # Set default middle kernel sizes to all 3
    if not middle_ks:
        middle_ks = [3 for _ in range(block_count)]

    blocks = []
    stride = first_stride
    for i in range(block_count):
        blocks.append(
            transformation_module(
                in_channels,
                bottleneck_channels,
                out_channels,
                num_groups,
                stride_in_1x1,
                stride,
                dilation=dilation,
                dcn_config=dcn_config,
                middle_k=middle_ks[i],
                use_unfixed_bn=use_unfixed_bn
            )
        )
        stride = 1
        in_channels = out_channels
    return nn.Sequential(*blocks)


class Bottleneck(nn.Module):
    def __init__(
        self,
        in_channels,
        bottleneck_channels,
        out_channels,
        num_groups,
        stride_in_1x1,
        stride,
        dilation,
        norm_func,
        dcn_config,
        middle_k,
        use_unfixed_bn
    ):
        super(Bottleneck, self).__init__()

        self.downsample = None
        if in_channels != out_channels:
            down_stride = stride #if dilation == 1 else 1  # Don't want this
            self.downsample = nn.Sequential(
                Conv2d(
                    in_channels, out_channels,
                    kernel_size=1, stride=down_stride, bias=False
                ),
                norm_func(out_channels),
            )
            for modules in [self.downsample,]:
                for l in modules.modules():
                    if isinstance(l, Conv2d):
                        nn.init.kaiming_uniform_(l.weight, a=1)

        # Commented this out... don't want this
        #if dilation > 1:
        #    stride = 1 # reset to be 1

        # The original MSRA ResNet models have stride in the first 1x1 conv
        # The subsequent fb.torch.resnet and Caffe2 ResNe[X]t implementations have
        # stride in the 3x3 conv
        stride_1x1, stride_3x3 = (stride, 1) if stride_in_1x1 else (1, stride)

        self.conv1 = Conv2d(
            in_channels,
            bottleneck_channels,
            kernel_size=1,
            stride=stride_1x1,
            bias=False,
        )

        if use_unfixed_bn:
            self.bn1 = nn.BatchNorm2d(bottleneck_channels)
        else:
            self.bn1 = norm_func(bottleneck_channels)
        
        # TODO: specify init for the above
        with_dcn = dcn_config.get("stage_with_dcn", False)
        if with_dcn:
            deformable_groups = dcn_config.get("deformable_groups", 1)
            with_modulated_dcn = dcn_config.get("with_modulated_dcn", False)
            self.conv2 = DFConv2d(
                bottleneck_channels,
                bottleneck_channels,
                with_modulated_dcn=with_modulated_dcn,
                #kernel_size=3,
                kernel_size=middle_k,
                stride=stride_3x3,
                groups=num_groups,
                dilation=dilation,
                deformable_groups=deformable_groups,
                bias=False
            )
        else:
            padding = dilation
            # If our middle kernel size is 1, we don't need padding
            if middle_k == 1:
                padding = 0
            self.conv2 = Conv2d(
                bottleneck_channels,
                bottleneck_channels,
                #kernel_size=3,
                kernel_size=middle_k,
                stride=stride_3x3,
                #padding=dilation,
                padding=padding,
                bias=False,
                groups=num_groups,
                dilation=dilation
            )
            nn.init.kaiming_uniform_(self.conv2.weight, a=1)

        if use_unfixed_bn:
            self.bn2 = nn.BatchNorm2d(bottleneck_channels)
        else:
            self.bn2 = norm_func(bottleneck_channels)

        self.conv3 = Conv2d(
            bottleneck_channels, out_channels, kernel_size=1, bias=False
        )

        if use_unfixed_bn:
            self.bn3 = nn.BatchNorm2d(out_channels)
        else:
            self.bn3 = norm_func(out_channels)

        for l in [self.conv1, self.conv3,]:
            nn.init.kaiming_uniform_(l.weight, a=1)

    def forward(self, x):
        identity = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = F.relu_(out)

        out = self.conv2(out)
        out = self.bn2(out)
        out = F.relu_(out)

        out = self.conv3(out)
        out = self.bn3(out)

        if self.downsample is not None:
            identity = self.downsample(x)

        out += identity
        out = F.relu_(out)

        return out


class BaseStem(nn.Module):
    def __init__(self, cfg, norm_func):
        super(BaseStem, self).__init__()

        out_channels = cfg.MODEL.RESNETS.STEM_OUT_CHANNELS

        self.conv1 = Conv2d(
            3, out_channels, kernel_size=7, stride=2, padding=3, bias=False
        )
        self.bn1 = norm_func(out_channels)

        for l in [self.conv1,]:
            nn.init.kaiming_uniform_(l.weight, a=1)

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = F.relu_(x)
        x = F.max_pool2d(x, kernel_size=3, stride=2, padding=1)
        return x


class BottleneckWithFixedBatchNorm(Bottleneck):
    def __init__(
        self,
        in_channels,
        bottleneck_channels,
        out_channels,
        num_groups=1,
        stride_in_1x1=True,
        stride=1,
        dilation=1,
        dcn_config={},
        middle_k=3,
        use_unfixed_bn=False
    ):
        super(BottleneckWithFixedBatchNorm, self).__init__(
            in_channels=in_channels,
            bottleneck_channels=bottleneck_channels,
            out_channels=out_channels,
            num_groups=num_groups,
            stride_in_1x1=stride_in_1x1,
            stride=stride,
            dilation=dilation,
            norm_func=FrozenBatchNorm2d,
            dcn_config=dcn_config,
            middle_k=middle_k,
            use_unfixed_bn=use_unfixed_bn
        )


class StemWithFixedBatchNorm(BaseStem):
    def __init__(self, cfg):
        super(StemWithFixedBatchNorm, self).__init__(
            cfg, norm_func=FrozenBatchNorm2d
        )


class BottleneckWithGN(Bottleneck):
    def __init__(
        self,
        in_channels,
        bottleneck_channels,
        out_channels,
        num_groups=1,
        stride_in_1x1=True,
        stride=1,
        dilation=1,
        dcn_config={},
        middle_k=3,
        use_unfixed_bn=False
    ):
        super(BottleneckWithGN, self).__init__(
            in_channels=in_channels,
            bottleneck_channels=bottleneck_channels,
            out_channels=out_channels,
            num_groups=num_groups,
            stride_in_1x1=stride_in_1x1,
            stride=stride,
            dilation=dilation,
            norm_func=group_norm,
            dcn_config=dcn_config,
            middle_k=middle_k,
            use_unfixed_bn=use_unfixed_bn
        )


class StemWithGN(BaseStem):
    def __init__(self, cfg):
        super(StemWithGN, self).__init__(cfg, norm_func=group_norm)


_TRANSFORMATION_MODULES = Registry({
    "BottleneckWithFixedBatchNorm": BottleneckWithFixedBatchNorm,
    "BottleneckWithGN": BottleneckWithGN,
})

_STEM_MODULES = Registry({
    "StemWithFixedBatchNorm": StemWithFixedBatchNorm,
    "StemWithGN": StemWithGN,
})

_STAGE_SPECS = Registry({
    "R-50-C4": ResNet50StagesTo4,
    "R-50-C5": ResNet50StagesTo5,
    "R-101-C4": ResNet101StagesTo4,
    "R-101-C5": ResNet101StagesTo5,
    "R-50-FPN": ResNet50FPNStagesTo5,
    "R-50-FPN-RETINANET": ResNet50FPNStagesTo5,
    "R-101-FPN": ResNet101FPNStagesTo5,
    "R-101-FPN-RETINANET": ResNet101FPNStagesTo5,
    "R-152-FPN": ResNet152FPNStagesTo5,

    "R-50-3_4_2": ResNet50_3_4_2,
    "R-50-3_4_8": ResNet50_3_4_8,
    "R-50-3_4_14": ResNet50_3_4_14,
    "R-50-3_4_20": ResNet50_3_4_20,
})

# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved.
from collections import OrderedDict

from torch import nn

from maskrcnn_benchmark.modeling import registry
from maskrcnn_benchmark.modeling.make_layers import conv_with_kaiming_uniform
from . import fpn as fpn_module
from . import resnet
from . import ddpp
from . import custom_resnet
from . import selector
from . import resreg


@registry.BACKBONES.register("R-50-C4")
@registry.BACKBONES.register("R-50-C5")
@registry.BACKBONES.register("R-101-C4")
@registry.BACKBONES.register("R-101-C5")
@registry.BACKBONES.register("R-50-3_4_2")
@registry.BACKBONES.register("R-50-3_4_8")
@registry.BACKBONES.register("R-50-3_4_14")
@registry.BACKBONES.register("R-50-3_4_20")
def build_resnet_backbone(cfg):
    body = resnet.ResNet(cfg)
    if cfg.MODEL.BACKBONE.RESREG == 4:
        rr = resreg.Up4x(cfg)
        model = nn.Sequential(OrderedDict([("body", body), ("resreg", rr)]))
    elif cfg.MODEL.BACKBONE.RESREG == 2:
        rr = resreg.Up2x(cfg)
        model = nn.Sequential(OrderedDict([("body", body), ("resreg", rr)]))
    elif cfg.MODEL.BACKBONE.RESREG == -2:
        rr = resreg.Down2x(cfg)
        model = nn.Sequential(OrderedDict([("body", body), ("resreg", rr)]))
    elif cfg.MODEL.BACKBONE.RESREG == 1:
        rr = resreg.Keep1x(cfg)
        model = nn.Sequential(OrderedDict([("body", body), ("resreg", rr)]))
    elif cfg.MODEL.BACKBONE.RESREG == 0:
        model = nn.Sequential(OrderedDict([("body", body)]))
    else:
        print("Invalid cfg.MODEL.BACKBONE.RESREG value")
        exit()
    model.out_channels = cfg.MODEL.RESNETS.BACKBONE_OUT_CHANNELS
    return model


@registry.BACKBONES.register("R-50-FPN")
@registry.BACKBONES.register("R-101-FPN")
@registry.BACKBONES.register("R-152-FPN")
def build_resnet_fpn_backbone(cfg):
    body = resnet.ResNet(cfg)
    in_channels_stage2 = cfg.MODEL.RESNETS.RES2_OUT_CHANNELS
    out_channels = cfg.MODEL.RESNETS.BACKBONE_OUT_CHANNELS
    fpn = fpn_module.FPN(
        in_channels_list=[
            in_channels_stage2,
            in_channels_stage2 * 2,
            in_channels_stage2 * 4,
            in_channels_stage2 * 8,
        ],
        out_channels=out_channels,
        conv_block=conv_with_kaiming_uniform(
            cfg.MODEL.FPN.USE_GN, cfg.MODEL.FPN.USE_RELU
        ),
        top_blocks=fpn_module.LastLevelMaxPool(),
    )
    model = nn.Sequential(OrderedDict([("body", body), ("fpn", fpn)]))
    model.out_channels = out_channels
    return model


@registry.BACKBONES.register("R-50-FPN-RETINANET")
@registry.BACKBONES.register("R-101-FPN-RETINANET")
def build_resnet_fpn_p3p7_backbone(cfg):
    body = resnet.ResNet(cfg)
    in_channels_stage2 = cfg.MODEL.RESNETS.RES2_OUT_CHANNELS
    out_channels = cfg.MODEL.RESNETS.BACKBONE_OUT_CHANNELS
    in_channels_p6p7 = in_channels_stage2 * 8 if cfg.MODEL.RETINANET.USE_C5 \
        else out_channels
    fpn = fpn_module.FPN(
        in_channels_list=[
            0,
            in_channels_stage2 * 2,
            in_channels_stage2 * 4,
            in_channels_stage2 * 8,
        ],
        out_channels=out_channels,
        conv_block=conv_with_kaiming_uniform(
            cfg.MODEL.FPN.USE_GN, cfg.MODEL.FPN.USE_RELU
        ),
        top_blocks=fpn_module.LastLevelP6P7(in_channels_p6p7, out_channels),
    )
    model = nn.Sequential(OrderedDict([("body", body), ("fpn", fpn)]))
    model.out_channels = out_channels
    return model


@registry.BACKBONES.register("DDPP")
@registry.BACKBONES.register("DDPP-SS")
@registry.BACKBONES.register("DDPPv2")
@registry.BACKBONES.register("DDPPv2-SS")
def build_ddpp_backbone(cfg):
    if cfg.MODEL.BACKBONE.CONV_BODY == "DDPP-SS":
        body = ddpp.DDPP_SS(cfg)
    elif cfg.MODEL.BACKBONE.CONV_BODY == "DDPPv2":
        body = ddpp.DDPPv2(cfg)
    elif cfg.MODEL.BACKBONE.CONV_BODY == "DDPPv2-SS":
        body = ddpp.DDPPv2_SS(cfg)
    else:
        body = ddpp.DDPP(cfg)
    model = nn.Sequential(OrderedDict([("body", body)]))
    model.out_channels = cfg.MODEL.DDPP.OUT_CHANNELS_AFTER_CHRED
    return model


@registry.BACKBONES.register("Custom-C4")
def build_custom_resnet_backbone(cfg):
    body = custom_resnet.CustomResNet(cfg)
    model = nn.Sequential(OrderedDict([("body", body)]))
    model.out_channels = cfg.MODEL.CUSTOM_RESNET.OUT_CHANNELS
    return model


def build_backbone(cfg):
    assert cfg.MODEL.BACKBONE.CONV_BODY in registry.BACKBONES, \
        "cfg.MODEL.BACKBONE.CONV_BODY: {} are not registered in registry".format(
            cfg.MODEL.BACKBONE.CONV_BODY
        )
    return registry.BACKBONES[cfg.MODEL.BACKBONE.CONV_BODY](cfg)



# Build ResNet stem
def build_resnet_stem(cfg):
    module = resnet.ResNet_Stem(cfg)
    #module = nn.Sequential(OrderedDict([("stem", module)]))
    return module

# Build a ResNet stage
def build_resnet_stage(cfg, stage, in_channels):
    module = resnet.ResNet_Stage(cfg, stage, in_channels)
    out_channels = module.out_channels
    #module = nn.Sequential(OrderedDict([("module", module)]))
    return module, out_channels

# Build ILA switch
def build_ewa_selector(in_channels, num_branches):
    module = selector.EWAdaptive_Selector(in_channels, num_branches)
    return module

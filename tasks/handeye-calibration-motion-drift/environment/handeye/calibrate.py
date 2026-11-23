import argparse
from pathlib import Path

import yaml

from fk import Kinematics
from handeye import estimate
from sync import load_observations


def main():
    parser = argparse.ArgumentParser(description='Estimate the wrist camera mount from a board recording.')
    parser.add_argument('--session', required=True)
    parser.add_argument('--urdf', required=True)
    parser.add_argument('--camera', required=True)
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    with open(arguments.camera) as stream:
        camera = yaml.safe_load(stream)
    kinematics = Kinematics(arguments.urdf, camera['flange_frame'])
    joints, observations = load_observations(arguments.session, kinematics.joint_names)
    calibration = estimate(kinematics.poses(joints), observations)
    output = Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump({'flange_T_camera': calibration.tolist()}, sort_keys=False))


if __name__ == '__main__':
    main()

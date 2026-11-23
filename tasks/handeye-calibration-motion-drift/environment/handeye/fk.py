import numpy as np
import pinocchio as pin


class Kinematics:
    def __init__(self, urdf, flange='flange'):
        self.model = pin.buildModelFromUrdf(str(urdf))
        self.data = self.model.createData()
        self.frame_id = self.model.getFrameId(flange)
        self.joint_names = list(self.model.names)[1:]

    def poses(self, positions):
        result = []
        for configuration in positions:
            pin.framesForwardKinematics(self.model, self.data, configuration)
            result.append(np.array(self.data.oMf[self.frame_id].homogeneous))
        return np.array(result)

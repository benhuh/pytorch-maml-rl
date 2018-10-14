import numpy as np
from maml_rl.envs.mujoco import mujoco_env

class AntEnv(mujoco_env.MujocoEnv):
    def __init__(self):
        super(AntEnv, self).__init__('ant.xml', frame_skip=1)
        self._action_scaling = None

    @property
    def action_scaling(self):
        if self._action_scaling is None:
            lb, ub = self.action_space.low, self.action_space.high
            self._action_scaling = 0.5 * (ub - lb)
        return self._action_scaling

    def get_current_obs(self):
        return np.concatenate([
            self.sim.data.qpos.flat,
            self.sim.data.qvel.flat,
            np.clip(self.sim.data.cfrc_ext, -1, 1).flat,
            self.get_body_xmat("torso").flat,
            self.get_body_com("torso").flat,
        ]).astype(np.float32).flatten()

class AntVelEnv(AntEnv):
    """Ant environment with target velocity, as described in [1]. The 
    code is adapted from
    https://github.com/cbfinn/maml_rl/blob/9c8e2ebd741cb0c7b8bf2d040c4caeeb8e06cc95/rllab/envs/mujoco/ant_env_rand.py

    The ant follows the dynamics from MuJoCo [2], and receives at each 
    time step a reward composed of a control cost, a contact cost, a survival 
    reward, and a penalty equal to the difference between its current velocity 
    and the target velocity. The tasks are generated by sampling the target 
    velocities from the uniform distribution on [0, 3].

    [1] Chelsea Finn, Pieter Abbeel, Sergey Levine, "Model-Agnostic 
        Meta-Learning for Fast Adaptation of Deep Networks", 2017 
        (https://arxiv.org/abs/1703.03400)
    [2] Emanuel Todorov, Tom Erez, Yuval Tassa, "MuJoCo: A physics engine for 
        model-based control", 2012 
        (https://homes.cs.washington.edu/~todorov/papers/TodorovIROS12.pdf)
    """
    def __init__(self, task={}):
        self._task = task
        self._goal_vel = task.get('velocity', 0.0)
        self._action_scaling = None
        super(AntVelEnv, self).__init__()

    def step(self, action):
        self.forward_dynamics(action)

        forward_vel = self.get_body_comvel("torso")[0]
        forward_reward = -1.0 * np.abs(forward_vel - self._goal_vel) + 1.0
        survive_reward = 0.05

        ctrl_cost = 0.5 * 1e-2 * np.sum(np.square(action / self.action_scaling))
        contact_cost = 0.5 * 1e-3 * np.sum(
            np.square(np.clip(self.sim.data.cfrc_ext, -1, 1)))

        observation = self.get_current_obs()
        reward = forward_reward - ctrl_cost - contact_cost + survive_reward
        state = self.state_vector()
        notdone = np.isfinite(state).all() \
            and state[2] >= 0.2 and state[2] <= 1.0
        done = not notdone
        infos = dict(reward_forward=forward_reward, reward_ctrl=-ctrl_cost,
            reward_contact=-contact_cost, reward_survive=survive_reward,
            task=self._task)
        return (observation, reward, done, infos)

    def sample_tasks(self, num_tasks):
        velocities = self.np_random.uniform(0.0, 3.0, size=(num_tasks,))
        tasks = [{'velocity': velocity} for velocity in velocities]
        return tasks

    def reset_task(self, task):
        self._task = task
        self._goal_vel = task['velocity']

class AntDirEnv(AntEnv):
    """Ant environment with target direction, as described in [1]. The 
    code is adapted from
    https://github.com/cbfinn/maml_rl/blob/9c8e2ebd741cb0c7b8bf2d040c4caeeb8e06cc95/rllab/envs/mujoco/ant_env_rand_direc.py

    The ant follows the dynamics from MuJoCo [2], and receives at each 
    time step a reward composed of a control cost, a contact cost, a survival 
    reward, and a reward equal to its velocity in the target direction. The 
    tasks are generated by sampling the target directions from a Bernoulli 
    distribution on {-1, 1} with parameter 0.5 (-1: backward, +1: forward).

    [1] Chelsea Finn, Pieter Abbeel, Sergey Levine, "Model-Agnostic 
        Meta-Learning for Fast Adaptation of Deep Networks", 2017 
        (https://arxiv.org/abs/1703.03400)
    [2] Emanuel Todorov, Tom Erez, Yuval Tassa, "MuJoCo: A physics engine for 
        model-based control", 2012 
        (https://homes.cs.washington.edu/~todorov/papers/TodorovIROS12.pdf)
    """
    def __init__(self, task={}):
        self._task = task
        self._goal_dir = task.get('direction', 1)
        self._action_scaling = None
        super(AntDirEnv, self).__init__()

    def step(self, action):
        self.forward_dynamics(action)

        forward_vel = self.get_body_comvel("torso")[0]
        forward_reward = self._goal_dir * forward_vel
        survive_reward = 0.05

        ctrl_cost = 0.5 * 1e-2 * np.sum(np.square(action / self.action_scaling))
        contact_cost = 0.5 * 1e-3 * np.sum(
            np.square(np.clip(self.sim.data.cfrc_ext, -1, 1)))

        observation = self.get_current_obs()
        reward = forward_reward - ctrl_cost - contact_cost + survive_reward
        state = self.state_vector()
        notdone = np.isfinite(state).all() \
            and state[2] >= 0.2 and state[2] <= 1.0
        done = not notdone
        infos = dict(reward_forward=forward_reward, reward_ctrl=-ctrl_cost,
            reward_contact=-contact_cost, reward_survive=survive_reward,
            task=self._task)
        return (observation, reward, done, infos)

    def sample_tasks(self, num_tasks):
        directions = 2 * self.np_random.binomial(1, p=0.5, size=(num_tasks,)) - 1
        tasks = [{'direction': direction} for direction in directions]
        return tasks

    def reset_task(self, task):
        self._task = task
        self._goal_dir = task['direction']

class AntPosEnv(AntEnv):
    """Ant environment with target position. The code is adapted from
    https://github.com/cbfinn/maml_rl/blob/9c8e2ebd741cb0c7b8bf2d040c4caeeb8e06cc95/rllab/envs/mujoco/ant_env_rand_goal.py

    The ant follows the dynamics from MuJoCo [1], and receives at each 
    time step a reward composed of a control cost, a contact cost, a survival 
    reward, and a penalty equal to its L1 distance to the target position. The 
    tasks are generated by sampling the target positions from the uniform 
    distribution on [-3, 3]^2.

    [1] Emanuel Todorov, Tom Erez, Yuval Tassa, "MuJoCo: A physics engine for 
        model-based control", 2012 
        (https://homes.cs.washington.edu/~todorov/papers/TodorovIROS12.pdf)
    """
    def __init__(self, task={}):
        self._task = task
        self._goal_pos = task.get('position', np.zeros((2,), dtype=np.float32))
        self._action_scaling = None
        super(AntPosEnv, self).__init__()

    def step(self, action):
        self.forward_dynamics(action)
        xyposafter = self.get_body_com("torso")[:2]

        goal_reward = -np.sum(np.abs(xyposafter - self._goal_pos)) + 4.0
        survive_reward = 0.05

        ctrl_cost = 0.5 * 1e-2 * np.sum(np.square(action / self.action_scaling))
        contact_cost = 0.5 * 1e-3 * np.sum(
            np.square(np.clip(self.sim.data.cfrc_ext, -1, 1)))

        observation = self.get_current_obs()
        reward = goal_reward - ctrl_cost - contact_cost + survive_reward
        state = self.state_vector()
        notdone = np.isfinite(state).all() \
            and state[2] >= 0.2 and state[2] <= 1.0
        done = not notdone
        infos = dict(reward_goal=goal_reward, reward_ctrl=-ctrl_cost,
            reward_contact=-contact_cost, reward_survive=survive_reward,
            task=self._task)
        return (observation, reward, done, infos)

    def sample_tasks(self, num_tasks):
        positions = self.np_random.uniform(-3.0, 3.0, size=(num_tasks, 2))
        tasks = [{'position': position} for position in positions]
        return tasks

    def reset_task(self, task):
        self._task = task
        self._goal_pos = task['position']

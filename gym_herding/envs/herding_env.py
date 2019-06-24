"""
Herding Experiment environment:

Description

Action Space:
    - Where to move: (Up, Down, Left, Right, Stay)

Written by: Zahi Kakish

"""
import sys
from contextlib import closing
from six import StringIO
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from gym import Env
from gym.spaces import Box
from gym.spaces import Discrete
from gym_herding.envs.graph import NodeGraph
from gym_herding.envs.leader import Leader
from gym_herding.envs.parameters import HerdingEnvParameters
from gym_herding.envs.rendering import HerdingEnvPlotting


class HerdingEnv(Env):
    """
    Herding OpenAI Environment

    Parameters
    ----------
    hep : HerdingEnvParameters
        Parameters required for the Herding Environment.
    observation_space : {1, 2, 3}, optional
        Choose the size of the observation space that is returned by the
        `step()` method and used by the remainder of the `HerdingEnv`.

    """
    MOVEMENTS = ["left", "right", "up", "down", "stay"]
    def __init__(self, hep=None, observation_space=3):
        # Set immutable params and mutable variables
        self.param = hep
        self.var = {
            "is_out_of_bounds": False,
        }

        if self.param is None:
            print("Please provide environment parameters in the " + \
                  "HerdingEnvParamters object\nbefore continuing!")

        else:
            self.initialize(hep, observation_space)

    def initialize(self, hep, observation_space=3):
        """ Initializes the OpenAI Environment """
        # Set plotting class
        self._plot = HerdingEnvPlotting(
            self.param.n_v, self.param.n_p)

        # Instantiate Graph, Agents, and Leader object.
        self._graph = NodeGraph(
            self.param.n_v, self.param.n_p,self.param.weights)
        self._leader = Leader(
            0, self.param.n_v, self.param.extra["init_leader_pos"][0],
            self.param.extra["init_leader_pos"][1])

        # Initialize Graph, Agent, and Leader values.
        self._initialize_env_objects()

        ## Observation Space
        # Testing with multiple observation spaces
        #     Test 1: Dist in the current node (1)
        #     Test 2: Dist in left, right, up, down, and current node (5)
        #     Test 3: The whole state-space (n_v^2)
        if observation_space == 1:
            self.observation_space = Box(
                low=0, high=1, shape=(1,), dtype=np.float32)

        elif observation_space == 2:
            self.observation_space = Box(
                low=0, high=1, shape=(5,), dtype=np.float32)

        elif observation_space == 3:
            self.observation_space = Box(
                low=0, high=1, shape=(self.param.n_v, self.param.n_v),
                dtype=np.float32)

        ## Action Space
        # Should be only possible path actions that the agent can go through,
        # and in this case it is either:
        #     0 - Left
        #     1 - Right
        #     2 - Up
        #     3 - Down
        #     4 - Stay
        self.action_space = Discrete(5)

        # Initialize rendering environment (matplotlib)
        self._plot.create_figure()

    def step(self, action):
        """ Executes the given action """
        # Get new leader state and position from action
        new_lx, new_ly, new_ls, is_out_of_bounds = \
            self._graph.convert_action_to_node_info(self._leader.state, action)

        # If action takes leader out of bounds, change info state to say that
        # occured.
        self.var["is_out_of_bounds"] = is_out_of_bounds

        # Apply changes to leaders position and state onto the class
        self._move_leader(new_ls, new_lx, new_ly)

        # Apply repulsive effect of leader in new location on those local
        # herding agents.
        if self.param.extra["leader_motion_moves_agents"]:
            self._move_herding_agents()

        # Apply repulsive effect of leader in new location on those local
        # herding agents ONLY IF action STAY is used.
        else:
            if action == 4:  # Stay
                self._move_herding_agents()

        # Get newest observation of the state space.
        obs = self._get_observation()

        # Get reward for action
        # reward = self._get_reward_greedy(new_lx, new_ly)
        reward = self._get_reward(action)
        done = False

        # Write info
        info = {
            "is_out_of_bounds": self.var["is_out_of_bounds"],
            "leader_state": self._leader.state,
            "leader_pos": [new_lx, new_ly],
        }

        # Check for end of episode
        if self.param.iter == self.param.max_iter:
            done = True

        else:
            self.param.iter += 1

        return (obs, reward, done, info)

    def reset(self):
        """ Initializies the environment to initial state for next episode """
        self._graph.reset()
        self._graph.update_count()
        self._leader.reset()
        self.param.iter = 0
        self.param.extra["t"] = 0

        # Returns the current reset observational space.
        return self._graph.distribution.current

    def render(self):
        """ Displays the environment """
        self._plot.render(self._graph, self._leader)

    def save_render(self, file_name):
        """ Save image of the render """
        self._plot.save_render(file_name)

    def close(self):
        """ Something """
        pass

    def is_action_valid(self, action):
        """ Checks if the leader agent action is valid """
        if action == 0:  # Left
            if self._leader.state % self.param.n_v != 0:
                return True

        elif action == 1:  # Right
            if (self._leader.state  + 1) % self.param.n_v != 0:
                return True

        elif action == 2:  # Up
            if self._leader.state < (self.param.n_v * (self.param.n_v - 1)):
                return True

        elif action == 3:  # Down
            if self._leader.state > self.param.n_v:
                return True

        elif action == 4:  # Stay
            return True

        return False

    def _initialize_env_objects(self):
        """ Initialize environment object values """
        self._graph.distribution.target = self.param.dist["target"]
        self._graph.distribution.initial = self.param.dist["initial"]
        for dist in ["initial", "current", "target"]:
            self._graph.distribution.apply_population(dist)

        self._graph.set_node_positions()
        self._graph.set_node_neighbors()
        self._graph.update_count()

    def _get_reward_greedy(self, new_lx, new_ly):
        """ Get greedy reward from current state of Leader and Agents """
        target_dist = self._graph.distribution.get_node_value(
            new_lx, new_ly, "target")
        current_dist = self._graph.distribution.get_node_value(
            new_lx, new_ly, "current")

        return current_dist - target_dist

    def _get_reward(self, action):
        """
        Get reward that is the sum of the difference of the target and
        current distribution
        """
        return -1 * np.sum(np.power(
            self._graph.distribution.current - self._graph.distribution.target, 2))

    def _get_observation(self):
        """ Get the calculated observation of environment state """
        return self._graph.distribution.current

    def _move_herding_agents(self):
        """ Moves the herding agents within the environment """
        # Get number of agents within the node that the leader is in
        chk_ld = self._graph.node[self._leader.state].agent_count

        # Increment time
        self.param.extra["t"] += self.param.extra["dt"]

        # Generate random number to see if agent should change node
        if chk_ld != 1:
            toss = np.squeeze(np.random.rand(1, chk_ld))

        else:
            # Squeeze reduces too much if chk_ld == 1
            toss = np.random.rand(1, chk_ld)[0]

        for i in range(chk_ld):
            temp_neigh = self._graph.node[self._leader.state].neighbors

            if toss[i] <= len(temp_neigh) * self.param.extra["jump_weight"]:
                # Get the new state for the agent to jump to
                rand_perm = np.random.permutation(len(temp_neigh))
                jump_state = self._graph.get_state(
                    temp_neigh[rand_perm[0], :])

                # Helpful variables
                old_x, old_y = self._graph.get_position(self._leader.state)
                new_x, new_y = self._graph.get_position(jump_state)

                # Update current distribution map
                # TODO: May need to remove these vvvv
                self._graph.node[self._leader.state].agent_count -= 1
                self._graph.node[jump_state].agent_count += 1
                self._graph.distribution.increment_node_value(
                    -1, old_x, old_y, "current")
                self._graph.distribution.increment_node_value(
                    1, new_x, new_y, "current")

    def _move_leader(self, new_ls, new_lx, new_ly):
        """ Moves the leader to the next position """
        self._leader.state = new_ls
        self._leader.real = np.array([new_lx, new_ly], dtype=np.int8)
        self._leader.visual = np.array([new_lx, new_ly], dtype=np.int8)

    def _valid_action_check(self, action):
        """ Checks if the leader agent action is valid """
        if action == 0:  # Left
            if self._leader.state % self.param.n_v != 0:
                return True

        elif action == 1:  # Right
            if (self._leader.state  + 1) % self.param.n_v != 0:
                return True

        elif action == 2:  # Up
            if self._leader.state < (self.param.n_v * (self.param.n_v - 1)):
                return True

        elif action == 3:  # Down
            if self._leader.state > self.param.n_v:
                return True

        elif action == 5:  # Stay
            return True

        return False

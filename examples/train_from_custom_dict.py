# Copyright 2022-2023 OmniSafe Team. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Example of training a policy from custom dict with OmniSafe."""

import argparse

import omnisafe


parser = argparse.ArgumentParser()
env_id = 'SafetyHumanoidVelocity-v4'
parser.add_argument(
    '--parallel',
    default=1,
    type=int,
    metavar='N',
    help='Number of paralleled progress for calculations.',
)
custom_dict = {'epochs': 1, 'data_dir': './runs'}
args, _ = parser.parse_known_args()
agent = omnisafe.Agent('PPOLag', env_id, custom_cfgs=custom_dict, parallel=args.parallel)
agent.learn()

# obs = env.reset()
# for i in range(1000):
#     action, _states = agent.predict(obs, deterministic=True)
#     obs, reward, done, info = env.step(action)
#     env.render()
#     if done:
#         obs = env.reset()
# env.close()

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
"""Implementation of the PID-Lagrange version of the TRPO algorithm."""

from typing import Dict, NamedTuple, Tuple

import torch

from omnisafe.algorithms import registry
from omnisafe.algorithms.on_policy.base.trpo import TRPO
from omnisafe.common.pid_lagrange import PIDLagrangian


@registry.register
class TRPOPid(TRPO, PIDLagrangian):
    """The PID-Lagrange version of the TRPO algorithm.

    References:
        - Title: Responsive Safety in Reinforcement Learning by PID Lagrangian Methods
        - Authors: Joshua Achiam, David Held, Aviv Tamar, Pieter Abbeel.
        - URL: https://arxiv.org/abs/2007.03964
    """

    def __init__(self, env_id: str, cfgs: NamedTuple) -> None:
        """Initialize TRPOPid.

        TRPOPid is a simple combination of :class:`TRPO` and :class:`PIDLagrangian`.

        Args:
            env_id (str): The environment id.
            cfgs (NamedTuple): The configuration of the algorithm.
        """
        TRPO.__init__(
            self,
            env_id=env_id,
            cfgs=cfgs,
        )
        PIDLagrangian.__init__(self, **self.cfgs.PID_cfgs)
        self.cost_limit = self.cfgs.cost_limit

    def _specific_init_logs(self):
        super()._specific_init_logs()
        self.logger.register_key('Metrics/LagrangeMultiplier')
        self.logger.register_key('PID/pid_Kp')
        self.logger.register_key('PID/pid_Ki')
        self.logger.register_key('PID/pid_Kd')

    def algorithm_specific_logs(self) -> None:
        """Log the TRPOPid specific information.

        .. list-table::

            *   -   Things to log
                -   Description
            *   -   Metrics/LagrangeMultiplier
                -   The Lagrange multiplier value in current epoch.
            *   -   PID/pid_Kp
                -   The Kp value in current epoch.
            *   -   PID/pid_Ki
                -   The Ki value in current epoch.
            *   -   PID/pid_Kd
                -   The Kd value in current epoch.
        """
        super().algorithm_specific_logs()
        self.logger.store(
            **{
                'Metrics/LagrangeMultiplier': self.cost_penalty,
                'PID/pid_Kp': self.pid_kp,
                'PID/pid_Ki': self.pid_ki,
                'PID/pid_Kd': self.pid_kd,
            }
        )

    # pylint: disable-next=too-many-arguments
    def compute_loss_pi(
        self,
        obs: torch.Tensor,
        act: torch.Tensor,
        log_p: torch.Tensor,
        adv: torch.Tensor,
    ) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        r"""
        Computing pi/actor loss.
        In CPPOPid, the loss is defined as:

        .. math::
            L = \mathbb{E}_{s_t \sim \rho_{\pi}} \left[ \frac{\pi_\theta(a_t|s_t)}
            {\pi_\theta^{old}(a_t|s_t)} [A^{R}_t(s_t, a_t) - \lambda A^{C}_t(s_t, a_t)] \right]

        where :math:`A^{R}_t` is the advantage from the reward and :math:`A^{C}_t` is the advantage from the cost,
        and :math:`\lambda` is the Lagrange multiplier controlled by the PID controller.

        Args:
            obs (torch.Tensor): :meth:`observation` stored in buffer.
            act (torch.Tensor): :meth:`action` stored in buffer.
            log_p (torch.Tensor): ``log probability`` of action stored in buffer.
            adv (torch.Tensor): :meth:`advantage` stored in buffer.
            cost_adv (torch.Tensor): :meth:`cost advantage` stored in buffer.
        """
        dist, _log_p = self.actor_critic.actor(obs, act)
        ratio = torch.exp(_log_p - log_p)

        # compute loss via ratio and advantage
        loss_pi = -(ratio * adv).mean()
        loss_pi -= self.cfgs.entropy_coef * dist.entropy().mean()

        # useful extra info
        approx_kl = 0.5 * (log_p - _log_p).mean().item()
        ent = dist.entropy().mean().item()
        pi_info = {'kl': approx_kl, 'ent': ent, 'ratio': ratio.mean().item()}

        return loss_pi, pi_info

    def compute_surrogate(
        self,
        adv: torch.Tensor,
        cost_adv: torch.Tensor,
    ) -> torch.Tensor:
        """Compute surrogate loss.

        TRPOPid uses the Lagrange method to combine the reward and cost.
        The surrogate loss is defined as the difference between the reward
        advantage and the cost advantage

        Args:
            adv (torch.Tensor): reward advantage
            cost_adv (torch.Tensor): cost advantage
        """
        return (adv - self.cost_penalty * cost_adv) / (1 + self.cost_penalty)

    def update(self) -> Tuple[Dict[str, torch.Tensor], Dict[str, torch.Tensor]]:
        r"""Update actor, critic, running statistics as we used in the :class:`TRPO` algorithm.

        Additionally, we update the Lagrange multiplier parameter,
        by calling the :meth:`update_lagrange_multiplier` method.
        """
        # note that logger already uses MPI statistics across all processes.
        Jc = self.logger.get_stats('Metrics/EpCost')[0]
        # first update Lagrange multiplier parameter
        self.pid_update(Jc)
        # then update the policy and value net.
        TRPO.update(self)

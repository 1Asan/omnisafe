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
"""Implementation of the Reward Constrained Policy Optimization algorithm."""

from typing import Dict, NamedTuple, Tuple

import torch

from omnisafe.algorithms import registry
from omnisafe.algorithms.on_policy.base.natural_pg import NaturalPG
from omnisafe.common.lagrange import Lagrange


@registry.register
class RCPO(NaturalPG, Lagrange):
    """Reward Constrained Policy Optimization.

    References:
        - Title: Reward Constrained Policy Optimization.
        - Authors: Chen Tessler, Daniel J. Mankowitz, Shie Mannor.
        - URL: `Reward Constrained Policy Optimization <https://arxiv.org/abs/1805.11074>`_
    """

    def __init__(self, env_id: str, cfgs: NamedTuple) -> None:
        """Initialize RCPO.

        RCPO is a combination of :class:`NaturalPG` and :class:`Lagrange` model.

        Args:
            env_id (str): The environment id.
            cfgs (NamedTuple): The configuration of the algorithm.
        """
        NaturalPG.__init__(
            self,
            env_id=env_id,
            cfgs=cfgs,
        )
        Lagrange.__init__(
            self,
            cost_limit=self.cfgs.lagrange_cfgs.cost_limit,
            lagrangian_multiplier_init=self.cfgs.lagrange_cfgs.lagrangian_multiplier_init,
            lambda_lr=self.cfgs.lagrange_cfgs.lambda_lr,
            lambda_optimizer=self.cfgs.lagrange_cfgs.lambda_optimizer,
        )

    def _specific_init_logs(self):
        super()._specific_init_logs()
        self.logger.register_key('Metrics/LagrangeMultiplier')

    def update(self) -> Tuple[Dict[str, torch.Tensor], Dict[str, torch.Tensor]]:
        r"""Update actor, critic, running statistics as we used in the :class:`NaturalPG` algorithm.

        Additionally, we update the Lagrange multiplier parameter,
        by calling the :meth:`update_lagrange_multiplier` method.

        .. note::
            The :meth:`compute_loss_pi` is defined in the :class:`PolicyGradient` algorithm.
            When a lagrange multiplier is used,
            the :meth:`compute_loss_pi` method will return the loss of the policy as:

            .. math::
                L_{\pi} = \mathbb{E}_{s_t \sim \rho_{\pi}} \left[ \frac{\pi_\theta(a_t|s_t)}{\pi_\theta^{old}(a_t|s_t)}
                [A^{R}(s_t, a_t) - \lambda A^{C}(s_t, a_t)] \right]

            where :math:`\lambda` is the Lagrange multiplier parameter.
        """
        # note that logger already uses MPI statistics across all processes..
        Jc = self.logger.get_stats('Metrics/EpCost')[0]
        # first update Lagrange multiplier parameter
        self.update_lagrange_multiplier(Jc)
        # then update the policy and value net.
        NaturalPG.update(self)

    def compute_surrogate(
        self,
        adv: torch.Tensor,
        cost_adv: torch.Tensor,
    ) -> torch.Tensor:
        """Compute surrogate loss.

        RCPO uses the Lagrange method to combine the reward and cost.
        The surrogate loss is defined as the difference between the reward
        advantage and the cost advantage

        Args:
            adv (torch.Tensor): reward advantage
            cost_adv (torch.Tensor): cost advantage
        """
        penalty = self.lambda_range_projection(self.lagrangian_multiplier).item()
        return (adv - penalty * cost_adv) / (1 + penalty)

    def algorithm_specific_logs(self) -> None:
        """Log the RCPO specific information.

        .. list-table::

            *   -   Things to log
                -   Description
            *   -   Metrics/LagrangeMultiplier
                -   The Lagrange multiplier value in current epoch.
        """
        super().algorithm_specific_logs()
        self.logger.store(
            **{
                'Metrics/LagrangeMultiplier': self.lagrangian_multiplier.item(),
            }
        )

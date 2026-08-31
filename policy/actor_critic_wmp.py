import torch
import torch.nn as nn
from torch.distributions import Normal

from .utils import resolve_nn_activation


class ActorCriticWMP(nn.Module):
    is_recurrent = False

    def __init__(
        self,
        num_actor_obs,
        num_critic_obs,
        num_actions,
        encoder_hidden_dims=[256, 128],
        wm_encoder_hidden_dims=[64, 32],
        actor_hidden_dims=[256, 256, 256],
        critic_hidden_dims=[256, 256, 256],
        activation="elu",
        init_noise_std=1.0,
        fixed_std=False,
        latent_dim=32,
        height_dim=187,
        privileged_dim=3 + 24,
        history_dim=42 * 5,
        wm_feature_dim=1536,
        wm_latent_dim=16,
        **kwargs,
    ):
        if kwargs:
            print(
                "ActorCritic.__init__ got unexpected arguments, which will be ignored: "
                + str([key for key in kwargs.keys()])
            )
        super().__init__()

        activation = resolve_nn_activation(activation)

        self.latent_dim = latent_dim
        self.height_dim = height_dim
        self.privileged_dim = privileged_dim

        mlp_input_dim_a = (
            latent_dim + num_actor_obs - privileged_dim - height_dim + wm_latent_dim
        )  # latent vector + num_actor_obs + wm_latent
        mlp_input_dim_c = num_critic_obs + wm_latent_dim

        # History Encoder
        encoder_layers = []
        encoder_layers.append(nn.Linear(history_dim, encoder_hidden_dims[0]))
        encoder_layers.append(activation)
        for layer_index in range(len(encoder_hidden_dims)):
            if layer_index == len(encoder_hidden_dims) - 1:
                encoder_layers.append(nn.Linear(encoder_hidden_dims[layer_index], latent_dim))
            else:
                encoder_layers.append(nn.Linear(encoder_hidden_dims[layer_index], encoder_hidden_dims[layer_index + 1]))
                encoder_layers.append(activation)
        self.history_encoder = nn.Sequential(*encoder_layers)

        # World Model Feature Encoder
        wm_encoder_layers = []
        wm_encoder_layers.append(nn.Linear(wm_feature_dim, wm_encoder_hidden_dims[0]))
        wm_encoder_layers.append(activation)
        for layer_index in range(len(wm_encoder_hidden_dims)):
            if layer_index == len(wm_encoder_hidden_dims) - 1:
                wm_encoder_layers.append(nn.Linear(wm_encoder_hidden_dims[layer_index], wm_latent_dim))
            else:
                wm_encoder_layers.append(
                    nn.Linear(wm_encoder_hidden_dims[layer_index], wm_encoder_hidden_dims[layer_index + 1])
                )
                wm_encoder_layers.append(activation)
        self.wm_feature_encoder = nn.Sequential(*wm_encoder_layers)

        # Critic World Model Feature Encoder
        critic_wm_encoder_layers = []
        critic_wm_encoder_layers.append(nn.Linear(wm_feature_dim, wm_encoder_hidden_dims[0]))
        critic_wm_encoder_layers.append(activation)
        for layer_index in range(len(wm_encoder_hidden_dims)):
            if layer_index == len(wm_encoder_hidden_dims) - 1:
                critic_wm_encoder_layers.append(nn.Linear(wm_encoder_hidden_dims[layer_index], wm_latent_dim))
            else:
                critic_wm_encoder_layers.append(
                    nn.Linear(wm_encoder_hidden_dims[layer_index], wm_encoder_hidden_dims[layer_index + 1])
                )
                critic_wm_encoder_layers.append(activation)
        self.critic_wm_feature_encoder = nn.Sequential(*critic_wm_encoder_layers)

        # Policy
        actor_layers = []
        actor_layers.append(nn.Linear(mlp_input_dim_a, actor_hidden_dims[0]))
        actor_layers.append(activation)
        for layer_index in range(len(actor_hidden_dims)):
            if layer_index == len(actor_hidden_dims) - 1:
                actor_layers.append(nn.Linear(actor_hidden_dims[layer_index], num_actions))
                # actor_layers.append(nn.Tanh())
            else:
                actor_layers.append(nn.Linear(actor_hidden_dims[layer_index], actor_hidden_dims[layer_index + 1]))
                actor_layers.append(activation)
        self.actor = nn.Sequential(*actor_layers)

        # Value function
        critic_layers = []
        critic_layers.append(nn.Linear(mlp_input_dim_c, critic_hidden_dims[0]))
        critic_layers.append(activation)
        for layer_index in range(len(critic_hidden_dims)):
            if layer_index == len(critic_hidden_dims) - 1:
                critic_layers.append(nn.Linear(critic_hidden_dims[layer_index], 1))
            else:
                critic_layers.append(nn.Linear(critic_hidden_dims[layer_index], critic_hidden_dims[layer_index + 1]))
                critic_layers.append(activation)

        self.critic = nn.Sequential(*critic_layers)

        print(f"Actor MLP: {self.actor}")
        print(f"Critic MLP: {self.critic}")

        # Action noise
        self.fixed_std = fixed_std
        std = init_noise_std * torch.ones(num_actions)
        self.std = torch.tensor(std) if fixed_std else nn.Parameter(std)
        self.distribution = None
        # disable args validation for speedup
        Normal.set_default_validate_args = False

    @staticmethod
    # not used at the moment
    def init_weights(sequential, scales):
        [
            torch.nn.init.orthogonal_(module.weight, gain=scales[idx])
            for idx, module in enumerate(mod for mod in sequential if isinstance(mod, nn.Linear))
        ]

    def reset(self, dones=None):
        pass

    def forward(self):
        raise NotImplementedError

    @property
    def action_mean(self):
        return self.distribution.mean

    @property
    def action_std(self):
        return self.distribution.stddev

    @property
    def entropy(self):
        return self.distribution.entropy().sum(dim=-1)

    def update_distribution(self, observations):
        mean = self.actor(observations)
        std = self.std.to(mean.device)
        self.distribution = Normal(mean, mean * 0.0 + std)

    def act(self, observations, history, wm_feature, **kwargs):
        latent_vector = self.history_encoder(history)
        # obs = observations[:, self.privileged_dim : -self.height_dim]
        wm_latent_vector = self.wm_feature_encoder(wm_feature)
        concat_observations = torch.concat((latent_vector, observations, wm_latent_vector), dim=-1)
        actions_mean = self.actor(concat_observations)
        return actions_mean

    def get_latent_vector(self, observations, history, **kwargs):
        latent_vector = self.history_encoder(history)
        return latent_vector

    def get_linear_vel(self, observations, history, **kwargs):
        latent_vector = self.history_encoder(history)
        linear_vel = latent_vector[:, -3:]
        return linear_vel

    def get_actions_log_prob(self, actions):
        return self.distribution.log_prob(actions).sum(dim=-1)

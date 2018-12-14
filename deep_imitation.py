import gym
import itertools
import matplotlib.pyplot as plt
import numpy as np
import csv
import tensorflow as tf
import random
import keyboard as kbd
from tensorflow.contrib import layers as layers
from pickle import dumps,loads

import baselines.common.tf_util as U

from baselines import logger
from baselines import deepq
from baselines.deepq.replay_buffer import ReplayBuffer
from baselines.deepq.utils import ObservationInput
from baselines.common.schedules import LinearSchedule

def model(inpt, num_actions, scope, reuse=False):
    """This model takes as input an observation and returns values of all actions."""
    with tf.variable_scope(scope, reuse=reuse):
        out = inpt
        out = layers.fully_connected(out, num_outputs=64, activation_fn=tf.nn.tanh)
        out = layers.fully_connected(out, num_outputs=num_actions, activation_fn=None)
        return out

def readMentorExperieces():
    mentor_tr = []
    
    print("--Creating mentor_demonstrations buffer..")

    with open('mentor_demonstrations_NN_0.csv', 'r', newline='') as csvfile:
        data_reader = csv.reader(csvfile, delimiter=',')
        for r in data_reader:
            mentor_tr.append([float(i) for i in r])
    with open('mentor_demonstrations_NN_1.csv', 'r', newline='') as csvfile:
        data_reader = csv.reader(csvfile, delimiter=',')
        for r in data_reader:
            mentor_tr.append([float(i) for i in r])
    with open('mentor_demonstrations_NN_2.csv', 'r', newline='') as csvfile:
        data_reader = csv.reader(csvfile, delimiter=',')
        for r in data_reader:
            mentor_tr.append([float(i) for i in r])
    with open('mentor_demonstrations_NN_3.csv', 'r', newline='') as csvfile:
        data_reader = csv.reader(csvfile, delimiter=',')
        for r in data_reader:
            mentor_tr.append([float(i) for i in r])
    with open('mentor_demonstrations_NN_4.csv', 'r', newline='') as csvfile:
        data_reader = csv.reader(csvfile, delimiter=',')
        for r in data_reader:
            mentor_tr.append([float(i) for i in r])
    return mentor_tr

def similarityCheck(obs, ment, ment_act):
    # Check if the new state s' is similar to any state visited by the mentor.
    # The similarity threshold is set heuristicaly to 20% difference.
    sim_thres_perc = 20
    similarities = []

    for i in range(len(ment)-1):
        comparisons = []
        m_s = ment[i]

        for j in range(len(m_s)):
            diff_perc = ((obs[j] - m_s[j]) / m_s[j]) * 100
            comp = abs(diff_perc) < sim_thres_perc
            comparisons.append(comp)
        if (all(comparisons)):
            similarities.append(i)

    return similarities

def updateMentorActions(obs, new_obs, ment, ment_act, simList, action, env):
    sim_thres_perc = 20
    mentor_actions_index_list = []

    for i in simList:
        comparisons = []
        m_s = ment[i+1]
        if(ment_act[i] == None):
            for j in range(len(m_s)):
                diff_perc = ((new_obs[j] - m_s[j]) / m_s[j]) * 100
                comp = abs(diff_perc) < sim_thres_perc
                comparisons.append(comp)
            if (all(comparisons)):
                # print("Mentor action found")
                ment_act[i] = action
                mentor_actions_index_list.append(i)
            else:
                comparisons = []
                env.close()
                env_backup = dumps(env)
                for act in range(env.action_space.n):
                    if act != action:
                        tmp_new_obs, tmp_rew, tmp_done, _ = env.step(act)
                        for j in range(len(m_s)):
                            diff_perc = ((tmp_new_obs[j] - m_s[j]) / m_s[j]) * 100
                            comp = abs(diff_perc) < sim_thres_perc
                            comparisons.append(comp)
                        if (all(comparisons)):
                            print("Mentor action found through emulation")
                            ment_act[i] = act
                            mentor_actions_index_list.append(i)
                        env = loads(env_backup)

    return mentor_actions_index_list

def augmentReward(rew, obs, ment, index):
    bias = 20
    newReward = rew + bias
    
    return newReward


if __name__ == '__main__':
    try:
        with U.make_session():
            # Create the environment
            env = gym.make("CartPole-v0")

            # mentor_tr = []
            _gamma = 0.99
            oscillating = False
            mode = "0"

            print("Press 1 to enable imitation, 2 otherwise")
            while mode != "1" and mode != "2":
                mode = input("--> ")

            mentor_tr = readMentorExperieces()

            # Size of mentor's transitions
            N = len(mentor_tr)

            print("--Initializing mentor_actions buffer..")
            mentor_tr_actions = [None] * N

            # Create all the functions necessary to train the model
            act, train, trainAugmented, update_target, debug = deepq.build_train_imitation(
                make_obs_ph=lambda name: ObservationInput(env.observation_space, name=name),
                q_func=model,
                num_actions=env.action_space.n,
                optimizer=tf.train.AdamOptimizer(learning_rate=5e-4),
                gamma=_gamma,
            )
            # Create the replay buffer
            print("--Initializing experience replay buffer..")
            replay_buffer = ReplayBuffer(50000)
            # Create the schedule for exploration starting from 1 (every action is random) down to
            # 0.02 (98% of actions are selected according to values predicted by the model).
            exploration = LinearSchedule(schedule_timesteps=10000, initial_p=1.0, final_p=0.02)

            # Initialize the parameters and copy them to the target network.
            U.initialize()
            update_target()

            episode_rewards = [0.0]
            obs = env.reset()

            t = 0
            is_solved = False

            y = [0]

            while True:
                # Take action and update exploration to the newest value
                action = act(obs[None], update_eps=exploration.value(t))[0]
                new_obs, rew, done, _ = env.step(action)

                # Check if the new state s' is similar to any state visited by the mentor.
                if mode == "1":
                    similarity_list = similarityCheck(obs, mentor_tr, mentor_tr_actions)
                    similarity = len(similarity_list) != 0
                    if similarity and not is_solved:
                        # rew = augmentReward(rew, obs, mentor_tr, similarity_list)
                        ment_index_list = updateMentorActions(obs, new_obs, mentor_tr, mentor_tr_actions, similarity_list, action, env)
                        if len(ment_index_list) > 0:
                            ment_index = random.choice(ment_index_list)
                            ment_obs = mentor_tr[ment_index]
                            ment_obs_tp1 = mentor_tr[ment_index+1]
                            ment_act = mentor_tr_actions[ment_index]
                        else:
                            ment_index = random.choice(similarity_list)
                            ment_obs = mentor_tr[ment_index]
                            ment_obs_tp1 = mentor_tr[ment_index+1]
                            ment_act = random.randint(0, env.action_space.n)
                    else:
                        ment_index = random.randint(0, len(mentor_tr)-2)
                        ment_obs = mentor_tr[ment_index]
                        ment_obs_tp1 = mentor_tr[ment_index+1]
                        ment_act = random.randint(0, env.action_space.n)
                else:
                    ment_obs = []
                    ment_obs_tp1 = []
                    ment_act = 0

                # Store transition in the replay buffer.
                replay_buffer.add(obs, action, rew, new_obs, float(done), ment_obs, ment_obs_tp1, ment_act)

                obs = new_obs
                episode_rewards[-1] += rew

                # Detect oscilation or stalling of reward
                if len(episode_rewards) > 200 and abs(np.mean(episode_rewards[-101:-1]) - np.mean(episode_rewards[-201:-101])) <= 5:
                    oscillating = True
                else:
                    oscillating = False

                if done:
                    obs = env.reset()
                    episode_rewards.append(0)

                is_solved = t > 100 and np.mean(episode_rewards[-101:-1]) >= 200

                if is_solved:
                    # Show off the result
                    env.render()
                else:
                    # Minimize the error in Bellman's equation on a batch sampled from replay buffer.
                    if t > 1000:
                        obses_t, actions, rewards, obses_tp1, dones, ment_obs, ment_obs_tp1, ment_act = replay_buffer.sample(32)
                        if mode == "1":
                            trainAugmented(obses_t, actions, rewards, obses_tp1, dones, np.ones_like(rewards), ment_obs, ment_obs_tp1, ment_act)
                        else:
                            # trainAugmented2(obses_t, actions, rewards, obses_tp1, dones, np.ones_like(rewards), ment_obs, ment_obs_tp1, ment_act)
                            train(obses_t, actions, rewards, obses_tp1, dones, np.ones_like(rewards))

                    # Update target network periodically.
                    if t % 1000 == 0:
                        update_target()

                if done and len(episode_rewards) % 10 == 0:

                    if oscillating:
                        print("OSCILLATING")
                    
                    y.append(round(np.mean(episode_rewards[-101:-1]), 1))
                    cnt = 0
                    for actn in mentor_tr_actions:
                        if actn != None:
                            cnt += 1
                    logger.record_tabular("mentor actions", cnt)
                    logger.record_tabular("steps", t)
                    logger.record_tabular("episodes", len(episode_rewards))
                    # logger.record_tabular("mean episode reward", round(np.mean(episode_rewards[-101:-1]), 1))
                    logger.record_tabular("mean episode reward", np.mean(episode_rewards[-101:-1]))
                    logger.record_tabular("% time spent exploring", int(100 * exploration.value(t)))
                    logger.dump_tabular()

                    x = np.linspace(0, len(episode_rewards), num=len(y))
                    xmax = len(episode_rewards)
                    
                    plt.clf()
                    plt.plot(x, y, label='mean episode reward')
                    plt.axis([0, xmax, 0, 210])
                    plt.xticks(np.arange(0, len(episode_rewards), step=50), rotation=45)
                    plt.yticks(np.arange(0, 210, step=10))
                    plt.xlabel('time')
                    plt.ylabel('reward')
                    plt.title("deep_imitation: mean episode reward")
                    plt.grid(linestyle="-", linewidth="1")
                    plt.legend()
                    plt.pause(0.05)
                
                t += 1
    except KeyboardInterrupt:
        try:
            x = np.linspace(0, len(episode_rewards), num=len(y))
            xmax = len(episode_rewards)
            print(len(x))
            print(len(y))

            plt.clf()
            plt.plot(x, y, label='mean episode reward')
            plt.axis([0, xmax, 0, 210])
            plt.xticks(np.arange(0, len(episode_rewards), step=50), rotation=45)
            plt.yticks(np.arange(0, 210, step=10))
            plt.xlabel('time')
            plt.ylabel('reward')
            plt.title("deep_imitation: mean episode reward")
            plt.grid(linestyle="-", linewidth="1")
            plt.legend()
            plt.show()

            input("Press Enter to exit...")
        except Exception:
            print("\nAn Exception occured...")
            print("Exiting")
    exit()
    plt.show()

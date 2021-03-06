import random
import time
import sys
import numpy as np
import tensorflow as tf

from blocks.plots import visualize_samples

class Learner(object):

    def __init__(self, session, parallel_models, optimize_op, train_set=None, eval_set=None, variables=None):
        self.session = session
        self.parallel_models = parallel_models
        self.nr_model = len(parallel_models)
        if variables is not None:
            self.variables = variables
        else:
            self.variables = tf.trainable_variables()
        self.optimize_op = optimize_op
        self.clock = time.time()
        self.train_set = train_set
        self.eval_set = eval_set

    def qclock(self):
        cur_time = time.time()
        tdiff = cur_time - self.clock
        self.clock = cur_time
        return tdiff


    def _data_preprocessing(self, data):
        if len(data.shape)==3:
            data = data[:, :, :, None]
        data = np.rint(data)
        return data

    def _make_feed_dict(self, data, is_training=True, dropout_p=0.5):
        dd = self._data_preprocessing(data)
        ds = np.split(dd, self.nr_model)
        feed_dict = {}
        feed_dict.update({m.is_training: is_training for m in self.parallel_models})
        feed_dict.update({m.dropout_p: dropout_p for m in self.parallel_models})
        feed_dict.update({m.inputs: ds[i] for i, m in enumerate(self.parallel_models)})
        return feed_dict

    def train_epoch(self):
        for data in self.train_set:
            feed_dict = self._make_feed_dict(data, is_training=True, dropout_p=0.5)
            self.session.run(self.optimize_op, feed_dict=feed_dict)

    def evaluate(self):
        ls = []
        for data in self.eval_set:
            feed_dict = self._make_feed_dict(data, is_training=False, dropout_p=0.0)
            l = self.session.run([m.loss for m in self.parallel_models], feed_dict=feed_dict)
            nats_per_dim = np.mean(l) / np.prod(data.shape[1:3])
            ls.append(nats_per_dim)
        return np.mean(ls)

    def sample_from_model(self):
        self.eval_set.reset()
        dd = self._data_preprocessing(next(self.eval_set))
        self.eval_set.reset()
        ds = np.split(dd, self.nr_model)
        feed_dict = {}
        feed_dict.update({m.is_training: False for m in self.parallel_models})
        feed_dict.update({m.dropout_p: 0. for m in self.parallel_models})
        feed_dict.update({m.inputs: ds[i] for i, m in enumerate(self.parallel_models)})

        x_gen = [np.zeros_like(ds[i]) for i in range(self.nr_model)]
        img_h, img_w = dd.shape[1], dd.shape[2]
        for yi in range(img_h):
            for xi in range(img_w):
                feed_dict.update({m.inputs:x_gen[i] for i, m in enumerate(self.parallel_models)})
                x_hat = self.session.run([m.x_hat for m in self.parallel_models], feed_dict=feed_dict)
                for i in range(self.nr_model):
                    x_gen[i][:, yi, xi, :] = x_hat[i][:, yi, xi, :]
        return np.concatenate(x_gen, axis=0)

    def run(self, num_epoch, eval_interval, save_interval):
        for epoch in range(1, num_epoch+1):
            self.qclock()
            self.train_epoch()
            train_time = self.qclock()
            # if epoch % eval_interval == 0:
            v = self.evaluate()
            if epoch % save_interval == 0:
                # saver.save(sess, args.save_dir + '/params_' + args.data_set + '.ckpt')
                samples = self.sample_from_model()
                visualize_samples(samples, name="results/samples-{0}.png".format(epoch), layout=(3,3))
            print("Epoch {0}: {1:0.3f}s ...................".format(epoch, train_time))
            print("    Eval Loss: ", v)

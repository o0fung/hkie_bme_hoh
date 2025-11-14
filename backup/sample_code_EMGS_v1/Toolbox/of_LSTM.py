"""
Long Short Term Memory (LSTM)
 - a variation of Recurrent Neural Network (RNN)
 
 RNN:
 To work on sequential data like text corpora,
 where we have sentences associated with each other;
 or time-series where data is entirely sequential and 
 dynamic.
 
 Address the memory issue by giving a feedback mechanism
 that looks back to the previous output and serves as
 a kind of memory.
 
 LSTM:
 Create both short-term and long-term memory components 
 to efficiently study and learn sequential data.
 
 As opposed to RNN, which only have short-term memory.
 
 Applicaitons:
 Machine Translation, Speech Recognition, Time-seris analysis, etc.

"""

import numpy
from Toolbox import of_Math


class LstmParam:
    def __init__(self, mem_cell_ct=5, x_dim=1):
        # setup LSTM parameters
        # recommended mem_cell_ct = 5
        # recommended x_dim = 1
        
        # Initializing the Bias (B) and Weight (W) matrices
        
        self.mem_cell_ct = mem_cell_ct
        self.x_dim = x_dim
        concat_len = x_dim + mem_cell_ct
        
        # weight matrices
        self.wg = of_Math.rand_arr(-0.1, 0.1, mem_cell_ct, concat_len)
        self.wi = of_Math.rand_arr(-0.1, 0.1, mem_cell_ct, concat_len)
        self.wf = of_Math.rand_arr(-0.1, 0.1, mem_cell_ct, concat_len)
        self.wo = of_Math.rand_arr(-0.1, 0.1, mem_cell_ct, concat_len)
        
        # bias terms
        self.bg = of_Math.rand_arr(-0.1, 0.1, mem_cell_ct)
        self.bi = of_Math.rand_arr(-0.1, 0.1, mem_cell_ct)
        self.bf = of_Math.rand_arr(-0.1, 0.1, mem_cell_ct)
        self.bo = of_Math.rand_arr(-0.1, 0.1, mem_cell_ct)
        
        # diffs (derivative of loss function w.r.t. all parameters)
        self.wg_diff = numpy.zeros((mem_cell_ct, concat_len))
        self.wi_diff = numpy.zeros((mem_cell_ct, concat_len))
        self.wf_diff = numpy.zeros((mem_cell_ct, concat_len))
        self.wo_diff = numpy.zeros((mem_cell_ct, concat_len))
        self.bg_diff = numpy.zeros(mem_cell_ct)
        self.bi_diff = numpy.zeros(mem_cell_ct)
        self.bf_diff = numpy.zeros(mem_cell_ct)
        self.bo_diff = numpy.zeros(mem_cell_ct)

    def apply_diff(self, lr=1):
        # lr: the learning rate
        self.wg -= lr * self.wg_diff
        self.wi -= lr * self.wi_diff
        self.wf -= lr * self.wf_diff
        self.wo -= lr * self.wo_diff
        self.bg -= lr * self.bg_diff
        self.bi -= lr * self.bi_diff
        self.bf -= lr * self.bf_diff
        self.bo -= lr * self.bo_diff
        # reset diffs to zero
        self.wg_diff = numpy.zeros_like(self.wg)
        self.wi_diff = numpy.zeros_like(self.wi)
        self.wf_diff = numpy.zeros_like(self.wf)
        self.wo_diff = numpy.zeros_like(self.wo)
        self.bg_diff = numpy.zeros_like(self.bg)
        self.bi_diff = numpy.zeros_like(self.bi)
        self.bf_diff = numpy.zeros_like(self.bf)
        self.bo_diff = numpy.zeros_like(self.bo)
    

class LstmState:
    def __init__(self, mem_cell_ct, x_dim):
        # setup LSTM state values
        self.g = numpy.zeros(mem_cell_ct)
        self.i = numpy.zeros(mem_cell_ct)
        self.f = numpy.zeros(mem_cell_ct)
        self.o = numpy.zeros(mem_cell_ct)
        self.s = numpy.zeros(mem_cell_ct)
        self.h = numpy.zeros(mem_cell_ct)
        self.bottom_diff_h = numpy.zeros_like(self.h)
        self.bottom_diff_s = numpy.zeros_like(self.s)
        
       
class LstmNode:
    def __init__(self, lstm_param, lstm_state):
        # setup LSTM node
        # store reference to parameters and to activations
        self.state = lstm_state
        self.param = lstm_param
        # non-recurrent input concatenated with recurrent input
        self.xc = None
        
    def bottom_data_is(self, x, s_prev=None, h_prev=None):
        # if this is the first lstm node in the network
        if s_prev is None:
            s_prev = numpy.zeros_like(self.state.s)
        if h_prev is None:
            h_prev = numpy.zeros_like(self.state.h)
        self.s_prev = s_prev
        self.h_prev = h_prev
        
        # concatenate x(t) and h(t-1)
        # stacking x(present input xt) and h(t-1)
        # Sigmoid Activation decides which values to take in
        # tanh transform new tokens to vectors
        # dot product of Wf (forget weight matrix and xc +bias) to calculate output state
        # finally multiplying forget_gate(self.state.f) with previous cell state (s_prev) to get present state.
        
        xc = numpy.hstack((x, h_prev))
        # vector representation of the input gate values
        self.state.g = numpy.tanh(numpy.dot(self.param.wg, xc) + self.param.bg)
        # input gate select relevant data from current inputs
        self.state.i = of_Math.sigmoid(numpy.dot(self.param.wi, xc) + self.param.bi)
        # forget gate select relevant data from previous inputs
        self.state.f = of_Math.sigmoid(numpy.dot(self.param.wf, xc) + self.param.bf)
        # output gate select relevant data from the filtered inputs
        self.state.o = of_Math.sigmoid(numpy.dot(self.param.wo, xc) + self.param.bo)
        
        # get filtered inputs, from selected weighted input and selected forgotted input
        self.state.s = self.state.g * self.state.i + s_prev * self.state.f
        # get hidden inputs, from selected filtered input
        self.state.h = self.state.s * self.state.o
        # current data
        self.xc = xc
        
    def top_diff_is(self, top_diff_h, top_diff_s):
        # notice that top_diff_s is carried along the constant error carousel
        ds = self.state.o * top_diff_h + top_diff_s
        do = self.state.s * top_diff_h
        di = self.state.g * ds
        dg = self.state.i * ds
        df = self.s_prev * ds
        
        # diffs w.r.t. vector inside sigma / tanh function
        di_input = of_Math.sigmoid_derivative(self.state.i) * di
        df_input = of_Math.sigmoid_derivative(self.state.f) * df
        do_input = of_Math.sigmoid_derivative(self.state.o) * do
        dg_input = of_Math.tanh_derivative(self.state.g) * dg
        
        # diffs w.r.t. inputs
        self.param.wi_diff += numpy.outer(di_input, self.xc)
        self.param.wf_diff += numpy.outer(df_input, self.xc)
        self.param.wo_diff += numpy.outer(do_input, self.xc)
        self.param.wg_diff += numpy.outer(dg_input, self.xc)
        self.param.bi_diff += di_input
        self.param.bf_diff += df_input       
        self.param.bo_diff += do_input
        self.param.bg_diff += dg_input       

        # compute bottom diff
        dxc = numpy.zeros_like(self.xc)
        dxc += numpy.dot(self.param.wi.T, di_input)
        dxc += numpy.dot(self.param.wf.T, df_input)
        dxc += numpy.dot(self.param.wo.T, do_input)
        dxc += numpy.dot(self.param.wg.T, dg_input)

        # save bottom diffs
        self.state.bottom_diff_s = ds * self.state.f
        self.state.bottom_diff_h = dxc[self.param.x_dim:]
 
 
class LstmNetwork():
    def __init__(self, lstm_param):
        # setup the LSTM network
        self.lstm_param = lstm_param
        self.lstm_node_list = []
        # input sequence
        self.x_list = []

    def y_list_is(self, y_list, loss_layer):
        """
        Updates diffs by setting target sequence with corresponding loss layer. 
        Will *NOT* update parameters.  To update parameters, call apply_diff()
        """
        assert len(y_list) == len(self.x_list)
        idx = len(self.x_list) - 1
        # first node only gets diffs from label ...
        loss = loss_layer.loss(self.lstm_node_list[idx].state.h, y_list[idx])
        diff_h = loss_layer.bottom_diff(self.lstm_node_list[idx].state.h, y_list[idx])
        # here s is not affecting loss due to h(t+1), hence we set equal to zero
        diff_s = numpy.zeros(self.lstm_param.mem_cell_ct)
        self.lstm_node_list[idx].top_diff_is(diff_h, diff_s)
        idx -= 1

        ### ... following nodes also get diffs from next nodes, hence we add diffs to diff_h
        ### we also propagate error along constant error carousel using diff_s
        while idx >= 0:
            loss += loss_layer.loss(self.lstm_node_list[idx].state.h, y_list[idx])
            diff_h = loss_layer.bottom_diff(self.lstm_node_list[idx].state.h, y_list[idx])
            diff_h += self.lstm_node_list[idx + 1].state.bottom_diff_h
            diff_s = self.lstm_node_list[idx + 1].state.bottom_diff_s
            self.lstm_node_list[idx].top_diff_is(diff_h, diff_s)
            idx -= 1 

        return loss

    def x_list_clear(self):
        self.x_list = []

    def x_list_add(self, x):
        self.x_list.append(x)
        if len(self.x_list) > len(self.lstm_node_list):
            # need to add new lstm node, create new state mem
            lstm_state = LstmState(self.lstm_param.mem_cell_ct, self.lstm_param.x_dim)
            self.lstm_node_list.append(LstmNode(self.lstm_param, lstm_state))

        # get index of most recent x input
        idx = len(self.x_list) - 1
        if idx == 0:
            # no recurrent inputs yet
            self.lstm_node_list[idx].bottom_data_is(x)
        else:
            s_prev = self.lstm_node_list[idx - 1].state.s
            h_prev = self.lstm_node_list[idx - 1].state.h
            self.lstm_node_list[idx].bottom_data_is(x, s_prev, h_prev)
            

class LossLayer:
    def __init__(self, mem_cell_ct=5):
        self.state_h = numpy.zeros(mem_cell_ct)
        self.out_y = None
    
    def loss(self, h, y):
        return numpy.mean(numpy.power(y-h, 2))
    
    def bottom_diff(self, h, y):
        return 2*(h-y)


def model(input_x, output_y, n=1000, mem=5, x_dim=1):
    # Train the LSTM model
    # default MEM_CELL_CT and X_DIM are 5 and 1 respectively.
    lstm = LstmNetwork(LstmParam(mem_cell_ct=mem, x_dim=x_dim))
    ll = LossLayer(mem_cell_ct=mem)

    for i in range(n):
        lstm.x_list_clear()
        for x in input_x:
            lstm.x_list_add(x)

        loss = lstm.y_list_is(output_y, loss_layer=ll)
        print(i, loss)
        lstm.lstm_param.apply_diff()

    return lstm

def test(lstm, val):
    # test and apply the LSTM model using value
    lstm.x_list_add(val)
    return lstm.lstm_node_list[-1].state.h

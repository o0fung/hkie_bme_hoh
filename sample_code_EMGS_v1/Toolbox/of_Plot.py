import csv
import numpy
import tkinter
from matplotlib import pyplot
from matplotlib.backend_bases import MouseButton

            
class FigCanvas(tkinter.Frame):
    def __init__(self, parent, width=200, height=100, tick=10, nrow=1, ncol=1, callback=None):
        """
        Draw figures in tkinter canvas
        
        Args:
            parent (tkinter widget): link to the parent widget of the canvas frame
            width (int, optional): width of the canvas. Defaults to 200.
            height (int, optional): height of the canvas . Defaults to 100.
            tick (int, optional): tick size of figure in the canvas. Defaults to 10.
            nrow (int, optional): number of rows of figure in the canvas. Defaults to 1.
            ncol (int, optional): number of columns of figure in the canvas. Defaults to 1.
            callback (function, optional): function to call when click on canvas. Defaults to None.
        """
        tkinter.Frame.__init__(self, parent)
        self.parent = parent
        self.callback = callback
        self.width = width
        self.height = height
        # setup the dimension for each figure of the canvas
        self.w = int((width - tick*(ncol-1)) / ncol)
        self.h = int((height - tick*(nrow-1)) / nrow)
        self.t = tick
        self.nrow = nrow
        self.ncol = ncol
        # setup the canvas environment
        self.canvas = tkinter.Canvas(self, width=width, height=height)
        self.canvas.grid(row=0, column=0, sticky='news')
        self.canvas.bind('<Button-1>', self.callback)
        # setup the axes in the canvas
        self.axes = [[FigAxes(self.canvas, x0=int(self.w+tick)*i, y0=int(self.h+tick)*j, idx=f'{i}{j}'
                              ) for i in range(ncol)] for j in range(nrow)]
        
    def set_callback(self, callback=None):
        # setup the callback function when user click on the figure canvas
        self.callback = callback
        self.canvas.bind('<Button-1>', self.callback)
        
    def onclick(self, event):
        # ====================
        # Example:
        # when user click on the figure
        # get axes and pointer coordinates
        global param
        
        iax, ix, iy = event.inaxes, event.xdata, event.ydata
        if event.button == MouseButton.LEFT:
            clicked = 0
        elif event.button == MouseButton.RIGHT:
            clicked = 1
        else:
            return
        
        if ix is None or iy is None:
            # reset coordinate buffer if user click elsewhere
            print('clear')
            
        else:
            try:
                param
            except NameError:
                param = [0, 0]
            finally:
                param[clicked] = float(ix)
                print(param[1]-param[0])
        

class FigAxes:
    def __init__(self, canvas, x0, y0, idx):
        """
        Draw axis in the subplot of figure canvas

        Args:
            canvas (tkinter widget): link to the canvas for drawing axes
            x0 (int): origin x-coordinate of the subplot
            y0 (int): origin y-coordinate of the subplot
        """
        # get the FigCanvas class object
        self.fig = canvas.master
        self.axis = canvas
        self.tags = {'axis': f'axis_{idx}', 'data': f'data_{idx}'}
        # get the origin of subplot at top-right corner
        self.x0 = x0
        self.y0 = y0
        # setup the axes for individual figures in the canvas
        self.offset_w = None
        self.offset_h = None
        self.x_lo = None
        self.x_hi = None
        self.y_lo = None
        self.y_hi = None
        self.xu = None
        self.yu = None
        self.clear()
        
    def add_axis(self, x=None, y=None, xlim=None, ylim=None, offset_w=None, offset_h=None):
        """
        Prepare the axis for the specified data template
        Compute the range of data, axis offset required, and axis units

        either provide data x, y for auto compute the data range
        or mannually provide the xlim, ylim, offset_w, offset_h
        """
        if x is not None and y is not None:
            # auto compute the range of input data
            self.x_lo = min(numpy.min(x), self.x_lo)
            self.x_hi = max(numpy.max(x), self.x_hi)
            self.y_lo = min(numpy.min(y), self.y_lo)
            self.y_hi = max(numpy.max(y), self.y_hi)
        else:
            # manually provide the range of data 
            self.x_lo = xlim[0] if xlim else self.x_lo
            self.x_hi = xlim[1] if xlim else self.x_hi
            self.y_lo = ylim[0] if ylim else self.y_lo
            self.y_hi = ylim[1] if ylim else self.y_hi
        
        # manually provide the baseline axis offset
        self.offset_w = offset_w if offset_w else self.offset_w
        self.offset_h = offset_h if offset_h else self.offset_h
        
        # auto adjust the axis offset using range of data
        if self.x_lo < 0 and self.x_hi > 0:
            # compute proportion of -ve and +ve data about the origin
            temp_offset_w = - self.x_lo / (self.x_hi - self.x_lo)
            if temp_offset_w > self.offset_w:
                self.offset_w = temp_offset_w
        if self.y_lo < 0 and self.y_hi > 0:
            # compute proportion of -ve and +ve data about the origin
            temp_offset_h = 1 - self.y_lo / (self.y_hi - self.y_lo)
            if temp_offset_h < self.offset_h:
                self.offset_h = temp_offset_h
                    
        # compute the unit of axes from range of data
        self.xu = self.fig.w / (self.x_hi - self.x_lo)
        self.yu = self.fig.h / (self.y_hi - self.y_lo)
        
    def draw_axis(self, steps=5):
        """
        draw the axis based on range of data and axis specification

        Args:
            steps (int): minimum number of ticks on the axis
        """
        # get axis tick labels
        xtick_label = self.get_tick_label(self.x_lo, self.x_hi, 10)
        ytick_label = self.get_tick_label(self.y_lo, self.y_hi, steps)
        # axis shift
        xaxis = self.x0 + self.fig.w * self.offset_w
        yaxis = self.y0 + self.fig.h * self.offset_h
        # origin
        self.axis.create_text(xaxis - self.fig.t, yaxis,
                              anchor='n', text='0', tags=self.tags['axis'])
        # x-axis
        self.axis.create_line(xaxis, yaxis, self.x0 + self.fig.w, yaxis,
                              arrow=tkinter.LAST, tags=self.tags['axis'])
        for i in xtick_label:
            if i == 0:
                continue
            # xticks and xlabels
            self.axis.create_line(xaxis + (i - self.x_lo) * self.xu, yaxis + self.fig.t,
                                  xaxis + (i - self.x_lo) * self.xu, yaxis, tags=self.tags['axis'])
            self.axis.create_text(xaxis + (i - self.x_lo) * self.xu, yaxis + self.fig.t,
                                  anchor='n', text=i, tags=self.tags['axis'])
        # y-axis
        self.axis.create_line(xaxis, self.y0 + self.fig.h, xaxis, self.y0,
                              arrow=tkinter.LAST, tags=self.tags['axis'])
        for i in ytick_label:
            if i == 0:
                continue
            # yticks and ylabels
            self.axis.create_line(xaxis - self.fig.t, yaxis - i * self.yu,
                                  xaxis, yaxis - i * self.yu, tags=self.tags['axis'])
            self.axis.create_text(xaxis - self.fig.t, yaxis - i * self.yu,
                                  anchor='e', text=i, tags=self.tags['axis'])
    
    def get_tick_label(self, lo, hi, steps):
        """
        compute array of ticks label from range of data
        """
        tick_max, tick_min = 1, 1
        if lo < 0 and hi > 0:
            # for positive direction, optimize number of minor ticks
            for n in [1, 2, 3, 4, 5, 10, 25, 50, 100, 500, 1000]:
                if hi / steps > n:
                    tick_max = n
            # for negative direction, optimize number of minor ticks
            for n in [1, 2, 3, 4, 5, 10, 25, 50, 100, 500, 1000]:
                if lo / steps < -n:
                    tick_min = n
            # merge the two directions to optimize number of minor ticks
            axis_pos = numpy.arange(0, hi, max(tick_max, tick_min))
            axis_neg = numpy.arange(0, -lo, max(tick_max, tick_min))
            return numpy.concatenate((-axis_neg[-1: 0: -1], axis_pos))
        else:
            # simply formulate the tick label using range of data
            for n in [1, 2, 3, 4, 5, 10, 20, 25, 50, 100, 200, 500, 1000]:
                if (hi - lo) / steps > n:
                    tick_max = n
            return numpy.arange(int(lo), int(hi), tick_max)

    def draw_labels(self, xlab=None, ylab=None, xlab_shift=4, ylab_shift=4):
        """
        add axis label with specified separation from the axis line
        """
        # axis shift
        xaxis = self.x0 + self.fig.w * self.offset_w
        yaxis = self.y0 + self.fig.h * self.offset_h
        # 
        if xlab:
            self.axis.create_text(xaxis + int(self.fig.w/2), yaxis + self.fig.t * xlab_shift,
                                  anchor='n', text=xlab, tags=self.tags['axis'])
        if ylab:
            self.axis.create_text(xaxis - self.fig.t * ylab_shift, self.y0 + int(self.fig.h/2),
                                  anchor='s', text=ylab, angle=90, tags=self.tags['axis'])
            
    def draw_text(self, x, y, text=None, anchor=None):
        """
        add text label at the provided x and y coordinate point
        """
        # axis shift
        xaxis = self.x0 + self.fig.w * self.offset_w
        yaxis = self.y0 + self.fig.h * self.offset_h
        # add text to the canvas at coordinate x y corresponding to the data axis
        if text:
            self.axis.create_text(xaxis + (x - self.x_lo)*self.xu, yaxis - y*self.yu,
                                  text=text, anchor=anchor, tags=self.tags['axis'])
            
    def plot(self, x, y, fill='black', lw=1, threshold=None, fill2=None):
        """
        plot line figure using provided x and y data sequence
        """
        # axis shift
        xaxis = self.x0 + self.fig.w * self.offset_w
        yaxis = self.y0 + self.fig.h * self.offset_h
        # plot data line point-by-point
        for i in range(1, len(x)):
            line_color = fill2 if threshold is not None and fill2 is not None and y[i] > threshold else fill
                
            self.axis.create_line(xaxis + (x[i - 1] - self.x_lo) * self.xu,
                                  yaxis - y[i - 1] * self.yu,
                                  xaxis + (x[i] - self.x_lo) * self.xu,
                                  yaxis - y[i] * self.yu,
                                  tags=self.tags['data'], fill=line_color, width=lw)
            
    def clear(self):
        """
        reset the figure and axis
        """
        # reset the figure axis
        self.axis.delete(self.tags['data'])
        self.axis.delete(self.tags['axis'])
        self.axis.delete('reference')
        # reset the axis specifications
        self.offset_w = 0.1
        self.offset_h = 0.9
        self.x_lo = numpy.inf
        self.x_hi = -numpy.inf
        self.y_lo = numpy.inf
        self.y_hi = -numpy.inf
        self.xu = 1
        self.yu = 1



if __name__ == '__main__':
    data_x = [0, 1, 2]
    data_y = [3, 4, 5]
    
    gui = tkinter.Tk()

    frame = FigCanvas(gui, width=1000, height=800)
    frame.pack()

    fig = FigAxes(frame.canvas, 0, 2, 'test')
    fig.add_axis(data_x, data_y)
    fig.draw_axis()
    fig.draw_labels()
    fig.plot(data_x, data_y)

    gui.mainloop()

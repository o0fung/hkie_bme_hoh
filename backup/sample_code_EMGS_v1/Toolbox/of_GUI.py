import calendar
import datetime
import time
import sys
import cv2
import Tools
import os

import tkinter as tk
import tkinter.font
from PIL import Image, ImageTk


SCREEN_DIMENSION = (1024, 600)      # customized just for the touchscreen model we chosen
SAMPLING_PERIOD = 200               # customized to update chart at 5Hz frame rate, i.e. every 200 ms

DEFAULT_PATH_TO_USER = os.path.join('/Users/0f')
DEFAULT_PATH_TO_USER = os.path.join('/home/vrmt')


def attach_image(widget, path, size=None):
    # attach resized image to button or label
    temp = Image.open(path)
    if size:
        temp = temp.resize(size, Image.LANCZOS)
    temp = ImageTk.PhotoImage(temp)
    widget.config(image=temp)
    widget.image = temp
    return widget


class GuiHelper:
    # create the application
    
    def __init__(self):
        self.gui = None
        self.widgets = {}
        self.variables = {}
        self.timer = {}
        
    def setup_env(self, is_fullscreen=False):
        # setup the tkinter ui and scale it fullscreen
        self.gui = tk.Tk()
        if sys.platform.startswith('win') or sys.platform.startswith('darwin'):
            self.gui.geometry('1024x600')
            self.screen_width = 1024        # 1024 ?
            self.screen_height = 600      # 600 ?
        else:
            self.gui.attributes('-fullscreen', is_fullscreen)
            self.screen_width = self.gui.winfo_screenwidth()        # 1024 ?
            self.screen_height = self.gui.winfo_screenheight()      # 600 ?
        self.gui.update()
        
        # scale the font size and icon size according to ratio of screen size
        
        fontsize = int(self.screen_height/120)
        self.FONT_TITLE = tkinter.font.Font(family='Arial', size=fontsize*8, weight='bold') 
        self.FONT_LARGE = tkinter.font.Font(family='Arial', size=fontsize*5) 
        self.FONT_SPECIAL = tkinter.font.Font(family='Arial', size=fontsize*3, weight='bold') 
        self.FONT_NORMAL = tkinter.font.Font(family='Arial', size=fontsize*2) 
        self.ICON_SMALL = (30, 30)
        self.ICON_NORMAL = (48, 48)
        self.ICON_LARGE = (100, 100)
        
    def setup_layout(self):
        # setup the ui layout
        self.layout()
        
    def run(self):
        if self.gui:
            # run the loop at specific rate
            self._looping(period=SAMPLING_PERIOD)
            
        # run the tkinter ui
        self.gui.mainloop()
            
    def layout(self):
        # design the structure and appearance of the app ui
        pass
            
    def loop(self):
        # decide what to do in every loop
        pass
            
    def _looping(self, period):
        if self.gui:
            # run the loop recursively at specific rate
            self.gui.after(period, lambda: self._looping(period))
            self.loop()
            
    def kill(self):
        # decide what to do before closing the application
        pass
            
    def _killing(self):
        # sequence before closing the application
        self.kill()
        if self.gui:
            self.gui.destroy()
        exit()


class PageHelper(tk.Frame):
    # create a frame that held a bunch of pages
    
    def __init__(self, master):
        # the pages is based on a bunch of frame stacked on top of each other
        # active visible frame will be raised to the top
        
        tk.Frame.__init__(self, master)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.clear_pages()
        
    def clear_pages(self):
        self.pages = {}             # store a dictionary of pages in form of frame
        self.current_page = None    # keep track of the frame that is on the top visible
        self.prev_page = None       # keep track of the frame that is previous on top
        
    def add_page(self, name):
        # create a frame to store page content
        self.pages[name] = tk.Frame(self)
        self.pages[name].grid(row=0, column=0, sticky='news')
        
    def get_page(self, name, callback=None):
        # raise a specific page to the top
        # run some function if specified
        self.pages[name].tkraise()
        if not self.current_page == name:
            self.prev_page = self.current_page
        self.current_page = name
        if callback:
            callback()
            
    def set_grid_configure(self, name, row, column, uniform=None):
        # a quick shortcut to configure the grid scaling format
        for i in range(row):
            self.pages[name].grid_rowconfigure(i, weight=1, uniform=uniform)
        for i in range(column):
            self.pages[name].grid_columnconfigure(i, weight=1, uniform=uniform)
        

class ListboxHelper(tk.LabelFrame):
    # create a listbox with multiple columns
    PATH_TO_USER = DEFAULT_PATH_TO_USER
    PATH_TO_DATA = os.path.join(PATH_TO_USER, 'Capd_Data')       # location of database
    PATH_TO_APP = os.path.join(PATH_TO_USER, 'VRMT_CAPD', 'of_CAPD',)
    
    def __init__(self, master, text, callback=None):
        # the listbox is based on a listbox widget, set the title of listbox
        tk.LabelFrame.__init__(self, master, text=text)
        
        self.columns = {}               # store a list of column as Frame objects
        self.ncol = 0                   # store the total number of column in the listbox
        self.nrow = 0                   # store the total number of row in the current listbox
        self.row = -1                   # store the index of the current selected column
        self.callback = callback        # user defined function called when user selected an item
        self.sorted = False             # flag of whether the user has selected column sorting
        
        self.data = []                  # Store the list of data in a column
                                        # data in the format of [ [a1, a2, ] , [b1, b2, ] , ]
        
    def add_callback(self, callback=None):
        # register callback function called when user selected an item
        self.callback = callback
        
    def add_column(self, text, width, fontsize=19, justify=tk.CENTER):
        frame = tk.Frame(self, borderwidth=1, relief=tk.SUNKEN)
        frame.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        
        font = f'Arial {fontsize} bold'
        
        # header row of the listbox is a button to toggle sorting column
        tk.Button(frame, text=text, font=font, command=lambda x=self.ncol: self.sort_column(x, True)).pack(fill=tk.X)
        
        # listbox to store data in the column
        # touch the listbox can select a row
        widget = tk.Listbox(frame, width=width, relief=tk.SUNKEN, exportselection=False, justify='left')
        widget.config(font=font, justify=justify)
        widget.bind('<Button-1>', lambda e: self.select_row(e.y))
        widget.bind('<Leave>', lambda e: 'break')
        widget.pack(expand=True, fill=tk.BOTH)
        
        # associate the listbox to the frame
        self.columns[text] = widget
        self.ncol += 1
        
    def add_scrollbar(self):
        # define a column with two buttons to move up or down the listbox.
        frame = tk.Frame(self)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        frame.pack(side=tk.LEFT, fill=tk.Y)
        
        # UP button:
        widget = tk.Button(frame, compound=tk.TOP, command=self.step_up, background='white')
        widget = attach_image(widget, f'{self.PATH_TO_APP}/pic/UP.png', size=(48, 48))
        widget.grid(row=0, column=0, sticky='news')
        # DOWN button:
        widget = tk.Button(frame, compound=tk.TOP, command=self.step_down, background='white')
        widget = attach_image(widget, f'{self.PATH_TO_APP}/pic/DOWN.png', size=(48, 48))
        widget.grid(row=1, column=0, sticky='news')

    def set_data(self, data=None):
        # reset the listbox selection.
        self.clear_column()
        # check if data a valid array with size the same number of column as the listbox.
        if data and len(data) == self.ncol:
            # register the data.
            self.data = data
            self.nrow = len(self.data[0])
            # reset and update the corresponding column content.
            for i, text in enumerate(self.columns):
                # reset the column.
                self.columns[text].delete(0, tk.END)
                # insert the specific row content to the specific columns.
                for j, row in enumerate(self.data[i]):
                    self.columns[text].insert(j, row)
                    
            self.select_row()

    def get_data(self, col, row=None):
        # validate the data stored.
        if self.data and len(self.data) == self.ncol:
            if row is not None and row >= 0:
                # get the data on the specified row and column.
                return self.data[col][row]
            else:
                return self.data[col][self.row]
            
    def clear_column(self):
        # clear all items in the Listbox columns.
        self.nrow = 0
        self.select_clear()
        for text in self.columns:
            self.columns[text].delete(0, tk.END)

    def sort_column(self, n, reverse=False):
        # no sorting functionality in this app
        return
    
        # User specify the column index to be sorted.
        # Toggle the reverse flag.
        if reverse:
            self.sorted = not self.sorted
        # If not specified, make the default sorting.
        else:
            self.sorted = False

        sorted_data = [[] for _ in range(self.ncol)]  # List to store sorted data temporarily.
        # Get the current list of data stored in the specified column.
        temp = list(enumerate(self.columns['#'].get(0, tk.END)))
        # Sort the current list of enumerated column data according to the alphabet order.
        temp.sort(key=lambda x: x[1], reverse=self.sorted)
        # Find the updated order of data list relative to the old sequence.
        for i, _ in temp:
            for j in range(self.ncol):
                sorted_data[j].append(self.data[j][i])
        
        self.row = -1
        
        # Update the listbox content according to the sorted data.
        self.set_data(sorted_data)

    def select_row(self, y=None):
        # user selected a row, by clicking on the row.
        # get the nearest row that the user selected.
        if y is not None:
            self.row = self.columns[list(self.columns.keys())[0]].nearest(y)
        else:
            # by default select the last row
            self.row = len(self.data[0]) - 1
            
        # highlight the selected row.
        self.highlight_row()
        # run the callback function if provided.
        if self.callback:
            self.callback()

    def select_clear(self):
        # Reset the selected row index.
        self.row = -1
        # Clear the selection made in the listbox.
        for text in self.columns:
            self.columns[text].selection_clear(0, tk.END)

    def step_down(self, e=None):
        # User selected to step down a row.
        # Check if the row index can be decreased by one, and is valid.
        if 0 <= self.row < len(self.data[0]) - 1:
            # Step down the row (selection up) and highlight the selected row.
            self.row += 1
            self.highlight_row()
        # Run the callback function if provided.
        if self.callback:
            self.callback()
        return 'break'

    def step_up(self, e=None):
        # User selected to step up a row.
        # Check if the row index can be increased by one, and is valid.
        if 0 < self.row <= len(self.data[0]) - 1:
            # Step up the row (selection down) and highlight the selected row.
            self.row -= 1
            self.highlight_row()
        # Run the callback function if provided.
        if self.callback:
            self.callback()
        return 'break'

    def highlight_row(self):
        # Check if the row index is within valid range.
        if self.row >= 0 and self.row <= len(self.data[0]) - 1:
            # Highlight selected row for each column.
            for text in self.columns:
                # Clear existing highlighted selected row.
                self.columns[text].selection_clear(0, tk.END)
                # Set currently selected row.
                self.columns[text].selection_set(self.row)
                # Make sure the selected row can be seen by the user.
                self.columns[text].see(self.row)


class CalendarHelper(tk.Frame):
    # create a Calendar that can be selected
    # the current date is exposed today, or transferred to date
    
    def __init__(self, master=None, date=None, dateformat="%Y-%m-%d", command=lambda i:None):
        tk.Frame.__init__(self, master)
        
        calendar.setfirstweekday(6)  # set sunday as the first day of the week
        
        # get specified date or using today instead
        self.dt = datetime.datetime.strptime(date, dateformat) if date else datetime.datetime.now()
        
        self.frame = tk.Frame(self)
        self.frame.grid(row=0, column=0, sticky='news')
        
        self.showmonth()  # construct the calendar
        self.command = command
        self.dateformat = dateformat
        
    def update_date(self, date):
        self.dt = datetime.datetime.strptime(date, self.dateformat) if date else datetime.datetime.now()
        self.showmonth()
        
    def showmonth(self):
        # get the calendar for a month as string
        sc = calendar.month(self.dt.year, self.dt.month).split('\n')
        
        # refresh and reconstruct the calendar
        self.frame.grid_forget()
        self.frame.destroy()
        
        self.frame = tk.Frame(self)
        self.frame.grid(row=0, column=0, sticky='news')
        
        # the buttons to the previous and to the next year and month
        for t, c in [('<<', 0), ('<', 1), ('>', 5), ('>>', 6)]: 
            tk.Button(self.frame, text=t, relief='flat', font='Arial 12', command=lambda i=t: self.callback(i)).grid(row=0, column=c)
            
        # the label to show the current selected year and month
        tk.Label(self.frame, text=sc[0], font='Arial 12').grid(row=0, column=2, columnspan=3)
        
        # reconstruct the calendar using customized format
        # typical caldendar:
        
        #    December 2023
        # Mo Tu We Th Fr Sa Su
        #              1  2  3
        #  4  5  6  7  8  9 10
        # 11 12 13 14 15 16 17
        # 18 19 20 21 22 23 24
        # 25 26 27 28 29 30 31
        
        for line, lineT in [(i, sc[i+1]) for i in range(1, len(sc)-1)]:
            # every date cell is repeated every 3 characters
            for col, colT in [(i, lineT[i*3:(i+1)*3-1]) for i in range(7)]:
                # only numeric date can be pressed as button and attached a callback function
                obj = tk.Button if colT.strip().isdigit() else tk.Label
                args = {'command': lambda i=colT: self.callback(i)} if obj == tk.Button else {}
                
                # selected date highlighted as green
                # Saturday and Sunday colored as red
                bg = 'green' if colT.strip() == str(self.dt.day) else 'gray' 
                fg = 'red' if col >= 6 or col < 1 else 'white' 
                
                # draw the button or label accordingly
                obj(self.frame, text="%s" % colT, relief='flat', font='Arial 12', bg=bg, fg=fg, **args).grid(row=line, column=col, ipadx=2, sticky='nwse')
    
    def callback(self, but):
        if but.strip().isdigit():
            # if you clicked on a date - the date changes
            self.dt=self.dt.replace(day=int(but)) 
            
        elif but in ['<','>','<<','>>']:
            # if you clicked on the arrows, the month and year change
            day=self.dt.day
            if but in['<','>']:  # month
                self.dt = self.dt + datetime.timedelta(days = 30 if but =='>' else -30) # Move a month in advance / rewind
            if but in['<<','>>']:  # year
                self.dt = self.dt + datetime.timedelta(days = 365 if but =='>>' else -365) #  Year forward / backward
            
            try: 
                # We are trying to put the date on which stood
                self.dt = self.dt.replace(day=day) 
            except: 
                pass # It is not always possible (esp. for date 29, 30, 31)
            
        self.showmonth() # Then always show calendar again
        
        if but.strip().isdigit(): 
            # If it was a date, then call the command
            self.command(self.dt.strftime(self.dateformat)) 


class ChartHelper(tk.LabelFrame):
    # create a chart that update the curve when called and fed with data
    
    def __init__(self, master, text, font):
        tk.LabelFrame.__init__(self, master, text=text, font=font, labelanchor='n')
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.font = font
        
    def draw_canvas(self, width, height):
        # draw the background of the chart that does not need update
        
        # prepare the scale and size of components
        self.w, w = int(width), int(width)
        self.h, h = int(height), int(height)
        self.t = int(h / 25)
        t = self.t
        
        # Canvas
        self.canvas = tk.Canvas(self, width=w, height=h)
        self.canvas.grid(row=0, column=0, sticky='news')
        # X-axis
        self.canvas.create_line(w * 1.0 / 11.0, h * 10.0 / 11.0, w, h * 10.0 / 11.0, arrow=tk.LAST)
        # X-ticks
        self.canvas.create_line(w * 2.0 / 11.0, h * 10.0 / 11.0, w * 2.0 / 11.0, h * 10.0 / 11.0 + t)
        self.canvas.create_line(w * 3.0 / 11.0, h * 10.0 / 11.0, w * 3.0 / 11.0, h * 10.0 / 11.0 + t)
        self.canvas.create_line(w * 4.0 / 11.0, h * 10.0 / 11.0, w * 4.0 / 11.0, h * 10.0 / 11.0 + t)
        self.canvas.create_line(w * 5.0 / 11.0, h * 10.0 / 11.0, w * 5.0 / 11.0, h * 10.0 / 11.0 + t)
        self.canvas.create_line(w * 6.0 / 11.0, h * 10.0 / 11.0, w * 6.0 / 11.0, h * 10.0 / 11.0 + t)
        self.canvas.create_line(w * 7.0 / 11.0, h * 10.0 / 11.0, w * 7.0 / 11.0, h * 10.0 / 11.0 + t)
        self.canvas.create_line(w * 8.0 / 11.0, h * 10.0 / 11.0, w * 8.0 / 11.0, h * 10.0 / 11.0 + t)
        self.canvas.create_line(w * 9.0 / 11.0, h * 10.0 / 11.0, w * 9.0 / 11.0, h * 10.0 / 11.0 + t)
        self.canvas.create_line(w * 10.0 / 11.0, h * 10.0 / 11.0, w * 10.0 / 11.0, h * 10.0 / 11.0 + t)
        # X-labels
        self.canvas.create_text(w * 2.0 / 11.0, h * 10.0 / 11.0, anchor='n', text='', font=self.font)
        self.canvas.create_text(w * 3.0 / 11.0, h * 10.0 / 11.0, anchor='n', text='5', font=self.font)
        self.canvas.create_text(w * 4.0 / 11.0, h * 10.0 / 11.0, anchor='n', text='', font=self.font)
        self.canvas.create_text(w * 5.0 / 11.0, h * 10.0 / 11.0, anchor='n', text='10', font=self.font)
        self.canvas.create_text(w * 6.0 / 11.0, h * 10.0 / 11.0, anchor='n', text='', font=self.font)
        self.canvas.create_text(w * 7.0 / 11.0, h * 10.0 / 11.0, anchor='n', text='15', font=self.font)
        self.canvas.create_text(w * 8.0 / 11.0, h * 10.0 / 11.0, anchor='n', text='', font=self.font)
        self.canvas.create_text(w * 9.0 / 11.0, h * 10.0 / 11.0, anchor='n', text='20', font=self.font)
        self.canvas.create_text(w * 10.0 / 11.0, h * 10.0 / 11.0, anchor='n', text='', font=self.font)
        self.canvas.create_text(w * 11.0 / 11.0 - 3 * t, h * 10.0 / 11.0, anchor='n', text='min', font=self.font)
        # Y-axis
        self.canvas.create_line(w * 1.0 / 11.0, h, w * 1.0 / 11.0, 0, arrow=tk.LAST)
        # Y-ticks
        # self.canvas.create_line(w * 1.0 / 11.0, h * 10.0 / 11.0, w * 1.0 / 11.0 - t, h * 10.0 / 11.0)
        # self.canvas.create_line(w * 1.0 / 11.0, h * 9.0 / 11.0, w * 1.0 / 11.0 - t, h * 9.0 / 11.0)
        # self.canvas.create_line(w * 1.0 / 11.0, h * 8.0 / 11.0, w * 1.0 / 11.0 - t, h * 8.0 / 11.0)
        # self.canvas.create_line(w * 1.0 / 11.0, h * 7.0 / 11.0, w * 1.0 / 11.0 - t, h * 7.0 / 11.0)
        # self.canvas.create_line(w * 1.0 / 11.0, h * 6.0 / 11.0, w * 1.0 / 11.0 - t, h * 6.0 / 11.0)
        # self.canvas.create_line(w * 1.0 / 11.0, h * 5.0 / 11.0, w * 1.0 / 11.0 - t, h * 5.0 / 11.0)
        # self.canvas.create_line(w * 1.0 / 11.0, h * 4.0 / 11.0, w * 1.0 / 11.0 - t, h * 4.0 / 11.0)
        # self.canvas.create_line(w * 1.0 / 11.0, h * 3.0 / 11.0, w * 1.0 / 11.0 - t, h * 3.0 / 11.0)
        # self.canvas.create_line(w * 1.0 / 11.0, h * 2.0 / 11.0, w * 1.0 / 11.0 - t, h * 2.0 / 11.0)
        # self.canvas.create_line(w * 1.0 / 11.0, h * 1.0 / 11.0, w * 1.0 / 11.0 - t, h * 1.0 / 11.0)
        # Y-major-grids
        self.canvas.create_line(w * 1.0 / 11.0, h * 2.0 / 11.0, w, h * 2.0 / 11.0, dash=(4, 4))
        self.canvas.create_line(w * 1.0 / 11.0, h * 4.0 / 11.0, w, h * 4.0 / 11.0, dash=(4, 4))
        self.canvas.create_line(w * 1.0 / 11.0, h * 6.0 / 11.0, w, h * 6.0 / 11.0, dash=(4, 4))
        self.canvas.create_line(w * 1.0 / 11.0, h * 8.0 / 11.0, w, h * 8.0 / 11.0, dash=(4, 4))
        self.canvas.create_line(w * 1.0 / 11.0, h * 10.0 / 11.0, w, h * 10.0 / 11.0, dash=(4, 4))
        # Y-labels
        self.canvas.create_text(w * 1.0 / 11.0 - t, h * 10.0 / 11.0 + t, anchor='n', text='0', font=self.font)
        self.canvas.create_text(w * 1.0 / 11.0 - t, h * 8.0 / 11.0, anchor='e', text='0.5', font=self.font, tags='ytick')
        self.canvas.create_text(w * 1.0 / 11.0 - t, h * 6.0 / 11.0, anchor='e', text='1.0', font=self.font, tags='ytick')
        self.canvas.create_text(w * 1.0 / 11.0 - t, h * 4.0 / 11.0, anchor='e', text='1.5', font=self.font, tags='ytick')
        self.canvas.create_text(w * 1.0 / 11.0 - t, h * 2.0 / 11.0, anchor='e', text='2.0', font=self.font, tags='ytick')
        self.canvas.create_text(w * 1.0 / 11.0 - t, h * 0.0 / 11.0 + 2 * t, anchor='e', text='L', font=self.font, tags='ytick')
        
    def clear_data(self):
        # only remove the data on the chart without altering the background
        self.canvas.delete('data')
    
    def draw_data(self, data, xdata=None, xb=None, yb=None, color='red', lw=1):
        # draw and update the data curve
        xb = xb if xb is not None else 1.0
        yb = yb if yb is not None else 1.0
        
        # prepare the scale and size of components
        w = self.w
        h = self.h
        t = self.t
        xu = w / 11.0 / xb
        yu = h / 11.0 / yb
        
        # update every new points in the data array
        # draw tiny line segment point-by-point
        for i in range(len(data) - 1):
            
            # prepare the starting and ending points of the line segment
            if xdata is not None:
                t0 = w * 1.0 / 11.0 + int(xdata[i] * xu)
                t1 = w * 1.0 / 11.0 + int(xdata[i+1] * xu)
            else:
                t0 = w * 1.0 / 11.0 + int(i * xu)
                t1 = w * 1.0 / 11.0 + int((i + 1) * xu)
            
            y0 = h / 11.0 * 10.0 - int(data[i] * yu)
            y1 = h / 11.0 * 10.0 - int(data[i+1] * yu)
            
            # skip if one end of the time point is out of the time axis scope
            if t0 <= 0 or t1 <= 0 or t0 >= w or t1 >= w:
                continue
            
            # clip if one end of the line segment is out of the canvas scope
            t0 = 0 if t0 <= 0 else t0
            t0 = w if t0 >= w else t0
            t1 = 0 if t1 <= 0 else t1
            t1 = w if t1 >= w else t1
            y0 = 0 if y0 <= 0 else y0
            y0 = h if y0 >= h else y0
            y1 = 0 if y1 <= 0 else y1
            y1 = h if y1 >= h else y1
            
            # draw each tiny line segments
            self.canvas.create_line(t0, y0, t1, y1, tags='data', fill=color, width=lw)
            

class KeyboardHelper(PageHelper):
    # create a frame that held a keyboard panel
    PATH_TO_USER = DEFAULT_PATH_TO_USER
    PATH_TO_DATA = os.path.join(PATH_TO_USER, 'Capd_Data')       # location of database
    PATH_TO_APP = os.path.join(PATH_TO_USER, 'VRMT_CAPD', 'of_CAPD',)
    
    def __init__(self, master, callback):
        # the pages is based on a bunch of frame containing different keys
        # the frame stacked on top of each other
        
        PageHelper.__init__(self, master)
        
        self.FONT_KEY = tkinter.font.Font(master, family='Arial', size=50, weight='bold')
        self.callback = callback

        # keyboard pages for lower/uppercase alphabet, numbers, and symbols        
        self.add_page('abc')
        self.add_page('ABC')
        self.add_page('123')
        self.add_page('#+=')
        
        self.page_abc()
        self.page_ABC()
        self.page_123()
        self.page_symbol()
        
        self.get_page('abc')
        
    def page_abc(self):
        frame = self.pages['abc']
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_rowconfigure(3, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        subframe = tk.Frame(frame)
        subframe.grid(row=0, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        subframe.grid_columnconfigure(3, weight=1)
        subframe.grid_columnconfigure(4, weight=1)
        subframe.grid_columnconfigure(5, weight=1)
        subframe.grid_columnconfigure(6, weight=1)
        subframe.grid_columnconfigure(7, weight=1)
        subframe.grid_columnconfigure(8, weight=1)
        subframe.grid_columnconfigure(9, weight=1)
        tk.Button(subframe, text='q', font=self.FONT_KEY, command=lambda x='q': self.callback(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='w', font=self.FONT_KEY, command=lambda x='w': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='e', font=self.FONT_KEY, command=lambda x='e': self.callback(x)).grid(row=0, column=2, sticky='news')
        tk.Button(subframe, text='r', font=self.FONT_KEY, command=lambda x='r': self.callback(x)).grid(row=0, column=3, sticky='news')
        tk.Button(subframe, text='t', font=self.FONT_KEY, command=lambda x='t': self.callback(x)).grid(row=0, column=4, sticky='news')
        tk.Button(subframe, text='y', font=self.FONT_KEY, command=lambda x='y': self.callback(x)).grid(row=0, column=5, sticky='news')
        tk.Button(subframe, text='u', font=self.FONT_KEY, command=lambda x='u': self.callback(x)).grid(row=0, column=6, sticky='news')
        tk.Button(subframe, text='i', font=self.FONT_KEY, command=lambda x='i': self.callback(x)).grid(row=0, column=7, sticky='news')
        tk.Button(subframe, text='o', font=self.FONT_KEY, command=lambda x='o': self.callback(x)).grid(row=0, column=8, sticky='news')
        tk.Button(subframe, text='p', font=self.FONT_KEY, command=lambda x='p': self.callback(x)).grid(row=0, column=9, sticky='news')
                
        subframe = tk.Frame(frame)
        subframe.grid(row=1, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        subframe.grid_columnconfigure(3, weight=1)
        subframe.grid_columnconfigure(4, weight=1)
        subframe.grid_columnconfigure(5, weight=1)
        subframe.grid_columnconfigure(6, weight=1)
        subframe.grid_columnconfigure(7, weight=1)
        subframe.grid_columnconfigure(8, weight=1)
        tk.Button(subframe, text='a', font=self.FONT_KEY, command=lambda x='a': self.callback(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='s', font=self.FONT_KEY, command=lambda x='s': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='d', font=self.FONT_KEY, command=lambda x='d': self.callback(x)).grid(row=0, column=2, sticky='news')
        tk.Button(subframe, text='f', font=self.FONT_KEY, command=lambda x='f': self.callback(x)).grid(row=0, column=3, sticky='news')
        tk.Button(subframe, text='g', font=self.FONT_KEY, command=lambda x='g': self.callback(x)).grid(row=0, column=4, sticky='news')
        tk.Button(subframe, text='h', font=self.FONT_KEY, command=lambda x='h': self.callback(x)).grid(row=0, column=5, sticky='news')
        tk.Button(subframe, text='j', font=self.FONT_KEY, command=lambda x='j': self.callback(x)).grid(row=0, column=6, sticky='news')
        tk.Button(subframe, text='k', font=self.FONT_KEY, command=lambda x='k': self.callback(x)).grid(row=0, column=7, sticky='news')
        tk.Button(subframe, text='l', font=self.FONT_KEY, command=lambda x='l': self.callback(x)).grid(row=0, column=8, sticky='news')
        
        subframe = tk.Frame(frame)
        subframe.grid(row=2, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        subframe.grid_columnconfigure(3, weight=1)
        subframe.grid_columnconfigure(4, weight=1)
        subframe.grid_columnconfigure(5, weight=1)
        subframe.grid_columnconfigure(6, weight=1)
        subframe.grid_columnconfigure(7, weight=1)
        subframe.grid_columnconfigure(8, weight=1)
        widget = tk.Button(subframe, command=lambda x='ABC': self.get_page(x))
        widget = attach_image(widget, f'{self.PATH_TO_APP}/pic/SHIFT.png', size=(50, 50))
        widget.grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='z', font=self.FONT_KEY, command=lambda x='z': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='x', font=self.FONT_KEY, command=lambda x='x': self.callback(x)).grid(row=0, column=2, sticky='news')
        tk.Button(subframe, text='c', font=self.FONT_KEY, command=lambda x='c': self.callback(x)).grid(row=0, column=3, sticky='news')
        tk.Button(subframe, text='v', font=self.FONT_KEY, command=lambda x='v': self.callback(x)).grid(row=0, column=4, sticky='news')
        tk.Button(subframe, text='b', font=self.FONT_KEY, command=lambda x='b': self.callback(x)).grid(row=0, column=5, sticky='news')
        tk.Button(subframe, text='n', font=self.FONT_KEY, command=lambda x='n': self.callback(x)).grid(row=0, column=6, sticky='news')
        tk.Button(subframe, text='m', font=self.FONT_KEY, command=lambda x='m': self.callback(x)).grid(row=0, column=7, sticky='news')
        widget = tk.Button(subframe, command=lambda x='delete': self.callback(x))
        widget = attach_image(widget, f'{self.PATH_TO_APP}/pic/BACKSPACE.png', size=(50, 50))
        widget.grid(row=0, column=8, sticky='news')
        
        subframe = tk.Frame(frame)
        subframe.grid(row=3, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        tk.Button(subframe, text='123', font=self.FONT_KEY, command=lambda x='123': self.get_page(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='space', font=self.FONT_KEY, command=lambda x=' ': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='return', font=self.FONT_KEY, command=lambda x='\n': self.callback(x)).grid(row=0, column=2, sticky='news')
        
    def page_ABC(self):
        frame = self.pages['ABC']
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_rowconfigure(3, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        subframe = tk.Frame(frame)
        subframe.grid(row=0, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        subframe.grid_columnconfigure(3, weight=1)
        subframe.grid_columnconfigure(4, weight=1)
        subframe.grid_columnconfigure(5, weight=1)
        subframe.grid_columnconfigure(6, weight=1)
        subframe.grid_columnconfigure(7, weight=1)
        subframe.grid_columnconfigure(8, weight=1)
        subframe.grid_columnconfigure(9, weight=1)
        tk.Button(subframe, text='Q', font=self.FONT_KEY, command=lambda x='Q': self.callback(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='W', font=self.FONT_KEY, command=lambda x='W': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='E', font=self.FONT_KEY, command=lambda x='E': self.callback(x)).grid(row=0, column=2, sticky='news')
        tk.Button(subframe, text='R', font=self.FONT_KEY, command=lambda x='R': self.callback(x)).grid(row=0, column=3, sticky='news')
        tk.Button(subframe, text='T', font=self.FONT_KEY, command=lambda x='T': self.callback(x)).grid(row=0, column=4, sticky='news')
        tk.Button(subframe, text='Y', font=self.FONT_KEY, command=lambda x='Y': self.callback(x)).grid(row=0, column=5, sticky='news')
        tk.Button(subframe, text='U', font=self.FONT_KEY, command=lambda x='U': self.callback(x)).grid(row=0, column=6, sticky='news')
        tk.Button(subframe, text='I', font=self.FONT_KEY, command=lambda x='I': self.callback(x)).grid(row=0, column=7, sticky='news')
        tk.Button(subframe, text='O', font=self.FONT_KEY, command=lambda x='O': self.callback(x)).grid(row=0, column=8, sticky='news')
        tk.Button(subframe, text='P', font=self.FONT_KEY, command=lambda x='P': self.callback(x)).grid(row=0, column=9, sticky='news')
        
        subframe = tk.Frame(frame)
        subframe.grid(row=1, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        subframe.grid_columnconfigure(3, weight=1)
        subframe.grid_columnconfigure(4, weight=1)
        subframe.grid_columnconfigure(5, weight=1)
        subframe.grid_columnconfigure(6, weight=1)
        subframe.grid_columnconfigure(7, weight=1)
        subframe.grid_columnconfigure(8, weight=1)
        tk.Button(subframe, text='A', font=self.FONT_KEY, command=lambda x='A': self.callback(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='S', font=self.FONT_KEY, command=lambda x='S': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='D', font=self.FONT_KEY, command=lambda x='D': self.callback(x)).grid(row=0, column=2, sticky='news')
        tk.Button(subframe, text='F', font=self.FONT_KEY, command=lambda x='F': self.callback(x)).grid(row=0, column=3, sticky='news')
        tk.Button(subframe, text='G', font=self.FONT_KEY, command=lambda x='G': self.callback(x)).grid(row=0, column=4, sticky='news')
        tk.Button(subframe, text='H', font=self.FONT_KEY, command=lambda x='H': self.callback(x)).grid(row=0, column=5, sticky='news')
        tk.Button(subframe, text='J', font=self.FONT_KEY, command=lambda x='J': self.callback(x)).grid(row=0, column=6, sticky='news')
        tk.Button(subframe, text='K', font=self.FONT_KEY, command=lambda x='K': self.callback(x)).grid(row=0, column=7, sticky='news')
        tk.Button(subframe, text='L', font=self.FONT_KEY, command=lambda x='L': self.callback(x)).grid(row=0, column=8, sticky='news')
        
        subframe = tk.Frame(frame)
        subframe.grid(row=2, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        subframe.grid_columnconfigure(3, weight=1)
        subframe.grid_columnconfigure(4, weight=1)
        subframe.grid_columnconfigure(5, weight=1)
        subframe.grid_columnconfigure(6, weight=1)
        subframe.grid_columnconfigure(7, weight=1)
        subframe.grid_columnconfigure(8, weight=1)
        widget = tk.Button(subframe, command=lambda x='abc': self.get_page(x))
        widget = attach_image(widget, f'{self.PATH_TO_APP}/pic/SHIFT.png', size=(50, 50))
        widget.grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='Z', font=self.FONT_KEY, command=lambda x='Z': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='X', font=self.FONT_KEY, command=lambda x='X': self.callback(x)).grid(row=0, column=2, sticky='news')
        tk.Button(subframe, text='C', font=self.FONT_KEY, command=lambda x='C': self.callback(x)).grid(row=0, column=3, sticky='news')
        tk.Button(subframe, text='V', font=self.FONT_KEY, command=lambda x='V': self.callback(x)).grid(row=0, column=4, sticky='news')
        tk.Button(subframe, text='B', font=self.FONT_KEY, command=lambda x='B': self.callback(x)).grid(row=0, column=5, sticky='news')
        tk.Button(subframe, text='N', font=self.FONT_KEY, command=lambda x='N': self.callback(x)).grid(row=0, column=6, sticky='news')
        tk.Button(subframe, text='M', font=self.FONT_KEY, command=lambda x='M': self.callback(x)).grid(row=0, column=7, sticky='news')
        widget = tk.Button(subframe, command=lambda x='delete': self.callback(x))
        widget = attach_image(widget, f'{self.PATH_TO_APP}/pic/BACKSPACE.png', size=(50, 50))
        widget.grid(row=0, column=8, sticky='news')
        
        subframe = tk.Frame(frame)
        subframe.grid(row=3, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        tk.Button(subframe, text='123', font=self.FONT_KEY, command=lambda x='123': self.get_page(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='space', font=self.FONT_KEY, command=lambda x=' ': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='return', font=self.FONT_KEY, command=lambda x='\n': self.callback(x)).grid(row=0, column=2, sticky='news')
        
    def page_123(self):
        frame = self.pages['123']
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_rowconfigure(3, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        subframe = tk.Frame(frame)
        subframe.grid(row=0, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        subframe.grid_columnconfigure(3, weight=1)
        subframe.grid_columnconfigure(4, weight=1)
        subframe.grid_columnconfigure(5, weight=1)
        subframe.grid_columnconfigure(6, weight=1)
        subframe.grid_columnconfigure(7, weight=1)
        subframe.grid_columnconfigure(8, weight=1)
        subframe.grid_columnconfigure(9, weight=1)
        tk.Button(subframe, text='1', font=self.FONT_KEY, command=lambda x='1': self.callback(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='2', font=self.FONT_KEY, command=lambda x='2': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='3', font=self.FONT_KEY, command=lambda x='3': self.callback(x)).grid(row=0, column=2, sticky='news')
        tk.Button(subframe, text='4', font=self.FONT_KEY, command=lambda x='4': self.callback(x)).grid(row=0, column=3, sticky='news')
        tk.Button(subframe, text='5', font=self.FONT_KEY, command=lambda x='5': self.callback(x)).grid(row=0, column=4, sticky='news')
        tk.Button(subframe, text='6', font=self.FONT_KEY, command=lambda x='6': self.callback(x)).grid(row=0, column=5, sticky='news')
        tk.Button(subframe, text='7', font=self.FONT_KEY, command=lambda x='7': self.callback(x)).grid(row=0, column=6, sticky='news')
        tk.Button(subframe, text='8', font=self.FONT_KEY, command=lambda x='8': self.callback(x)).grid(row=0, column=7, sticky='news')
        tk.Button(subframe, text='9', font=self.FONT_KEY, command=lambda x='9': self.callback(x)).grid(row=0, column=8, sticky='news')
        tk.Button(subframe, text='0', font=self.FONT_KEY, command=lambda x='0': self.callback(x)).grid(row=0, column=9, sticky='news')
        
        subframe = tk.Frame(frame)
        subframe.grid(row=1, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        subframe.grid_columnconfigure(3, weight=1)
        subframe.grid_columnconfigure(4, weight=1)
        subframe.grid_columnconfigure(5, weight=1)
        subframe.grid_columnconfigure(6, weight=1)
        subframe.grid_columnconfigure(7, weight=1)
        subframe.grid_columnconfigure(8, weight=1)
        subframe.grid_columnconfigure(9, weight=1)
        tk.Button(subframe, text='-', font=self.FONT_KEY, command=lambda x='-': self.callback(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='/', font=self.FONT_KEY, command=lambda x='/': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text=':', font=self.FONT_KEY, command=lambda x=':': self.callback(x)).grid(row=0, column=2, sticky='news')
        tk.Button(subframe, text=';', font=self.FONT_KEY, command=lambda x=';': self.callback(x)).grid(row=0, column=3, sticky='news')
        tk.Button(subframe, text='(', font=self.FONT_KEY, command=lambda x='(': self.callback(x)).grid(row=0, column=4, sticky='news')
        tk.Button(subframe, text=')', font=self.FONT_KEY, command=lambda x=')': self.callback(x)).grid(row=0, column=5, sticky='news')
        tk.Button(subframe, text='$', font=self.FONT_KEY, command=lambda x='$': self.callback(x)).grid(row=0, column=6, sticky='news')
        tk.Button(subframe, text='&', font=self.FONT_KEY, command=lambda x='&': self.callback(x)).grid(row=0, column=7, sticky='news')
        tk.Button(subframe, text='@', font=self.FONT_KEY, command=lambda x='@': self.callback(x)).grid(row=0, column=8, sticky='news')
        tk.Button(subframe, text='"', font=self.FONT_KEY, command=lambda x='\"': self.callback(x)).grid(row=0, column=9, sticky='news')
        
        subframe = tk.Frame(frame)
        subframe.grid(row=2, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        subframe.grid_columnconfigure(3, weight=1)
        subframe.grid_columnconfigure(4, weight=1)
        subframe.grid_columnconfigure(5, weight=1)
        subframe.grid_columnconfigure(6, weight=1)
        subframe.grid_columnconfigure(7, weight=1)
        subframe.grid_columnconfigure(8, weight=1)
        tk.Button(subframe, text='#+=', font=self.FONT_KEY, command=lambda x='#+=': self.get_page(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='.', font=self.FONT_KEY, command=lambda x='.': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text=',', font=self.FONT_KEY, command=lambda x=',': self.callback(x)).grid(row=0, column=2, sticky='news')
        tk.Button(subframe, text='?', font=self.FONT_KEY, command=lambda x='?': self.callback(x)).grid(row=0, column=3, sticky='news')
        tk.Button(subframe, text='!', font=self.FONT_KEY, command=lambda x='!': self.callback(x)).grid(row=0, column=4, sticky='news')
        tk.Button(subframe, text="'", font=self.FONT_KEY, command=lambda x="'": self.callback(x)).grid(row=0, column=5, sticky='news')
        tk.Button(subframe, text='˚', font=self.FONT_KEY, command=lambda x='˚': self.callback(x)).grid(row=0, column=6, sticky='news')
        tk.Button(subframe, text='±', font=self.FONT_KEY, command=lambda x='±': self.callback(x)).grid(row=0, column=7, sticky='news')
        widget = tk.Button(subframe, command=lambda x='delete': self.callback(x))
        widget = attach_image(widget, f'{self.PATH_TO_APP}/pic/BACKSPACE.png', size=(50, 50))
        widget.grid(row=0, column=8, sticky='news')
        
        subframe = tk.Frame(frame)
        subframe.grid(row=3, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        tk.Button(subframe, text='abc', font=self.FONT_KEY, command=lambda x='abc': self.get_page(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='space', font=self.FONT_KEY, command=lambda x=' ': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='return', font=self.FONT_KEY, command=lambda x='\n': self.callback(x)).grid(row=0, column=2, sticky='news')
        
    def page_symbol(self):
        frame = self.pages['#+=']
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_rowconfigure(3, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        subframe = tk.Frame(frame)
        subframe.grid(row=0, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        subframe.grid_columnconfigure(3, weight=1)
        subframe.grid_columnconfigure(4, weight=1)
        subframe.grid_columnconfigure(5, weight=1)
        subframe.grid_columnconfigure(6, weight=1)
        subframe.grid_columnconfigure(7, weight=1)
        subframe.grid_columnconfigure(8, weight=1)
        subframe.grid_columnconfigure(9, weight=1)
        tk.Button(subframe, text='[', font=self.FONT_KEY, command=lambda x='[': self.callback(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text=']', font=self.FONT_KEY, command=lambda x=']': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='{', font=self.FONT_KEY, command=lambda x='{': self.callback(x)).grid(row=0, column=2, sticky='news')
        tk.Button(subframe, text='}', font=self.FONT_KEY, command=lambda x='}': self.callback(x)).grid(row=0, column=3, sticky='news')
        tk.Button(subframe, text='#', font=self.FONT_KEY, command=lambda x='#': self.callback(x)).grid(row=0, column=4, sticky='news')
        tk.Button(subframe, text='%', font=self.FONT_KEY, command=lambda x='%': self.callback(x)).grid(row=0, column=5, sticky='news')
        tk.Button(subframe, text='^', font=self.FONT_KEY, command=lambda x='^': self.callback(x)).grid(row=0, column=6, sticky='news')
        tk.Button(subframe, text='*', font=self.FONT_KEY, command=lambda x='*': self.callback(x)).grid(row=0, column=7, sticky='news')
        tk.Button(subframe, text='+', font=self.FONT_KEY, command=lambda x='+': self.callback(x)).grid(row=0, column=8, sticky='news')
        tk.Button(subframe, text='=', font=self.FONT_KEY, command=lambda x='=': self.callback(x)).grid(row=0, column=9, sticky='news')
        
        subframe = tk.Frame(frame)
        subframe.grid(row=1, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        subframe.grid_columnconfigure(3, weight=1)
        subframe.grid_columnconfigure(4, weight=1)
        subframe.grid_columnconfigure(5, weight=1)
        subframe.grid_columnconfigure(6, weight=1)
        subframe.grid_columnconfigure(7, weight=1)
        subframe.grid_columnconfigure(8, weight=1)
        subframe.grid_columnconfigure(9, weight=1)
        tk.Button(subframe, text='_', font=self.FONT_KEY, command=lambda x='_': self.callback(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='\\', font=self.FONT_KEY, command=lambda x='\\': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='|', font=self.FONT_KEY, command=lambda x='|': self.callback(x)).grid(row=0, column=2, sticky='news')
        tk.Button(subframe, text='~', font=self.FONT_KEY, command=lambda x='~': self.callback(x)).grid(row=0, column=3, sticky='news')
        tk.Button(subframe, text='<', font=self.FONT_KEY, command=lambda x='<': self.callback(x)).grid(row=0, column=4, sticky='news')
        tk.Button(subframe, text='>', font=self.FONT_KEY, command=lambda x='>': self.callback(x)).grid(row=0, column=5, sticky='news')
        tk.Button(subframe, text='¥', font=self.FONT_KEY, command=lambda x='¥': self.callback(x)).grid(row=0, column=6, sticky='news')
        tk.Button(subframe, text='€', font=self.FONT_KEY, command=lambda x='€': self.callback(x)).grid(row=0, column=7, sticky='news')
        tk.Button(subframe, text='£', font=self.FONT_KEY, command=lambda x='£': self.callback(x)).grid(row=0, column=8, sticky='news')
        tk.Button(subframe, text='•', font=self.FONT_KEY, command=lambda x='•': self.callback(x)).grid(row=0, column=9, sticky='news')
        
        subframe = tk.Frame(frame)
        subframe.grid(row=2, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        subframe.grid_columnconfigure(3, weight=1)
        subframe.grid_columnconfigure(4, weight=1)
        subframe.grid_columnconfigure(5, weight=1)
        subframe.grid_columnconfigure(6, weight=1)
        subframe.grid_columnconfigure(7, weight=1)
        subframe.grid_columnconfigure(8, weight=1)
        tk.Button(subframe, text='123', font=self.FONT_KEY, command=lambda x='123': self.get_page(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='.', font=self.FONT_KEY, command=lambda x='.': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text=',', font=self.FONT_KEY, command=lambda x=',': self.callback(x)).grid(row=0, column=2, sticky='news')
        tk.Button(subframe, text='?', font=self.FONT_KEY, command=lambda x='?': self.callback(x)).grid(row=0, column=3, sticky='news')
        tk.Button(subframe, text='!', font=self.FONT_KEY, command=lambda x='!': self.callback(x)).grid(row=0, column=4, sticky='news')
        tk.Button(subframe, text="'", font=self.FONT_KEY, command=lambda x="'": self.callback(x)).grid(row=0, column=5, sticky='news')
        tk.Button(subframe, text='˚', font=self.FONT_KEY, command=lambda x='˚': self.callback(x)).grid(row=0, column=6, sticky='news')
        tk.Button(subframe, text='±', font=self.FONT_KEY, command=lambda x='±': self.callback(x)).grid(row=0, column=7, sticky='news')
        widget = tk.Button(subframe, command=lambda x='delete': self.callback(x))
        widget = attach_image(widget, f'{self.PATH_TO_APP}/pic/BACKSPACE.png', size=(50, 50))
        widget.grid(row=0, column=8, sticky='news')
        
        subframe = tk.Frame(frame)
        subframe.grid(row=3, column=0, sticky='news')
        subframe.grid_columnconfigure(0, weight=1)
        subframe.grid_columnconfigure(1, weight=1)
        subframe.grid_columnconfigure(2, weight=1)
        tk.Button(subframe, text='abc', font=self.FONT_KEY, command=lambda x='abc': self.get_page(x)).grid(row=0, column=0, sticky='news')
        tk.Button(subframe, text='space', font=self.FONT_KEY, command=lambda x=' ': self.callback(x)).grid(row=0, column=1, sticky='news')
        tk.Button(subframe, text='return', font=self.FONT_KEY, command=lambda x='\n': self.callback(x)).grid(row=0, column=2, sticky='news')
        

class VideoHelper(tk.Frame):
    # create a video frame that can play a specified video clip
    FRAME_RATE = 0.04
    
    def __init__(self, master, src=None, size=None, callback=None):
        tk.Frame.__init__(self, master)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Label widget to play the video
        self.screen = tk.Label(self)
        self.screen.grid(row=0, column=0, sticky='news')
        
        # config the video screen
        self.size = None
        self.src = None
        self.callback = None
        self.thread = None
        self.frame = None
        
        self.set_size(size)
        self.set_source(src)
        self.set_callback(callback)
        
    def set_size(self, size):
        if size:
            # size of video screen
            self.size = size
        
    def set_source(self, src):
        if src:
            self.src = src
            
    def set_callback(self, callback):
        if callback:
            self.callback = callback
            
    def set_thread(self, callback=None):
        # either call user customized function or the default "playing" funciton
        func = callback if callback is not None else lambda: self.play(cvt_color=True)
        self.thread = Tools.TimedLoop(period=self.FRAME_RATE, callback=func)
            
    def play(self, text=None, indicator=None, cvt_color=False):
        # get the video frame and play it on the screen
        ret, self.frame = self.src.read()
        if ret:
            self.attach_image(self.frame, cvt_color=cvt_color, text=text, indicator=indicator)
        else:
            self.src.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.src.release()
            time.sleep(1)
            
    def restart(self):
        self.stop()
        self.set_thread()
        self.thread.start()
    
    def stop(self):
        # set the event to terminate the thread, i.e., stop the video playing
        self.thread.stop()
        
    def attach_image(self, frame, cvt_color=False, text=None, indicator=None):
        
        if self.size:
            # image resize
            frame = cv2.resize(frame, self.size, fx=0.4, fy=0.4)
            
        if cvt_color:
            # image convert color config
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
        if text:
            # attach text and video recording red dot on top of the screen
            r = int(self.size[1] / 20)
            cv2.putText(frame, text, (r*3, r*3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1, cv2.LINE_AA)
            if indicator is not None and indicator:
                cv2.circle(frame, (r*2, r*3), radius=int(r/2), color=(255, 0, 0), thickness=-1)
            
        # attach the image frame onto the widget    
        image = Image.fromarray(frame)
        image = ImageTk.PhotoImage(image)
        
        self.screen.config(image=image)
        self.screen.image = image
        
        
class WarningDialog(tk.Toplevel):
    
    def __init__(self, master, title, text, color='red'):
        tk.Toplevel.__init__(self, master)
        self.title(title)
        self.overrideredirect(True)
        
        frame = tk.Frame(self, bg=color)
        frame.pack()
        
        subframe = tk.LabelFrame(frame, text=title, font='Arial 30 bold')
        subframe.pack(padx=10, pady=10)
        
        tk.Label(subframe, text=text, font='Arial 20 bold').grid(row=0, column=0, sticky='news', padx=10, pady=10)
        tk.Button(subframe, text='OK', command=self.destroy, font='Arial 30 bold').grid(row=1, column=0, sticky='news', padx=10, pady=10)
        
        self.wait_visibility()
        
        x = master.winfo_x() + master.winfo_width()//2 - self.winfo_width()//2
        y = master.winfo_y() + master.winfo_height()//2 - self.winfo_height()//2
        self.geometry(f"+{x}+{y}")
        
        self.transient(master)
        self.grab_set()
        self.focus_set()
        master.wait_window(self)


class InputDialog(tk.Toplevel):
    
    def __init__(self, master, title, text, command=None, color='red'):
        tk.Toplevel.__init__(self, master)
        self.title(title)
        self.overrideredirect(True)
        self.command = command
        
        frame = tk.Frame(self, bg=color)
        frame.pack()
        
        subframe = tk.LabelFrame(frame, text=title, font='Arial 30 bold')
        subframe.pack(padx=10, pady=10)
        
        tk.Label(subframe, text=text, font='Arial 20 bold').grid(row=0, column=0, sticky='news', padx=10, pady=10)
        self.widget = tk.Entry(subframe)
        self.widget.grid(row=1, column=0, sticky='news', padx=10, pady=10)
        
        tk.Button(subframe, text='OK', command=self.action, font='Arial 30 bold').grid(row=2, column=0, sticky='news', padx=10, pady=10)
        
        self.wait_visibility()
        
        x = master.winfo_x() + master.winfo_width()//2 - self.winfo_width()//2
        y = master.winfo_y() + master.winfo_height()//2 - self.winfo_height()//2
        self.geometry(f"+{x}+{y}")
        
        self.transient(master)
        self.grab_set()
        self.focus_set()
        master.wait_window(self)
        
    def action(self):
        self.command(self.widget.get())
        self.destroy()
                
        
class AuthenticationDialog(tk.Toplevel):
    
    def __init__(self, master, title, text, color='yellow'):
        tk.Toplevel.__init__(self, master)
        self.title(title)
        self.overrideredirect(True)
        
        frame = tk.Frame(self, bg=color)
        frame.pack()
        
        subframe = tk.LabelFrame(frame, text=title, font='Arial 30 bold')
        subframe.pack(padx=10, pady=10)
        
        tk.Label(subframe, text=text, font='Arial 20 bold').grid(row=0, column=0, columnspan=2, sticky='news', padx=10, pady=10)
        
        self.widget = tk.Entry(subframe, show='*', font='Arial 20 bold')
        self.widget.insert(0, '')
        self.widget.grid(row=1, column=0, columnspan=2, sticky='news', padx=10, pady=10)
        
        tk.Button(subframe, text='OK', command=self.selected_ok, font='Arial 30 bold').grid(row=2, column=0, sticky='news', padx=10, pady=10)
        tk.Button(subframe, text='CANCEL', command=self.selected_cancel, font='Arial 30 bold').grid(row=2, column=1, sticky='news', padx=10, pady=10)
        
        self.wait_visibility()
        
        x = master.winfo_x() + master.winfo_width()//2 - self.winfo_width()//2
        y = master.winfo_y() + master.winfo_height()//2 - self.winfo_height()//2
        self.geometry(f"+{x}+{y}")
        
        self.transient(master)
        self.grab_set()
        self.focus_set()
        master.wait_window(self)
        
    def selected_ok(self):
        self.result = self.widget.get()
        self.destroy()
    
    def selected_cancel(self):
        self.result = False
        self.destroy()
        
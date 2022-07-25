"""
File:                       DaqDevDiscovery01.py

Library Call Demonstrated:  mcculw.ul.get_daq_device_inventory()
                            mcculw.ul.create_daq_device()
                            mcculw.ul.release_daq_device()

Purpose:                    Discovers DAQ devices and assigns board number to
                            the detected devices.

Demonstration:              Displays the detected DAQ devices and flashes the
                            LED of the selected device.

Other Library Calls:        mcculw.ul.ignore_instacal()
                            mcculw.ul.flash_led()
"""
from __future__ import absolute_import, division, print_function

import sys
import threading
import time
import tkinter as tk
from builtins import *  # @UnusedWildImport
from tkinter import StringVar
from tkinter.ttk import Combobox  # @UnresolvedImport

from mcculw import ul
from mcculw.device_info import DaqDeviceInfo, DioInfo
from mcculw.enums import InterfaceType, DigitalIODirection, DigitalPortType

try:
    from ui_examples_util import UIExample, show_ul_error
except ImportError:
    from .ui_examples_util import UIExample, show_ul_error


board_resolution = 4096
board_voltage_range = 4
board_ramping_analog_channel = 1
ramp_target_voltage = 2
ramp_start_voltage = 0
inverse_display_rate = 4


class DAQ_AO1_Ramping(UIExample):

    def __init__(self, resolution, voltage_range, analog_channel, start_voltage, target_voltage, master):
        super(DAQ_AO1_Ramping, self).__init__(master)
        # Declaring a bunch of variables

        self.up_to_output = None
        self.ramp_up_to = None  # Initialize all the variables, as suggested by Pycharm
        self.down_to_output = None
        self.ramp_down_to = None
        self.ramp_down_to_input_box = None
        self.restart_step_count = None
        self.end_voltage_text = None
        self.ramp_rate_voltage_text = None
        self.start_voltage_text = None
        self.Ramp_rate_input_box = None
        self.End_voltage_input_box = None
        self.Start_voltage_input_box = None
        self.device_info = None
        self.board_num = 0
        self.daqo_info = " "
        self.device_created = False
        self.canvas = None
        self.DAQ_Info_text = None
        self.ramping_up = threading.Event()
        self.ramping_down = threading.Event()
        self.ramp_count = 0
        self.Start_voltage_input_box = None
        self.dio_info = DioInfo(self.board_num)
        self.board_resolution = resolution
        self.board_voltage_range = voltage_range
        self.board_ramping_analog_channel = analog_channel
        self.ramp_start_voltage = start_voltage
        self.ramp_target_voltage = target_voltage
        self.board_ground_voltage = 0  # Mapping the desired voltage (start, end,
        # and ground reference) to the 16-bit analog output pin

        # These next 4 lines could be unnecessary, might replace with = None later. These variables are computed again when initializing the board
        self.start_analog_output = 0
        self.target_analog_output = 0
        self.step_rate = 0.01  # volts/second for 0-10V range, placeholder, will be set later.
        self.step_delay = (self.board_voltage_range / self.step_rate) / (self.board_resolution / 2)

        self.current_voltage = 0.0
        self.current_step_count = 0
        # Tell the UL to ignore any boards configured in InstaCal
        ul.ignore_instacal()

        self.create_widgets()

    def discover_devices(self):  # initializing the buttons after device is found, un-grey them all
        self.inventory = ul.get_daq_device_inventory(InterfaceType.ANY)

        if len(self.inventory) > 0:
            combobox_values = []
            for device in self.inventory:
                combobox_values.append(str(device))

            self.devices_combobox["values"] = combobox_values
            self.devices_combobox.current(0)
            self.status_label["text"] = (str(len(self.inventory))
                                         + " DAQ Device(s) Discovered")
            self.devices_combobox["state"] = "readonly"
            self.begin_ramping_up_button["state"] = "normal"
            self.stop_ramping_button["state"] = "normal"
            self.initiate_board_button["state"] = "normal"
            self.ramp_down_button["state"] = "normal"
            self.quick_ramp_down_button["state"] = "normal"
            self.quick_ramp_down_to_button["state"] = "normal"
            # self.volt_switch_button["state"] = "normal"
            self.quick_ramp_up_to_button["state"] = "normal"

        else:
            self.devices_combobox["values"] = [""]
            self.devices_combobox.current(0)
            self.status_label["text"] = "No Devices Discovered"
            self.devices_combobox["state"] = "disabled"
            self.begin_ramping_up_button["state"] = "disabled"
            self.stop_ramping_button["state"] = "disabled"
            self.initiate_board_button["state"] = "disabled"
            self.ramp_down_button["state"] = "disabled"
            self.quick_ramp_down_button["state"] = "disabled"
            self.quick_ramp_down_to_button["state"] = "disabled"
            self.quick_ramp_up_to_button["state"] = "disabled"
            # self.volt_switch_button["state"] = "disabled"
            # Beginning of change June 9, 2022

    def initiate_board(self):  # initalize the connected board, compute and map the voltage values, set pin voltage to 0,
        # zero all the thread control variables and get the ramping threads ready
        self.ramping_up.clear()
        self.ramping_down.clear()
        ul.a_out(self.board_num, self.board_ramping_analog_channel, self.board_voltage_range,
                 self.board_ground_voltage)  # Reset analog output to ground voltage
        #
        # ul.d_config_port(self.board_num, DigitalPortType.AUXPORT,
        #                  DigitalIODirection.IN)  # configure the digital ports to input mode

        # configure the digital ports for reading the pause ramping & hold signal

        # compute the start and end voltage, and the ramp rate in terms of analog output resolution, based on the user input in the textboxes
        self.ramp_start_voltage = self.Start_voltage_input_box.get()
        self.ramp_target_voltage = self.End_voltage_input_box.get()
        self.step_rate = self.Ramp_rate_input_box.get()

        # If the text boxes are empty, then replace with 0 as placeholders
        if self.ramp_start_voltage == '':
            self.ramp_start_voltage = 0.0
        else:
            self.ramp_start_voltage = float(self.ramp_start_voltage)

        if self.ramp_target_voltage == '':
            self.ramp_target_voltage = 0.0
        else:
            self.ramp_target_voltage = float(self.ramp_target_voltage)

        if self.step_rate == '':
            self.step_rate = 0.00001 / (4 / self.board_voltage_range)
        else:
            self.step_rate = float(self.step_rate) / (4 / self.board_voltage_range)

        if self.ramp_start_voltage > self.board_voltage_range:
            self.ramp_start_voltage = self.board_voltage_range
        if self.ramp_target_voltage > self.board_voltage_range:
            self.ramp_target_voltage = self.board_voltage_range

        # zero the step counts
        self.current_voltage = 0.0
        self.current_step_count = 0

        # Compute the stepping rate and range based on user input and display the results as on-screen message
        self.start_analog_output = int((self.board_resolution) * (
                self.ramp_start_voltage / self.board_voltage_range) + self.board_ground_voltage) #/2 removed
        self.target_analog_output = int((self.board_resolution) * (
                self.ramp_target_voltage / self.board_voltage_range) + self.board_ground_voltage) #/2 removed
        self.restart_step_count = self.start_analog_output
        self.current_step_count = self.start_analog_output
        self.step_delay = (self.board_voltage_range / self.step_rate) / (self.board_resolution) #/2 removed
        self.canvas.itemconfigure(self.DAQ_Info_text,
                                  text="DAQ initiated:\nStarting voltage " + str(self.ramp_start_voltage)
                                       + " V\nFinal voltage " + str(self.ramp_target_voltage) + " V\nRamp rate " + str(
                                      self.step_rate) + " V/s")
        self.canvas.itemconfigure(self.DAQ_State_text,
                                  text="Current Status: \nAnalog Output at 0V\nReady for ramping up")

    def begin_ramping_up(self):

        self.ramping_up.set()
        self.ramping_down.clear()

        if self.ramping_up.isSet():
            self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping up\n" + str(
                round(self.current_voltage, 3)) + " V")

        # disable all other buttons except "pause" when a ramp is happening.
        self.begin_ramping_up_button["state"] = "disabled"
        self.ramp_down_button["state"] = "disabled"
        self.stop_ramping_button["state"] = "normal"
        self.quick_ramp_down_button["state"] = "disabled"
        self.initiate_board_button["state"] = "disabled"
        self.quick_ramp_down_to_button["state"] = "disabled"
        self.quick_ramp_up_to_button["state"] = "disabled"
        self.restart_step_count = self.current_step_count  # keep track of where the ramp started/stopped

        self.ramp_up_thread = threading.Thread(target=self.ramp_up_loop)  # begin the normal ramping up thread
        self.ramp_up_thread.start()



    def ramp_up_loop(self):

        loopCount = 0
        for i in range(self.restart_step_count, self.target_analog_output):
            if not self.ramping_up.isSet():
                self.canvas.itemconfigure(self.DAQ_State_text,
                                          text="Current Status: \nRamping paused\n holding at " + str(
                                              round(self.current_voltage, 3)) + " V")

                break
            ul.a_out(self.board_num, board_ramping_analog_channel, board_voltage_range, i) # writing to the analog pin
            self.current_step_count = i  # keep track of the 16-bit count
            self.current_voltage = self.board_voltage_range * (
                    (i - self.board_ground_voltage) / (self.board_resolution - self.board_ground_voltage))
            loopCount = loopCount + 1  # used by the display counter, so the displayed voltage value doesn't fluctuate too fast
            if loopCount % inverse_display_rate == 0:
                self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping up\n" + str(
                    round(self.current_voltage, 3)) + " V")

            time.sleep(self.step_delay - (time.time() % self.step_delay))  # self synchronizing time delay

        self.canvas.itemconfigure(self.DAQ_State_text,
                                  text="Current Status: \nRamping up completed,\n holding at " + str(
                                      round(self.current_voltage, 3)) + " V")

        self.begin_ramping_up_button["state"] = "normal"  # enable all the buttons when the ramping ends
        self.ramp_down_button["state"] = "normal"
        self.quick_ramp_down_button["state"] = "normal"
        self.quick_ramp_down_to_button["state"] = "normal"
        self.initiate_board_button["state"] = "normal"
        self.quick_ramp_up_to_button["state"] = "normal"
        sys.exit()  # exit thread when the ramp is done or asked to stop


    def stop_ramping(self):
        self.ramping_up.clear()  # change the ramping boolean to false, thus the ramping stops and holds at current voltage
        self.ramping_down.clear()

    def begin_ramping_down(self):


        self.ramping_up.clear()
        self.ramping_down.set()
        if self.ramping_down.isSet():
            self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping down\n" + str(
                round(self.current_voltage, 3)) + " V")
        self.restart_step_count = self.current_step_count
        self.ramp_down_thread = threading.Thread(target=self.ramp_down_loop)
        self.ramp_down_thread.start()


        self.begin_ramping_up_button["state"] = "disabled"
        self.ramp_down_button["state"] = "disabled"
        self.quick_ramp_down_button["state"] = "disabled"
        self.initiate_board_button["state"] = "disabled"
        self.quick_ramp_down_to_button["state"] = "disabled"
        self.quick_ramp_up_to_button["state"] = "disabled"

    def ramp_down_loop(self):

        loopCount = 0
        for i in range(self.restart_step_count, self.start_analog_output, -1):
            ul.a_out(self.board_num, board_ramping_analog_channel, board_voltage_range, i)
            self.current_voltage = self.board_voltage_range * (
                    (i - self.board_ground_voltage) / (self.board_resolution - self.board_ground_voltage))
            loopCount = loopCount + 1
            self.current_step_count = i  # keep track of the 16-bit count
            if loopCount % inverse_display_rate == 0:
                self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping down\n" + str(
                    round(self.current_voltage, 3)) + " V")
            time.sleep(self.step_delay - (time.time() % self.step_delay))  # self synchronizing time delay
            if not self.ramping_down.isSet():
                self.canvas.itemconfigure(self.DAQ_State_text,
                                          text="Current Status: \nRamping paused\n holding at " + str(
                                              round(self.current_voltage, 3)) + " V")
                break
        self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping down complete:\n" + str(
            round(self.current_voltage, 3)) + " V")

        self.begin_ramping_up_button["state"] = "normal"  # enable all the buttons when the ramping ends
        self.ramp_down_button["state"] = "normal"
        self.quick_ramp_down_button["state"] = "normal"
        self.quick_ramp_down_to_button["state"] = "normal"
        self.initiate_board_button["state"] = "normal"
        self.quick_ramp_up_to_button["state"] = "normal"
        sys.exit()  # exit thread when the ramp is done or asked to stop

    def begin_quick_ramping_down(self):

        self.ramping_up.clear()
        self.ramping_down.set()
        if self.ramping_down.isSet():
            self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping down\n" + str(
                round(self.current_voltage, 3)) + " V")

        self.quick_ramp_down_thread = threading.Thread(target=self.quick_ramp_down_loop)
        self.quick_ramp_down_thread.start()

        self.begin_ramping_up_button["state"] = "disabled"
        self.ramp_down_button["state"] = "disabled"
        self.stop_ramping_button["state"] = "normal" #stop ramping button should always be available to pause the ramp
        self.quick_ramp_down_button["state"] = "disabled"
        self.quick_ramp_down_to_button["state"] = "disabled"
        self.quick_ramp_up_to_button["state"] = "disabled"
        self.initiate_board_button["state"] = "disabled"

    def quick_ramp_down_loop(self):

        self.short_step_delay = 1 / self.current_step_count

        loopCount = 0
        rate = int(round(self.current_voltage * -4))
        if rate == 0:
            rate = -1
        for i in range(self.current_step_count, self.board_ground_voltage, rate):
            ul.a_out(self.board_num, board_ramping_analog_channel, board_voltage_range, i)
            self.current_voltage = self.board_voltage_range * (
                    (i - self.board_ground_voltage) / (self.board_resolution - self.board_ground_voltage))
            loopCount = loopCount + 1
            self.current_step_count = i
            if loopCount % inverse_display_rate == 0:
                self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping down\n" + str(
                    round(self.current_voltage, 3)) + " V")
            time.sleep(self.short_step_delay - (time.time() % self.short_step_delay))  # self synchronizing time delay
            # time.sleep(self.short_step_delay)
            if not self.ramping_down.isSet():
                self.canvas.itemconfigure(self.DAQ_State_text,
                                          text="Current Status: \nRamping paused\n holding at " + str(
                                              round(self.current_voltage, 3)) + " V")
                break
        self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping down complete:\n" + str(
            round(self.current_voltage, 3)) + " V")

        self.begin_ramping_up_button["state"] = "normal"  # enable all the buttons when the ramping ends
        self.ramp_down_button["state"] = "normal"
        self.stop_ramping_button["state"] = "normal"
        self.quick_ramp_down_button["state"] = "normal"
        self.quick_ramp_down_to_button["state"] = "normal"
        self.quick_ramp_up_to_button["state"] = "normal"
        self.initiate_board_button["state"] = "normal"
        sys.exit()

    def quick_ramp_down_to(self):
        # if self.ramp_up_thread.is_alive():
        #     self.stop_ramping()
        #     self.ramping_up.clear()
        #     time.sleep(1)
        #     self.ramp_up_thread.join()

        self.ramp_down_to = self.ramp_down_to_input_box.get()

        if self.ramp_down_to == '':
            self.ramp_down_to = 0.0
        else:
            self.ramp_down_to = float(self.ramp_down_to)

        self.ramping_up.clear()
        self.ramping_down.set()
        if self.ramping_down.isSet():
            self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping down\n" + str(
                round(self.current_voltage, 3)) + " V")

        self.quick_ramp_down_to_thread = threading.Thread(target=self.quick_ramp_down_to_loop)
        self.quick_ramp_down_to_thread.start()

        self.begin_ramping_up_button["state"] = "disabled"
        self.ramp_down_button["state"] = "disabled"
        self.stop_ramping_button["state"] = "normal"
        self.quick_ramp_down_button["state"] = "disabled"
        self.quick_ramp_down_to_button["state"] = "disabled"
        self.quick_ramp_up_to_button["state"] = "disabled"
        self.initiate_board_button["state"] = "disabled"

    def quick_ramp_up_to(self):

        self.ramp_up_to = self.ramp_up_to_input_box.get()

        if self.ramp_up_to == '':
            self.ramp_up_to = 0.0
        else:
            self.ramp_up_to = float(self.ramp_up_to)

        self.ramping_up.set()
        self.ramping_down.clear()
        if self.ramping_up.isSet():
            self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping up\n" + str(
                round(self.current_voltage, 3)) + " V")

        self.quick_ramp_up_to_thread = threading.Thread(target=self.quick_ramp_up_to_loop)
        self.quick_ramp_up_to_thread.start()

        self.begin_ramping_up_button["state"] = "disabled" #  disable all the buttons except the pausing button to allow
        self.ramp_down_button["state"] = "disabled"
        self.stop_ramping_button["state"] = "normal"
        self.quick_ramp_down_button["state"] = "disabled"
        self.quick_ramp_down_to_button["state"] = "disabled"
        self.quick_ramp_up_to_button["state"] = "disabled"
        self.initiate_board_button["state"] = "disabled"

    def quick_ramp_down_to_loop(self): #the loop that ramps the AO1 voltage down to a user set value at a fairly fast rate

        self.short_step_delay = 1 / self.current_step_count  #computing the loop delays and where the loop ends
        self.down_to_output = int((self.board_resolution) * ( #/2 removed
                self.ramp_down_to / self.board_voltage_range) + self.board_ground_voltage)
        loopCount = 0
        rate = int(round(self.current_voltage * -1)) # negative rate for ramping down
        if rate == 0:
            rate = -1
        for i in range(self.current_step_count, self.down_to_output, rate):
            ul.a_out(self.board_num, board_ramping_analog_channel, board_voltage_range, i)
            self.current_voltage = self.board_voltage_range * (
                    (i - self.board_ground_voltage) / (self.board_resolution - self.board_ground_voltage))
            loopCount = loopCount + 1
            self.current_step_count = i
            if loopCount % inverse_display_rate == 0:
                self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping down\n" + str(
                    round(self.current_voltage, 3)) + " V")
            time.sleep(self.short_step_delay - (time.time() % self.short_step_delay))  # self synchronizing time delay
            # time.sleep(self.short_step_delay)
            if not self.ramping_down.isSet():
                self.canvas.itemconfigure(self.DAQ_State_text,
                                          text="Current Status: \nRamping paused\n holding at " + str(
                                              round(self.current_voltage, 3)) + " V")
                break
        self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping down complete:\n" + str(
            round(self.current_voltage, 3)) + " V")

        self.begin_ramping_up_button["state"] = "normal"  # enable all the buttons when the ramping ends
        self.ramp_down_button["state"] = "normal"
        self.stop_ramping_button["state"] = "normal"
        self.quick_ramp_down_button["state"] = "normal"
        self.quick_ramp_down_to_button["state"] = "normal"
        self.quick_ramp_up_to_button["state"] = "normal"
        self.initiate_board_button["state"] = "normal"
        sys.exit()

    def quick_ramp_up_to_loop(self): #essentially the same structure as above except the rate is now positive

        self.short_step_delay = 1 / self.current_step_count
        self.up_to_output = int((self.board_resolution) * (#/2 removed
                self.ramp_up_to / self.board_voltage_range) + self.board_ground_voltage)
        loopCount = 0
        rate = int(round(self.current_voltage * 4))
        if rate == 0:
            rate = 1
        for i in range(self.current_step_count, self.up_to_output, rate):
            ul.a_out(self.board_num, board_ramping_analog_channel, board_voltage_range, i)
            self.current_voltage = self.board_voltage_range * (
                    (i - self.board_ground_voltage) / (self.board_resolution - self.board_ground_voltage))
            loopCount = loopCount + 1
            self.current_step_count = i
            if loopCount % inverse_display_rate == 0:
                self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping up\n" + str(
                    round(self.current_voltage, 3)) + " V")
            time.sleep(self.short_step_delay - (time.time() % self.short_step_delay))  # self synchronizing time delay
            if not self.ramping_up.isSet():
                self.canvas.itemconfigure(self.DAQ_State_text,
                                          text="Current Status: \nRamping paused\n holding at " + str(
                                              round(self.current_voltage, 3)) + " V")
                break
        self.canvas.itemconfigure(self.DAQ_State_text, text="Current Status: \nRamping up complete:\n" + str(
            round(self.current_voltage, 3)) + " V")
        self.begin_ramping_up_button["state"] = "normal"  # enable all the buttons when the ramping ends
        self.ramp_down_button["state"] = "normal"
        self.stop_ramping_button["state"] = "normal"
        self.quick_ramp_down_button["state"] = "normal"
        self.quick_ramp_down_to_button["state"] = "normal"
        self.quick_ramp_up_to_button["state"] = "normal"
        self.initiate_board_button["state"] = "normal"
        sys.exit()

    def quit_program(self):
        self.ramping_up.clear()  #clear all the ramping state variables, join the threads and exit the program
        self.ramping_down.clear()
        self.ramp_up_thread.join()
        sys.exit()


    def selected_device_changed(self, *args):  # @UnusedVariable
        selected_index = self.devices_combobox.current()
        inventory_count = len(self.inventory)

        if self.device_created:
            # Release any previously configured DAQ device from the UL.
            ul.release_daq_device(self.board_num)
            self.device_created = False

        if inventory_count > 0 and selected_index < inventory_count:
            descriptor = self.inventory[selected_index]
            # Update the device ID label
            self.device_id_label["text"] = descriptor.unique_id

            # Create the DAQ device from the descriptor
            # For performance reasons, it is not recommended to create
            # and release the device every time hardware communication is
            # required. Instead, create the device once and do not release
            # it until no additional library calls will be made for this
            # device
            ul.create_daq_device(self.board_num, descriptor)
            self.device_info = DaqDeviceInfo(self.board_num)
            self.device_created = True

    def create_widgets(self): #Frontend of the program, making buttons, input boxes, etc
        '''Create the tkinter UI'''
        main_frame = tk.Frame(self, height=300, width=300)
        main_frame.pack(fill=tk.X, anchor=tk.NW)
        # main_frame.pack_propagate(0)
        # main_frame.place(height=1000, width=500)
        discover_button = tk.Button(main_frame)
        discover_button["text"] = "Discover DAQ Devices"
        discover_button["command"] = self.discover_devices
        discover_button.pack(padx=3, pady=3)

        self.status_label = tk.Label(main_frame)
        self.status_label["text"] = "Status"
        self.status_label.pack(anchor=tk.NW, padx=3, pady=3)

        results_group = tk.LabelFrame(self, height=300, width=200, text="Discovered Devices")
        results_group.pack(fill=tk.X, anchor=tk.NW, padx=3, pady=3)
        results_group.pack_propagate(False)

        self.selected_device_textvar = StringVar()
        self.selected_device_textvar.trace('w', self.selected_device_changed)
        self.devices_combobox = Combobox(
            results_group, textvariable=self.selected_device_textvar)
        self.devices_combobox["state"] = "disabled"
        self.devices_combobox.pack(fill=tk.X, padx=3, pady=3)

        device_id_frame = tk.Frame(results_group)
        device_id_frame.pack(anchor=tk.NW)

        device_id_left_label = tk.Label(device_id_frame)
        device_id_left_label["text"] = "Device Identifier:"
        device_id_left_label.grid(row=0, column=0, sticky=tk.W, padx=3, pady=3)

        self.device_id_label = tk.Label(device_id_frame)
        self.device_id_label.grid(row=0, column=1, sticky=tk.W, padx=3, pady=3)

        self.initiate_board_button = tk.Button(results_group)
        self.initiate_board_button["text"] = "Initiate board"
        self.initiate_board_button["command"] = self.initiate_board
        self.initiate_board_button["state"] = "disabled"
        self.initiate_board_button.pack(padx=3, pady=3)

        button_frame = tk.Frame(self)
        button_frame.pack(fill=tk.X, side=tk.RIGHT, anchor=tk.SE)

        self.quick_ramp_down_button = tk.Button(results_group)
        self.quick_ramp_down_button["text"] = "Quick ramp down to 0V (2s)"
        self.quick_ramp_down_button["command"] = self.begin_quick_ramping_down
        self.quick_ramp_down_button["state"] = "disabled"
        self.quick_ramp_down_button.pack(padx=3, pady=3)

        button_frame = tk.Frame(self)
        button_frame.pack(fill=tk.X, side=tk.RIGHT, anchor=tk.SE)

        self.quick_ramp_up_to_button = tk.Button(results_group)  #standard template for making a button and specify where it goes
        self.quick_ramp_up_to_button["text"] = "Quick Ramp Up to"
        self.quick_ramp_up_to_button["command"] = self.quick_ramp_up_to
        self.quick_ramp_up_to_button["state"] = "disabled"
        self.quick_ramp_up_to_button.place(x=90, y=120)

        button_frame = tk.Frame(self)
        button_frame.pack(fill=tk.X, side=tk.RIGHT, anchor=tk.SE)

        self.begin_ramping_up_button = tk.Button(results_group)
        self.begin_ramping_up_button["text"] = "Begin ramping up"
        self.begin_ramping_up_button["command"] = self.begin_ramping_up
        self.begin_ramping_up_button["state"] = "disabled"
        self.begin_ramping_up_button.place(x=135, y=150)

        button_frame = tk.Frame(self)
        button_frame.pack(fill=tk.X, side=tk.RIGHT, anchor=tk.SE)

        self.stop_ramping_button = tk.Button(results_group)
        self.stop_ramping_button["text"] = "Stop ramping and hold"
        self.stop_ramping_button["command"] = self.stop_ramping
        self.stop_ramping_button["state"] = "disabled"
        self.stop_ramping_button.place(x=125, y=180)

        button_frame = tk.Frame(self)
        button_frame.pack(fill=tk.X, side=tk.RIGHT, anchor=tk.SE)

        self.ramp_down_button = tk.Button(results_group)
        self.ramp_down_button["text"] = "Ramp down"
        self.ramp_down_button["command"] = self.begin_ramping_down
        self.ramp_down_button["state"] = "disabled"
        self.ramp_down_button.place(x=150, y=210)

        button_frame = tk.Frame(self)
        button_frame.pack(fill=tk.X, side=tk.RIGHT, anchor=tk.SE)

        self.quick_ramp_down_to_button = tk.Button(results_group)
        self.quick_ramp_down_to_button["text"] = "Quick ramp down to"
        self.quick_ramp_down_to_button["command"] = self.quick_ramp_down_to
        self.quick_ramp_down_to_button["state"] = "disabled"
        self.quick_ramp_down_to_button.place(x=80, y=240)

        button_frame = tk.Frame(self)
        button_frame.pack(fill=tk.X, side=tk.RIGHT, anchor=tk.SE)

        quit_button = tk.Button(button_frame)
        quit_button["text"] = "Quit"
        quit_button["command"] = sys.exit
        quit_button.grid(row=0, column=1, padx=3, pady=3)

        self.canvas = tk.Canvas(main_frame, width=400, height=210, bg="ivory3") #A canvas for displaying all sorts of text messages and buttons

        self.Start_voltage_input_box = tk.Entry(main_frame)
        self.canvas.create_window(80, 30, window=self.Start_voltage_input_box)
        self.End_voltage_input_box = tk.Entry(main_frame)
        self.canvas.create_window(80, 60, window=self.End_voltage_input_box)
        self.Ramp_rate_input_box = tk.Entry(main_frame)
        self.canvas.create_window(80, 90, window=self.Ramp_rate_input_box)


        self.ramp_down_to_input_box = tk.Entry(results_group, width=4)
        self.ramp_down_to_input_box.place(x=205, y=245)
        self.ramp_up_to_input_box = tk.Entry(results_group, width=4)
        self.ramp_up_to_input_box.place(x=205, y=123)
        self.ramp_down_to_volt_text = tk.Label(results_group, text="Volts")
        self.ramp_down_to_volt_text.place(x=235, y=243)
        self.ramp_up_to_volt_text = tk.Label(results_group, text="Volts")
        self.ramp_up_to_volt_text.place(x=235, y=122)


        self.start_voltage_text = self.canvas.create_text(230, 30, text="Starting Voltage (0-10V)", fill="black",
                                                          font=('Helvetica 11'))
        self.end_voltage_text = self.canvas.create_text(220, 60, text="Final Voltage (0-10V)", fill="black",
                                                        font=('Helvetica 11'))
        self.ramp_rate_voltage_text = self.canvas.create_text(250, 100,
                                                              text="Ramp Rate (V/s, DAQ output)\n(Max 0.1V/s)",
                                                              fill="black",
                                                              font=('Helvetica 11'))
        self.DAQ_Info_text = self.canvas.create_text(80, 140, text=" ", fill="black",
                                                     font=('Helvetica 11'))
        self.DAQ_State_text = self.canvas.create_text(250, 140, text=" ", fill="black",
                                                      font=('Helvetica 11'))
        self.canvas.pack()



if __name__ == "__main__":
    # Start the example
    DAQ_AO1_Ramping(board_resolution, board_voltage_range, board_ramping_analog_channel, ramp_start_voltage,
                    ramp_target_voltage, master=tk.Tk()).mainloop()

#!/usr/bin/env python
'''
Created on July 1, 2019
Author: Albert Go (albertgo@mit.edu)
'''
import rospy
import sensor_msgs.msg as smsg
from ur.msg import Mode, Setpoint, Trajectory, Position, PositionFeedback, PositionResult
from std_msgs.msg import Bool, Int32
from sensor_msgs.msg import JointState
from geometry_msgs.msg import WrenchStamped
import helper as hp
import math
import numpy as np
from statistics import mode, mean

import threading

JOINT_MOVE = 0
ADMITTANCE = 1

class LimbManager:

    def __init__(self):
        self.completed = False
        self.initialized = False
        self.robot_ready = False
        self.command_mode = JOINT_MOVE

        self.current_pos = [0,0,0,0,0,0]
        self.req = []
        self.success = [0,0,0,0,0,0]

        ########################
        #####BASE VARIABLES#####
        ########################

        #These are for GoToJointAngles
        self.base_error_prev = 0
        self.base_final = 0
        self.base_success = False

        #These are for admittance
        self.base = []
        self.base_most = [0,0]
        self.admit_base_final =[]
        self.base_push = 0
        self.base_base = 0
        self.base_prev_base = 0
        self.base_last_diff = 0

        ########################
        ###SHOULDER VARIABLES###
        ########################
        
        #These are for GoToJointAngles
        self.shoulder_error_prev = 0
        self.shoulder_final = 0
        self.shoulder_success = False

        ########################
        ####ELBOW VARIABLES#####
        ########################

        #These are for GoToJointAngles
        self.elbow_error_prev = 0
        self.elbow_final = 0
        self.elbow_success = False

        ########################
        ####WRIST1 VARIABLES####
        ########################
        
        #These are for GoToJointAngles
        self.wrist1_error_prev = 0
        self.wrist1_final = 0
        self.wrist1_success = False

        ########################
        ####WRIST2 VARIABLES####
        ########################

        #These are for GoToJointAngles
        self.wrist2_error_prev = 0
        self.wrist2_final = 0
        self.wrist2_success = False

        #These are for Admittance
        self.wrist2 = []
        self.wrist2_most = [0,0]
        self.admit_wrist2_final =[]
        self.wrist2_push = 0
        self.wrist2_base = 0
        self.wrist2_prev_base = 0
        self.wrist2_last_diff = 0

        ########################
        ####WRIST3 VARIABLES####
        ########################

        #These are for GoToJointAngles
        self.wrist3_error_prev = 0
        self.wrist3_final = 0
        self.wrist3_success = False

        #Subscribers
        rospy.Subscriber('position', Position, self.cb_command)
        rospy.Subscriber('joint_states', JointState, self.cb_joint_states)
        rospy.Subscriber('robot_ready', Bool, self.cb_robot_ready)
        rospy.Subscriber('wrench', WrenchStamped, self.cb_force_control)
        rospy.Subscriber('ur_mode', Int32, self.cb_switch_mode)


        #Publishers
        self.pub_setpoint   = rospy.Publisher('setpoint', Setpoint, queue_size= 1)
        self.pub_posfeedback = rospy.Publisher('position_feedback', PositionFeedback, queue_size=1)
        self.pub_posresult = rospy.Publisher('position_result', PositionResult, queue_size=1)

        rospy.Timer(rospy.Duration(0.0008), self.cb_publish)

    def cb_robot_ready(self, robot_ready_msg):
        '''
        Discovers whether or not if the robot is ready.
        If it is not ready, it staes that the robot is on standby
        '''
        if not self.robot_ready:
            self.initialized = robot_ready_msg.data
            if self.initialized:
                self.robot_ready = True
                self.completed = True
                print "Robot initialized"
                self.success = [1, 1, 1, 1, 1, 1]
        else:
            if not robot_ready_msg.data:
                print "STANDBY mode engaged from program halt"
            else:
                self.robot_ready = True 
                self.completed = True 


    def cb_switch_mode(self, mode):
        self.command_mode = mode.data
        return

    def cb_joint_states(self, data):

        self.current_pos  = data.position

        if len(self.req) > 0: 
            print 'Completing request'

        try:

            base = self.current_pos[0]
            base_req = self.req[0]
            self.move_base(base, base_req)

            shoulder = self.current_pos[1]
            shoulder_req = self.req[1]
            self.move_shoulder(shoulder, shoulder_req)

            elbow = self.current_pos[2]
            elbow_req = self.req[2]
            self.move_elbow(elbow, elbow_req)

            wrist1 = self.current_pos[3]
            wrist1_req = self.req[3]
            self.move_wrist1(wrist1, wrist1_req)

            wrist2 = self.current_pos[4]
            wrist2_req = self.req[4]
            self.move_wrist2(wrist2, wrist2_req)

            wrist3 = self.current_pos[5]
            wrist3_req = self.req[5]
            self.move_wrist3(wrist3, wrist3_req)

        except:
            pass

        if(self.command_mode == JOINT_MOVE):
            if sum(self.success) == 6:
                self.completed = True
                result = PositionResult()

                result.final = self.current_pos
                result.completed = self.completed
                result.initialized = self.initialized
                self.pub_posresult.publish(result)
                self.success = [0,0,0,0,0,0]
                self.req = [] 

            elif self.initialized and len(self.req) == 0:
                self.completed = True
                result = PositionResult()

                result.final = self.current_pos
                result.completed = self.completed
                result.initialized = self.initialized
                self.pub_posresult.publish(result)

            else:
                self.completed = False

                feedback = PositionFeedback()
                feedback.progress = self.current_pos
                self.pub_posfeedback.publish(feedback)

                result = PositionResult()
                result.completed = self.completed
                self.pub_posresult.publish(result)


    def cb_command(self, req):
        self.command_mode = JOINT_MOVE
        self.completed = False
        self.success = [0,0,0,0,0,0]

        try:
            self.req.append(req.base)
            self.req.append(req.shoulder)
            self.req.append(req.elbow)
            self.req.append(req.wrist1)
            self.req.append(req.wrist2)
            self.req.append(req.wrist3)
            self.req.append(req.head)
        except:

            pass

    def move_base(self, cur_pos, req_pos):

        error = req_pos-cur_pos
        derivative = error-self.base_error_prev
        self.base_final = error+derivative

        if self.base_final > 1:
            self.base_final = 1
        elif self.base_final < -1:
            self.base_final = -1
        elif self.base_final > 0 and self.base_final < 0.08:
            self.base_final = 0.08
        elif self.base_final < 0 and self.base_final > -0.08:
            self.base_final = -0.08

        if cur_pos == req_pos:
            self.success[0] = 1

        self.base_error_prev = error

    def move_shoulder(self, cur_pos, req_pos):

        error = req_pos-cur_pos
        derivative = error-self.shoulder_error_prev
        self.shoulder_final = error+derivative

        if self.shoulder_final > 1:
            self.shoulder_final = 1
        elif self.shoulder_final < -1:
            self.shoulder_final = -1
        elif self.shoulder_final > 0 and self.shoulder_final < 0.08:
            self.shoulder_final = 0.08
        elif self.shoulder_final < 0 and self.shoulder_final > -0.08:
            self.shoulder_final = -0.08

        if cur_pos == req_pos:
            self.success[1] = 1

        self.shoulder_error_prev = error

    def move_elbow(self, cur_pos, req_pos):

        error = req_pos-cur_pos
        derivative = error-self.elbow_error_prev
        self.elbow_final = error+derivative

        if self.elbow_final > 1:
            self.elbow_final = 1
        elif self.elbow_final < -1:
            self.elbow_final = -1
        elif self.elbow_final > 0 and self.elbow_final < 0.08:
            self.elbow_final = 0.08
        elif self.elbow_final < 0 and self.elbow_final > -0.08:
            self.elbow_final = -0.08

        if cur_pos == req_pos:
            self.success[2] = 1

        self.elbow_error_prev = error

    def move_wrist1(self, cur_pos, req_pos):

        error = req_pos-cur_pos
        derivative = error-self.wrist1_error_prev
        self.wrist1_final = error+derivative

        if self.wrist1_final > 1:
            self.wrist1_final = 1
        elif self.wrist1_final < -1:
            self.wrist1_final = -1
        elif self.wrist1_final > 0 and self.wrist1_final < 0.08:
            self.wrist1_final = 0.08
        elif self.wrist1_final < 0 and self.wrist1_final > -0.08:
            self.wrist1_final = -0.08

        if cur_pos == req_pos:
            self.success[3] = 1

        self.wrist1_error_prev = error

    def move_wrist2(self, cur_pos, req_pos):

        error = req_pos-cur_pos
        derivative = error-self.wrist2_error_prev
        self.wrist2_final = error+derivative

        if self.wrist2_final > 1:
            self.wrist2_final = 1
        elif self.wrist2_final < -1:
            self.wrist2_final = -1
        elif self.wrist2_final > 0 and self.wrist2_final < 0.08:
            self.wrist2_final = 0.08
        elif self.wrist2_final < 0 and self.wrist2_final > -0.08:
            self.wrist2_final = -0.08

        if cur_pos == req_pos:
            self.success[4] = 1

        self.wrist2_error_prev = error

    def move_wrist3(self, cur_pos, req_pos):

        error = req_pos-cur_pos
        derivative = error-self.wrist3_error_prev
        self.wrist3_final = error+derivative

        if self.wrist3_final > 1:
            self.wrist3_final = 1
        elif self.wrist3_final < -1:
            self.wrist3_final = -1
        elif self.wrist3_final > 0 and self.wrist3_final < 0.08:
            self.wrist3_final = 0.08
        elif self.wrist3_final < 0 and self.wrist3_final > -0.08:
            self.wrist3_final = -0.08

        if cur_pos == req_pos:
            self.success[5] = 1

        self.wrist3_error_prev = error
    
    def cb_force_control(self, data):
        '''
        Detects a change in force, as if someone is pushing on it, and assigns
        a corresponding velocity to specific joints
        '''
        if self.command_mode == ADMITTANCE:
            print 'inside force control for admittance'
            self.completed = False
            base_force = data.wrench.force.y
            wrist2_torque = data.wrench.torque.z

            self.admittance_move_base(base_force)
            self.admittance_move_wrist2(wrist2_torque)
        else: 
            pass

    def admittance_move_base(self, forces):
        '''
        Focuses on creating a controller purely for the base joint
        If this starts messing up, switch back to the baseline being zero and 
        remove the updating baseling part
        '''
        if len(self.base) < 100:
            self.base.append(forces)
        else:
            del self.base[0]
            self.base.append(forces)

        #print(self.base)

        try:
            if len(self.base_most) < 2:
                self.base_most.append(mode(self.base))
            else:
                del self.base_most[0]
                self.base_most.append(mode(self.base))
        except:
            pass

        average = round(mean(self.base), 4)
        #print("AVERAGE:", mean(self.base))
        #print("Diff:", average-self.base_most[0])

        a = True
        if abs(average-self.base_most[0]) > 0.1:
            a = False

        if a == True:
            if self.base_prev_base == 0:
                self.base_base = forces
                self.base_prev_base = self.base_base
            else:
                if abs(forces-self.base_prev_base) < 2:
                    self.base_base = forces
        
        #print "BASE:", self.base_base

        diff = round((average-self.base_base), 3)
        #derivative = diff-self.base_last_diff
        #v = diff-(derivative*10)
        if abs(diff) < 0.5:
            diff = 0

        # self.base_push = round(diff, 2)

        if len(self.admit_base_final) < 50:
            self.admit_base_final.append(diff)
        else:
            del self.admit_base_final[0]
            self.admit_base_final.append(diff)

        derivative = (mean(self.admit_base_final)-self.base_last_diff)*2

        #print derivative

        self.base_push = round(mean(self.admit_base_final), 2)+derivative

        if abs(self.base_push) < 0.9:
            self.base_push = 0

        #print self.base_push
        

        self.base_last_diff = mean(self.admit_base_final)


    def admittance_move_wrist2(self, forces):
        '''
        Focuses on creating a controller purely for the wrist2 joint
        '''
        if len(self.wrist2) < 100:
            self.wrist2.append(forces)
        else:
            del self.wrist2[0]
            self.wrist2.append(forces)

        try:
            #print(mode(self.elbow))
            if len(self.wrist2_most) < 2:
                self.wrist2_most.append(mode(self.wrist2))
            else:
                del self.wrist2_most[0]
                self.wrist2_most.append(mode(self.wrist2))
        except:
            pass

        average = mean(self.wrist2)
        
        a = True
        new_diff = 0
        if abs(self.wrist2_most[0]-average) > 0.01:
            a = False

        if a == True:
            #print('here')
            if self.wrist2_prev_base == 0:
                #print ("HELLO")
                self.wrist2_base = forces
                self.wrist2_prev_base = self.wrist2_base
            else:
                if abs(forces-self.wrist2_prev_base) < 0.16:
                    self.wrist2_base = forces

        #print("BASES:", self.wrist2_base)
        #print("PREVIOUS:", self.elbow_prev_base)
        #print('DIFF:', abs(average-self.wrist2_most[0]))
 
        new_diff = average-self.wrist2_base

        if abs(new_diff) < 0.08:
            new_diff = 0

        #print('DIFF', new_diff)

        if len(self.admit_wrist2_final) < 100:
            self.admit_wrist2_final.append(new_diff)
        else:
            del self.admit_wrist2_final[0]
            self.admit_wrist2_final.append(new_diff)

        derivative = (mean(self.admit_wrist2_final)-self.wrist2_last_diff)*2

        self.wrist2_push = round(mean(self.admit_wrist2_final), 2)+derivative

        if abs(self.wrist2_push) < 0.08:
            self.wrist2_push = 0

        self.wrist2_last_diff = mean(self.admit_wrist2_final)

    def cb_publish(self, event):
        if self.command_mode == JOINT_MOVE:
            if len(self.req) == 0:
                setpoint = [0.0]*6
                setp_msg = Setpoint()
                setp_msg.setpoint = setpoint
                setp_msg.type = Setpoint.TYPE_JOINT_VELOCITY
                self.pub_setpoint.publish(setp_msg)
            else:
                setpoint = [0.0]*6
                setpoint[0] = self.base_final*0.35
                setpoint[1] = self.shoulder_final*0.35
                setpoint[2] = self.elbow_final*0.35
                setpoint[3] = self.wrist1_final*0.35
                setpoint[4] = self.wrist2_final*0.35
                setpoint[5] = self.wrist3_final*0.35
                setp_msg = Setpoint()
                setp_msg.setpoint = setpoint
                setp_msg.type = Setpoint.TYPE_JOINT_VELOCITY
                self.pub_setpoint.publish(setp_msg)
        
        if self.command_mode == ADMITTANCE:
            print 'in admittance publishing'
            setpoint = [0.0]*6

            if self.buttons[2] == 1:
                setpoint[0] = self.base_push*(0.02)

            setpoint[1] = self.current_pos[1] #shoulder
            setpoint[2] = self.current_pos[2] #elbow
            setpoint[3] = self.current_pos[3] #wrist1

            setpoint[4] = -self.wrist2_push*0.8 #wrist 2

            setpoint[5] = self.current_pos[5] #wrist3
            setp_msg = Setpoint()
            setp_msg.setpoint = setpoint
            setp_msg.type = Setpoint.TYPE_JOINT_VELOCITY
            self.pub_setpoint.publish(setp_msg)

if __name__ == '__main__':
    rospy.init_node('limb_manager')
    lm = LimbManager()

    try:              
        rospy.spin()

    except rospy.ROSInterruptException:
        pass
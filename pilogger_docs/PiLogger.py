#!/usr/bin/python3
# -*- coding: utf-8 -*-
# PiLogger Monitor DE, Version 1.3, 2021-11-14
# Coypright 2017,2021 G.Weiß-Engel
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

import smbus
import sys
import os
from datetime import datetime, date, time, timedelta
from tkinter import *
from tkinter import messagebox
from tkinter import ttk
from PiLo_Thermistor import PtcTable, NtcTable

class logger:

  def __init__(self,master):

    global aktP, minP, maxP, avgP, clearstats, PollInter, LoggInter, UnitPulse, FactPulse, TimPuFact
    global TempSense, SlaveAddr, dorecord, dologg, pollnext, loggnext
    global LiconP, LiconR, IconAct, IconNoAct, MeasInter, StatReset, PiLoFont, WorkDir
    global PtcTable, PtcTablePointer, NtcTable, NtcTablePointer
    
    aktP = 0
    minP = 999
    maxP = 0
    avgP = 0
    clearstats = False
    LiconP    = PhotoImage(file=WorkDir+'/Icon_Pause_small.gif')
    LiconR    = PhotoImage(file=WorkDir+'/Icon_Record_small.gif')
    IconAct   = PhotoImage(file=WorkDir+'/Icon_Active_small.gif')
    IconNoAct = PhotoImage(file=WorkDir+'/Icon_NotActive_small.gif')

    try:
      f = open(WorkDir+'/PiLogger_Config.txt','r')
      try:
        helpstrng = f.readline()
        SlaveAddr = helpstrng.replace('\n','')
        MeasInter = float(f.readline())
        TimPuFact = int(f.readline())
        helpstrng = f.readline()
        TempSense = helpstrng.replace('\n','')
        FactPulse = float(f.readline())
        helpstrng = f.readline()
        UnitPulse = helpstrng.replace('\n','')
        PollInter = int(f.readline())
        LoggInter = float(f.readline())
        helpstrng = f.readline()
        StatReset = helpstrng.replace('\n','') == 'True'
      finally:
        f.close
    except IOError:
      SlaveAddr = 0x48
      MeasInter = 1.0
      TimPuFact = 1
      TempSense = 'NTC 10k'
      FactPulse = 0.2
      UnitPulse = 'm/s'
      PollInter = 1000
      LoggInter = 10.0
      StatReset = False
      messagebox.showwarning("Fehler","Fehler beim Lesen von 'PiLogger_Config.txt'")
    pollnext = datetime.now() + timedelta(microseconds=PollInter*1000)
    loggnext = datetime.now()

    dorecord = True
    dologg = True
    with open(WorkDir+'/logdata.csv','a') as datafile:
      line = 'Timestamp;microsec;Mom [°C];Avg [°C];Min [°C];Max [°C];Mom [{0}];Avg [{0}];Min [{0}];Max [{0}];\
Mom [V];Avg [V];Min [V];Max [V];Mom [A];Avg [A];Min [A];Max [A];Mom [W];Avg [W];Min [W];Max [W]'.format(UnitPulse)
      print(line,file=datafile)

    for i in range(len(PtcTable)):
      if PtcTable[i][1] >= 25:
        PtcTablePointer = i
        break
    for i in range(len(NtcTable)):
      if NtcTable[i][1] >= 25:
        NtcTablePointer = i
        break

    self.master=master
    self.view()
    self.poll()

    
  def view (self):

    global LogButt, ActShow

    Label(mainframe,text="Aktuell",font=(PiLoFont,12),anchor=S).grid(column=2,row=1,sticky=S)
    Label(mainframe,text="Mittel", font=(PiLoFont,12),anchor=S).grid(column=3,row=1,sticky=S)
    Label(mainframe,text="Minimum",font=(PiLoFont,12),anchor=S).grid(column=4,row=1,sticky=S)
    Label(mainframe,text="Maximum",font=(PiLoFont,12),anchor=S).grid(column=5,row=1,sticky=S)
    Label(mainframe,text=" ",      font=(PiLoFont,12),anchor=S).grid(column=6,row=1,sticky=S)
    
    Label(mainframe,text="Spannung",   font=(PiLoFont,12)).grid(column=1,row=2,sticky=E)
    Label(mainframe,text="Strom",      font=(PiLoFont,12)).grid(column=1,row=3,sticky=E)
    Label(mainframe,text="Temperatur", font=(PiLoFont,12)).grid(column=1,row=4,sticky=E)
    Label(mainframe,text="Windgeschw.",font=(PiLoFont,12)).grid(column=1,row=5,sticky=E)
    Label(mainframe,text="Leistung",   font=(PiLoFont,12), anchor=E).grid(column=1,row=6,rowspan=2,sticky=E+N+S)
    
    Label(mainframe,textvariable=AktVolt,font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=2,row=2,sticky=EW)
    Label(mainframe,textvariable=AvgVolt,font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=3,row=2,sticky=EW)
    Label(mainframe,textvariable=MinVolt,font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=4,row=2,sticky=EW)
    Label(mainframe,textvariable=MaxVolt,font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=5,row=2,sticky=EW)
    Label(mainframe,textvariable=AktAmp, font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=2,row=3,sticky=EW)
    Label(mainframe,textvariable=AvgAmp, font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=3,row=3,sticky=EW)
    Label(mainframe,textvariable=MinAmp, font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=4,row=3,sticky=EW)
    Label(mainframe,textvariable=MaxAmp, font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=5,row=3,sticky=EW)
    Label(mainframe,textvariable=AktTemp,font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=2,row=4,sticky=EW)
    Label(mainframe,textvariable=AvgTemp,font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=3,row=4,sticky=EW)
    Label(mainframe,textvariable=MinTemp,font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=4,row=4,sticky=EW)
    Label(mainframe,textvariable=MaxTemp,font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=5,row=4,sticky=EW)
    Label(mainframe,textvariable=AktWind,font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=2,row=5,sticky=EW)
    Label(mainframe,textvariable=AvgWind,font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=3,row=5,sticky=EW)
    Label(mainframe,textvariable=MinWind,font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=4,row=5,sticky=EW)
    Label(mainframe,textvariable=MaxWind,font=(PiLoFont,14),relief=RIDGE,bd=6).grid(column=5,row=5,sticky=EW)
    
    Label(mainframe,textvariable=AktWatt,font=(PiLoFont,18),relief=RIDGE,bd=6).grid(column=2,row=6,rowspan=2,sticky=W+E)
    Label(mainframe,textvariable=AvgWatt,font=(PiLoFont,18),relief=RIDGE,bd=6).grid(column=3,row=6,rowspan=2,sticky=W+E)
    Label(mainframe,textvariable=MinWatt,font=(PiLoFont,18),relief=RIDGE,bd=6).grid(column=4,row=6,rowspan=2,sticky=W+E)
    Label(mainframe,textvariable=MaxWatt,font=(PiLoFont,18),relief=RIDGE,bd=6).grid(column=5,row=6,rowspan=2,sticky=W+E)

    ActShow = Label(mainframe,image=IconAct)
    ActShow.grid(column=1,row=9,rowspan=2,sticky=W+E)
    
    Button(mainframe,height=2,text="Einstellungen",command=self.doeinst).grid(column=2,row=9,sticky=W+E)
    LogButt = Button(mainframe,text="Loggen",image=LiconR,compound=RIGHT,command=self.togglerec)
    LogButt.grid(column=3,row=9,sticky=W+E)
    Button(mainframe,height=2,text="Reset",command=self.reset).grid(column=4,row=9,sticky=W+E)
    Button(mainframe,height=2,text="Stop",command=root.quit).grid(column=5,row=9,sticky=W+E)

    for child in mainframe.winfo_children(): child.grid_configure(padx=6,pady=6)


  def poll(self):

    global minP, maxP, aktP, avgP, clearstats, SlaveAddr, TempSense, ActShow, StatReset
    global pollstamp, pollnext, loggnext, dorecord, dologg

    def TempValNtc1(ntv):                                 # NTC 10 kOhm @ 25°C, alt, B25/100=3950
      v = ntv / 65535
      if ntv < 1763:
        w = 999
      elif ntv >= 60680:
        w = -999
      else:
        if ntv < 8424:
          w = 184.196-2068.25*v+16224.33*v*v-50245.929*v*v*v
        elif ntv < 54055:
          w = 111.6473-305.093*v+394.7776*v*v-247.0087*v*v*v
        else:
          w = 11292.757-39846.685*v+47031.885*v*v-18593.11*v*v*v
      return w

# NTC 10 kOhm @ 25°C, B25/85=3928, B25/100=3950
# -55°C...+150°C , 3 Segment Approximation -10°C..+70°C < +/-0.4K
    def TempValNtc2(ntv):
      v = ntv / 65535
      if ntv < 1336:                                      # > +150°C
        w = 999
      elif ntv >= 62218:                                  # < -55°C
        w = -999
      else:
        if ntv < 10523:                                   # > +70°C
          w = -37.9441456*log(v)+2.42698623
        elif ntv < 55328:                                 # > -15°C
          w = +110.012731-291.206862*v+365.866946*v*v-227.609690*v*v*v
        else:                                             # <= -15°C
          w = +46902.5190-159135.977*v+180139.491*v*v-68063.7560*v*v*v
      return w

# NTC 10 kOhm @ 25°C, B25/85=3477, B25/100=3492
# -55°C...+160°C , 3 Segment Approximation -55°C..+100°C < +/-0.6K
    def TempValNtc3(ntv):
      v = ntv / 65535
      if ntv < 1750:                                      # > +160°C
        w = 999
      elif ntv >= 61888:                                  # < -55°C
        w = -999
      else:
        if ntv < 9818:                                    # > +75°C
          w = -45.6395979*log(v)-4.97482473
        elif ntv < 55498:                                 # > -15°C
          w = +126.385782-360.841171*v+471.966445*v*v-290.638213*v*v*v
        else:                                             # <= -15°C
          w = +25437.9192-87503.0502*v+100504.490*v*v-38580.0352*v*v*v
      return w

# NTC per Tabelle
    def TempValNtc4(ntv):
      global NtcTable, NtcTablePointer
      if ntv < NtcTable[0][0]:
        w = -999
      elif ntv > NtcTable[len(NtcTable)-1][0]:
        w = 999
      else:
        if NtcTable[NtcTablePointer][0] < ntv:
          while NtcTable[NtcTablePointer][0] < ntv:
            NtcTablePointer += 1
        elif NtcTable[NtcTablePointer][0] > ntv:
          while NtcTable[NtcTablePointer][0] > ntv:
            NtcTablePointer -= 1
        if NtcTable[NtcTablePointer][0] == ntv:           # Treffer!
          w = NtcTable[NtcTablePointer][1]
        else:
          if NtcTable[NtcTablePointer][0] < ntv:
            i1=NtcTablePointer
            i2=NtcTablePointer+1
          else:
            i1=NtcTablePointer-1
            i2=NtcTablePointer
          x1=NtcTable[i1][0]
          x2=NtcTable[i2][0]
          y1=NtcTable[i1][1]
          y2=NtcTable[i2][1]
          w = y1+(y2-y1)*(ntv-x1)/(x2-x1)
      return w

# PTC Pt1000, 1000 Ohm @ 0°C
# -60°C...+290°C Approximation -55°C...+280°C < +/-0,02K
    def TempValPtc1(ptv):
      v = ptv / 65535
      if ptv < 25498:
        w = -999
      elif ptv < 62224:
        w = -249.992835+453.078834*v+62.3193206*v*v+63.2008663*v*v*v
      else:
        w = 999
      return w

# PTC KTY81-110, 1000 Ohm @ 25°C
# -55°C...+140°C Approximation < +/-0,4K
    def TempValPtc2(ptv):
      v = ptv / 65535
      if ptv < 16016:
        w = -999
      elif ptv < 62189:
        w = -175.628285+580.82185*v-437.516532*v*v+189.749364*v*v*v
      else:
        w = 999
      return w

# PTC per Tabelle
    def TempValPtc3(ptv):
      global PtcTable, PtcTablePointer
      if ptv < PtcTable[0][0]:
        w = -999
      elif ptv > PtcTable[len(PtcTable)-1][0]:
        w = 999
      else:
        if PtcTable[PtcTablePointer][0] < ptv:
          while PtcTable[PtcTablePointer][0] < ptv:
            PtcTablePointer += 1
        elif PtcTable[PtcTablePointer][0] > ptv:
          while PtcTable[PtcTablePointer][0] > ptv:
            PtcTablePointer -= 1
        if PtcTable[PtcTablePointer][0] == ptv:           # Treffer!
          w = PtcTable[PtcTablePointer][1]
        else:
          if PtcTable[PtcTablePointer][0] < ptv:
            i1=PtcTablePointer
            i2=PtcTablePointer+1
          else:
            i1=PtcTablePointer-1
            i2=PtcTablePointer
          x1=PtcTable[i1][0]
          x2=PtcTable[i2][0]
          y1=PtcTable[i1][1]
          y2=PtcTable[i2][1]
          w = y1+(y2-y1)*(ptv-x1)/(x2-x1)
      return w

    def TempVal(raw):
      if TempSense == 'NTC 10k':                          # rückwärts kompatibel
        tval = TempValNtc1(raw)
      elif TempSense == 'NTC 10k B3928':
        tval = TempValNtc2(raw)
      elif TempSense == 'NTC 10k B3477':
        tval = TempValNtc3(raw)
      elif TempSense == 'NTC Tabelle':
        tval = TempValNtc4(raw)
      elif TempSense == 'PT1000':                         # rückwärts kompatibel
        tval = TempValPtc1(raw)
      elif TempSense == 'PTC Pt1000':
        tval = TempValPtc1(raw)
      elif TempSense == 'PTC KTY81-110':
        tval = TempValPtc2(raw)
      elif TempSense == 'PTC Tabelle':
        tval = TempValPtc3(raw)
      else:
        tval = '-UTS-'                                    # Fehler: unbekannter Temp-Sensor
      return tval


    try:
      address = int(SlaveAddr)
    except ValueError:
      try:
        address = int(SlaveAddr,16)
      except ValueError:
        address = 0x48

    pilogger = smbus.SMBus(1)

    tp = pollnext - timedelta(microseconds=330)    # Vorhalt für Mindestlaufzeit - ohne IDLE Shell !
    while datetime.now() < tp:
      pass
    pollstamp = datetime.now()

    try:
      ant = pilogger.read_i2c_block_data(address,0x70)
    except IOError:
      messagebox.showerror("Fehler","Fehler I²C Bus bei BlockRead 1")
      print("I²C Fehler @ Blockread\n")
      exit(-1)
    
    try:
      ret = pilogger.read_i2c_block_data(address,0x80)
    except IOError:
      messagebox.showerror("Fehler","Fehler I²C Bus bei BlockRead 2")
      print("I²C Fehler @ Blockread\n")
      exit(-1)
      
    print(pollstamp)
    pollnext = pollnext + timedelta(microseconds=PollInter*1000)

    if loggnext <= pollstamp:
      loggnext = loggnext + timedelta(seconds=LoggInter)
      if dorecord:
        dologg = True

    if StatReset and dologg:
      clearstats = True
      
    if clearstats == True:                        # kann auch manuell gesetzt werden
      try:
        pilogger.write_byte(address,0x78)
      except IOError:
        messagebox.showerror("Fehler","Fehler I²C Bus bei Write-Byte")
        print("I²C Fehler @ WriteByte\n")
        exit(-1)
      try:
        pilogger.write_byte(address,0x88)
      except IOError:
        messagebox.showerror("Fehler","Fehler I²C Bus bei Write-Byte")
        print("I²C Fehler @ WriteByte\n")
        exit(-1)
      clearstats = False
        
    if dologg:
      line = str(pollstamp)
      line=line.replace('.',';')
        
    vl = []
    for i in range (16):
      x=ret.pop(0)
      y=ret.pop(0)
      z=y*256+x
      if i in range (12,16):                      # Stromwerte +/-
        if z >= 32768:
          z = z - 65536
      if i == 3:                                  # Wenn NTC dann Max Temp <> Min Temp
        if TempSense[0] == 'N':
          vl.insert(2,z)
        else:
          vl.append(z)
      else:
        vl.append(z)
      
    for i in range (16):
      z=vl.pop(0)
      if i < 4:                                   # Temperatur
        w = TempVal(z)
        if w != '-UTS-':
          out = '{0:-7.2f} °C'.format(w)
        else:
          out = ' -UTS- '
          messagebox.showerror("Fehler","Unbekannter Temp-Sensor")
          print("Unknown Temp-Sensor\n")
          exit(-2)
        if dologg:
          line = line+';'+'{0:-7.2f}'.format(w)
      elif i < 8:                                 # Pulse
        z = z * FactPulse / MeasInter / TimPuFact
        out = '{0:-6.1f} {1}'.format(z,UnitPulse)
        if dologg:
            line = line+';'+'{0:-6.1f}'.format(z)
      elif i < 12:                                # Volt
        z = z / 1092.267
        out = '{0:-8.3f} V'.format(z)
        if dologg:
          line = line+';'+'{0:-8.3f}'.format(z)
      else:                                       # Amp
        z = z / 2141.634
        out = '{0:-8.3f} A'.format(z)
        if dologg:
          line = line+';'+'{0:-8.3f}'.format(z)

      if i == 0:
        AktTemp.set(out.replace(".",","))
      if i == 1:
        AvgTemp.set(out.replace(".",","))
      if i == 2:
        MinTemp.set(out.replace(".",","))
      if i == 3:
        MaxTemp.set(out.replace(".",","))
      if i == 4:
        AktWind.set(out.replace(".",","))
      if i == 5:
        AvgWind.set(out.replace(".",","))
      if i == 6:
        MinWind.set(out.replace(".",","))
      if i == 7:
        MaxWind.set(out.replace(".",","))
      if i == 8:
        AktVolt.set(out.replace(".",","))
      if i == 9:
        AvgVolt.set(out.replace(".",","))
      if i == 10:
        MinVolt.set(out.replace(".",","))
      if i == 11:
        MaxVolt.set(out.replace(".",","))
      if i == 12:
        AktAmp.set(out.replace(".",","))
      if i == 13:
        AvgAmp.set(out.replace(".",","))
      if i == 14:
        MinAmp.set(out.replace(".",","))
      if i == 15:
        MaxAmp.set(out.replace(".",","))

    karl = ant.pop(0)
    lisa = ant.pop(0)
    maxi = ant.pop(0)
    nina = ant.pop(0)

    aktP = karl + lisa*256 + (maxi + nina*256)*65536
    if aktP > 2147483647:
      aktP = aktP - 4294967295
    aktP = aktP / 2147483648 * 918
    out = '{0:-8.3f} W'.format(aktP)
    if dologg:
      line = line+';'+'{0:-8.3f}'.format(aktP)
    AktWatt.set(out.replace(".",","))

    karl = ant.pop(0)
    lisa = ant.pop(0)
    maxi = ant.pop(0)
    nina = ant.pop(0)

    avgP = karl + lisa*256 + (maxi + nina*256)*65536
    if avgP > 2147483647:
      avgP = avgP - 4294967295
    avgP = avgP / 2147483648 * 918
    out = '{0:-8.3f} W'.format(avgP)
    if dologg:
      line = line+';'+'{0:-8.3f}'.format(avgP)
    AvgWatt.set(out.replace(".",","))

    karl = ant.pop(0)
    lisa = ant.pop(0)
    maxi = ant.pop(0)
    nina = ant.pop(0)

    minP = karl + lisa*256 + (maxi + nina*256)*65536
    if minP > 2147483647:
      minP = minP - 4294967295
    minP = minP / 2147483648 * 918
    out = '{0:-8.3f} W'.format(minP)
    if dologg:
      line = line+';'+'{0:-8.3f}'.format(minP)
    MinWatt.set(out.replace(".",","))

    karl = ant.pop(0)
    lisa = ant.pop(0)
    maxi = ant.pop(0)
    nina = ant.pop(0)

    maxP = karl + lisa*256 + (maxi + nina*256)*65536
    if maxP > 2147483647:
      maxP = maxP - 4294967295
    maxP = maxP / 2147483648 * 918
    out = '{0:-8.3f} W'.format(maxP)
    if dologg:
      line = line+';'+'{0:-8.3f}'.format(maxP)
    MaxWatt.set(out.replace(".",","))

    if dologg:
      with open('logdata.csv','a') as datafile:
        line=line.replace('.',',')
        print(line,file=datafile)
      dologg = False
      ActShow.configure(image=IconAct)
    else:
      ActShow.configure(image=IconNoAct)

    self.master.after(PollInter-80,self.poll)   # ca. 80 msec vorher zurückkommen


  def togglerec(self):

    global dorecord, dologg, LiconP, LiconR, LogButt, loggnext, WorkDir

    if dorecord:
      dorecord = False
      dologg = False
      LogButt.configure(image=LiconP)
    else:
      dorecord = True
      dologg = True
      LogButt.configure(image=LiconR)
      loggnext = datetime.now()
      with open(WorkDir+'/logdata.csv','a') as datafile:
        line = 'Timestamp;microsec;Mom [°C];Avg [°C];Min [°C];Max [°C];Mom [{0}];Avg [{0}];Min [{0}];Max [{0}];\
Mom [V];Avg [V];Min [V];Max [V];Mom [A];Avg [A];Min [A];Max [A];Mom [W];Avg [W];Min [W];Max [W]'.format(UnitPulse)
        print(line,file=datafile)
      

  def reset(self):

    global clearstats

    clearstats = True


  def doeinst(self):

    sub = einstell(root)

    
class einstell(Toplevel):

  def __init__(self, parent, title = "PiLogger Einstellungen"):

    global SlavAddr, TimeBase, TimFacLo, TimFacHi, TimInter, AvgFactr, TimPuFac, AvgFaDec
    global newSlavAddr, newTimeBase, newTimFacLo, newTimFacHi, newTimInter, newAvgFactr, newTimPuFac, newAvgFaDec
    global TempSens, FacPulse, UnitPuls, PollTime, LogInter, FactPulse, UnitPulse, PollInter, LoggInter
    global StatReset, TempSense, SlaveAddr, TimPuFact, PiLoInter, PiLoFont

        
    SlavAddr = StringVar()
    TimeBase = StringVar()
    TimFacLo = StringVar()
    TimFacHi = StringVar()
    TimInter = StringVar()
    AvgFactr = StringVar()
    TimPuFac = StringVar()
    AvgFaDec = StringVar()

    newSlavAddr = StringVar()
    newTimeBase = StringVar()
    newTimFacLo = StringVar()
    newTimFacHi = StringVar()
    newTimInter = StringVar()
    newAvgFactr = StringVar()
    newTimPuFac = StringVar()
    newAvgFaDec = StringVar()

    TempSens = StringVar()
    FacPulse = StringVar()
    UnitPuls = StringVar()
    PollTime = StringVar()
    LogInter = StringVar()
    self.StatAuto = BooleanVar()

    TempSens.set(TempSense)
    FacPulse.set(FactPulse)
    UnitPuls.set(UnitPulse)
    PollTime.set(PollInter)
    LogInter.set(LoggInter)
    self.StatAuto.set(StatReset)
    SlavAddr.set(SlaveAddr)
    TimPuFac.set(TimPuFact)
    newSlavAddr.set(SlaveAddr)
    newTimPuFac.set(TimPuFact)

    Toplevel.__init__(self, parent)
    self.transient(parent)
    self.title(title)
    self.parent = parent
    self.result = None
    body = Frame(self)
    self.initial_focus = self.body(body)
    body.pack(padx=5, pady=5)
    self.buttonline(body)
    self.grab_set()
    self.focus_set()
    self.protocol("WM_DELETE_WINDOW", self.cancel)
    self.geometry("+%d+%d" % (parent.winfo_rootx()+50,parent.winfo_rooty()+200))
    self.initial_focus.focus_set()
    self.wait_window(self)


  def body(self, master):

    self.readlogger()
    
    Label(master,text="PiLogger Einstellungen",font=(PiLoFont,14),anchor=S).grid(column=0,columnspan=3,row=0,sticky=S)

    Label(master,text="Aktuell",        font=(PiLoFont,12), anchor=S).grid(column=1, row=1, sticky=S)
    Label(master,text="neuer Wert ",    font=(PiLoFont,12), anchor=S).grid(column=3, row=1, sticky=S)
    Label(master,text="sec",            font=(PiLoFont,12), anchor=S).grid(column=2, row=6, sticky=W)
    Label(master,textvariable=AvgFaDec, font=(PiLoFont,12), anchor=S).grid(column=2, row=8, sticky=W)
    Label(master,text="dez",            font=(PiLoFont,12), anchor=S).grid(column=2, row=7, sticky=W)

    Label(master,text="I²C Slave Address:",font=(PiLoFont,12)).grid(column=0, row=2, sticky=E)
    Label(master,text="Zeitbasis:",        font=(PiLoFont,12)).grid(column=0, row=3, sticky=E)
    Label(master,text="Zeit Faktor  Low:", font=(PiLoFont,12)).grid(column=0, row=4, sticky=E)
    Label(master,text="Zeit Faktor High:", font=(PiLoFont,12)).grid(column=0, row=5, sticky=E)
    Label(master,text="-> Messintervall:", font=(PiLoFont,12)).grid(column=0, row=6, sticky=E)
    Label(master,text="Puls Mess Faktor:", font=(PiLoFont,12)).grid(column=0, row=7, sticky=E)
    Label(master,text="Mittelungsfaktor:", font=(PiLoFont,12)).grid(column=0, row=8, sticky=E)
    Label(master,text="Amp Korrektur:",    font=(PiLoFont,12)).grid(column=0, row=9, sticky=E)

    Label(master,textvariable=SlavAddr,font=(PiLoFont,12),relief=RIDGE,bd=6).grid(column=1,row=2,sticky=EW)
    Label(master,textvariable=TimeBase,font=(PiLoFont,12),relief=RIDGE,bd=6).grid(column=1,row=3,sticky=EW)
    Label(master,textvariable=TimFacLo,font=(PiLoFont,12),relief=RIDGE,bd=6).grid(column=1,row=4,sticky=EW)
    Label(master,textvariable=TimFacHi,font=(PiLoFont,12),relief=RIDGE,bd=6).grid(column=1,row=5,sticky=EW)
    Label(master,textvariable=TimInter,font=(PiLoFont,12),relief=None, bd=6).grid(column=1,row=6,sticky=EW)
    Label(master,textvariable=TimPuFac,font=(PiLoFont,12),relief=RIDGE,bd=6).grid(column=1,row=7,sticky=EW)
    Label(master,textvariable=AvgFactr,font=(PiLoFont,12),relief=RIDGE,bd=6).grid(column=1,row=8,sticky=EW)
    
    Label(master,text="\n\n\n\n\n\n\n\n\n\n\n\n\n\n", font=(PiLoFont,12),relief=RAISED,bd=4).grid(column=4,row=0,rowspan=11,sticky=EW)

    Label(master,text="RasPi Einstellungen",font=(PiLoFont,14),anchor=S).grid(column=5,columnspan=2,row=0,sticky=S)

    Label(master,text="Aktuell",   font=(PiLoFont,12),anchor=S).grid(column=6,row=1,sticky=S)
    Label(master,text="Temp Fühler Typ:",   font=(PiLoFont,12)).grid(column=5,row=2,sticky=E)
    Label(master,text="Faktor Pulse:",      font=(PiLoFont,12)).grid(column=5,row=3,sticky=E)
    Label(master,text="Einheit Pulse:",     font=(PiLoFont,12)).grid(column=5,row=4,sticky=E)
    Label(master,text="Abfrage Delay:",     font=(PiLoFont,12)).grid(column=5,row=5,sticky=E)
    Label(master,text="Logger Intervall:",  font=(PiLoFont,12)).grid(column=5,row=6,sticky=E)
    Label(master,text=" AutoReset mit Log:",font=(PiLoFont,12)).grid(column=5,row=7,sticky=E)

    Label(master,text="msec",font=(PiLoFont,12),anchor=W).grid(column=7,row=5,sticky=EW)
    Label(master,text="sec", font=(PiLoFont,12),anchor=W).grid(column=7,row=6,sticky=EW)

    Label(master,text=" ",font=(PiLoFont,6)).grid(column=0,row=10,columnspan=8,sticky=EW)

    self.e1  = Entry(master,textvariable=newSlavAddr,font=(PiLoFont,12),width=5,justify=CENTER)
    self.e1.icursor(END)
    self.e1.grid (column=3,row=2)

    self.cb1 = (ttk.Combobox(master,textvariable=newTimeBase,
                values=(0,1,2,3),state='readonly',font=(PiLoFont,12),width=5,justify=CENTER))
    self.cb1.grid(column=3,row=3)

    self.e2  = Entry(master,textvariable=newTimFacLo,font=(PiLoFont,12),width=5,justify=CENTER)
    self.e2.icursor(END)
    self.e2.grid (column=3,row=4)

    self.e3  = Entry(master,textvariable=newTimFacHi,font=(PiLoFont,12),width=5,justify=CENTER)
    self.e3.icursor(END)
    self.e3.grid (column=3,row=5)

    self.cb2 = (ttk.Combobox(master,textvariable=newAvgFactr,
                values=(0,1,2,3,4,5,6,7),state='readonly',font=(PiLoFont,12),width=5,justify=CENTER))
    self.cb2.grid(column=3,row=8)

    self.e4  = Entry(master,textvariable=newTimPuFac,font=(PiLoFont,12),width=5,justify=CENTER)
    self.e4.icursor(END)
    self.e4.grid (column=3,row=7)

    self.cb3 = (ttk.Combobox(master,textvariable=TempSens,
                values=("NTC 10k","NTC 10k B3928","NTC 10k B3477","NTC Tabelle","PT1000","PTC Pt1000","PTC KTY81-110","PTC Tabelle"),
                state='readonly',font=(PiLoFont,12),width=10,justify=CENTER))
    self.cb3.grid(column=6,row=2)
        
    self.e5  = Entry(master,textvariable=FacPulse,font=(PiLoFont,12),width=5,justify=CENTER)
    self.e5.icursor(END)
    self.e5.grid (column=6,row=3)

    self.e6  = Entry(master,textvariable=UnitPuls,font=(PiLoFont,12),width=5,justify=CENTER)
    self.e6.icursor(END)
    self.e6.grid (column=6,row=4)

    self.e7  = Entry(master,textvariable=PollTime,font=(PiLoFont,12),width=5,justify=CENTER)
    self.e7.icursor(END)
    self.e7.grid (column=6,row=5)

    self.e8  = Entry(master,textvariable=LogInter,font=(PiLoFont,12),width=5,justify=CENTER)
    self.e8.icursor(END)
    self.e8.grid (column=6,row=6)

    self.cb4 = Checkbutton(master,variable=self.StatAuto,onvalue=True,offvalue=False,height=2,command=self.togglecheck)
    self.cb4.grid(column=6,row=7)

    return self.e2    # initial focus


  def togglecheck(self):

    global StatReset
    
    StatReset = bool(self.StatAuto.get())
    
    
  def buttonline(self,master):
    
    Button(master,text="AmpZero",     width=8,command=self.AmpZero       ).grid(column=1,row=9,sticky=EW)
    Button(master,text="Werkseinst.", width=8,command=self.factorydefault).grid(column=0,row=11,sticky=EW)
    Button(master,text="* Flash *",   width=8,command=self.flashlogger   ).grid(column=1,row=11,sticky=EW)
    Button(master,text="Senden",      width=8,command=self.writelogger   ).grid(column=3,row=11,sticky=EW)
    Button(master,text="Cancel",      width=6,command=self.cancel        ).grid(column=6,row=11,sticky=EW)
    Button(master,text="OK",          width=6,command=self.ok,default=ACTIVE).grid(column=7,row=11,sticky=EW)
    
    self.bind("<Return>",self.ok)
    self.bind("<Escape>",self.cancel)
        
    
  def ok(self, event=None):

    if not self.validate():
      self.initial_focus.focus_set()    # Fokus zurück an master
      return
    self.withdraw()
    self.update_idletasks()
    self.apply()
    self.cancel()


  def flashlogger(self):
    
    try:
      address = int(SlaveAddr)
    except ValueError:
      try:
        address = int(SlaveAddr,16)
      except ValueError:
        address = 0x48
        
    pilogger = smbus.SMBus(1)
        
    basereg = 0x0F
    databyte = 0x55
    try:
      pilogger.write_byte_data(address, basereg, databyte)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim Flash-Befehl")
      print("I2C Fehler\n")
    self.cancel()


  def factorydefault(self):

    try:
      address = int(SlaveAddr)
    except ValueError:
      try:
        address = int(SlaveAddr,16)
      except ValueError:
        address = 0x48
        
    pilogger = smbus.SMBus(1)
        
    basereg = 0x0D
    databyte = 0xAB
    try:
      pilogger.write_byte_data(address, basereg, databyte)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim Default-Befehl")
      print("I2C Fehler\n")
    self.cancel()

    
  def readlogger(self):

    global PiLoInter
  
    try:
      address = int(SlaveAddr)
    except ValueError:
      try:
        address = int(SlaveAddr,16)
      except ValueError:
        address = 0x48
        
    pilogger = smbus.SMBus(1)
    
    try:
      ret = pilogger.read_byte_data(address,0x11)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim ConfigLesen")
      print("I2C Fehler\n")
      exit(-1)
    SlavAddr.set("0x{0:02X}".format(ret))
    
    try:
      ret = pilogger.read_byte_data(address,0x12)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim ConfigLesen")
      print("I2C Fehler\n")
      exit(-1)
    TiBa = ret
    TimeBase.set(str(ret))
        
    try:
      ret = pilogger.read_byte_data(address,0x13)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim ConfigLesen")
      print("I2C Fehler\n")
      exit(-1)
    FaLo = ret
    TimFacLo.set("0x{0:02X}".format(ret))
    
    try:
      ret = pilogger.read_byte_data(address,0x14)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim ConfigLesen")
      print("I2C Fehler\n")
      exit(-1)
    FaHi = ret
    TimFacHi.set("0x{0:02X}".format(ret))
    
    try:
      ret = pilogger.read_byte_data(address,0x15)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim ConfigLesen")
      print("I2C Fehler\n")
      exit(-1)
    if ret > 7:
        AvgFaDec.set("error")
        AvgFactr.set("error")
    else:
        AvFa = 2 ** ret
        AvgFaDec.set("1/{0:<3d}".format(AvFa))
        AvgFactr.set("{0:1d}".format(ret))

    try:
      ret = pilogger.read_byte_data(address,0x16)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim ConfigLesen")
      print("I2C Fehler\n")
      exit(-1)
    TimPuFac.set("{0:<2d}".format(ret))
    
    PiLoInter = 0.0
    if TiBa == 0:
      PiLoInter = 1 * (FaHi * 256 + FaLo)
    elif TiBa == 1:
      PiLoInter = 0.25 * (FaHi * 256 + FaLo)
    elif TiBa == 2:
      PiLoInter = 0.015625 * (FaHi * 256 + FaLo)
    elif TiBa == 3:
      PiLoInter = 0.001953125 * (FaHi * 256 + FaLo)
    TimInter.set("{0:5.4f}".format(PiLoInter))
    MeasInter = PiLoInter
    
    newSlavAddr.set(SlavAddr.get())
    newTimeBase.set(TimeBase.get())
    newTimFacLo.set(TimFacLo.get())
    newTimFacHi.set(TimFacHi.get())
    newTimInter.set(TimInter.get())
    newAvgFactr.set(AvgFactr.get())
    newAvgFaDec.set(AvgFaDec.get())
    newTimPuFac.set(TimPuFac.get())


  def AmpZero(self):
    
    try:
      address = int(SlaveAddr)
    except ValueError:
      try:
        address = int(SlaveAddr,16)
      except ValueError:
        address = 0x48
        
    pilogger = smbus.SMBus(1)
        
    basereg = 0x07
    databyte = 0x44
    try:
      pilogger.write_byte_data(address, basereg, databyte)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim AmpZero-Befehl")
      print("I2C Fehler\n")


  def writelogger(self):

    try:
      address = int(SlaveAddr)
    except ValueError:
      try:
        address = int(SlaveAddr,16)
      except ValueError:
        address = 0x48
        
    pilogger = smbus.SMBus(1)
        
    basereg = 0x01
    databyte = int(self.e1.get(),16)
    try:
      pilogger.write_byte_data(address, basereg, databyte)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim ConfigSchreiben")
      print("I2C Fehler\n")
      exit(-1)

    basereg = 0x02
    databyte = int(self.cb1.get(),16)
    try:
      pilogger.write_byte_data(address, basereg, databyte)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim ConfigSchreiben")
      print("I2C Fehler\n")
      exit(-1)

    basereg = 0x03
    databyte = int(self.e2.get(),16)
    try:
      pilogger.write_byte_data(address, basereg, databyte)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim ConfigSchreiben")
      print("I2C Fehler\n")
      exit(-1)

    basereg = 0x04
    databyte = int(self.e3.get(),16)
    try:
      pilogger.write_byte_data(address, basereg, databyte)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim ConfigSchreiben")
      print("I2C Fehler\n")
      exit(-1)

    basereg = 0x05
    databyte = int(self.cb2.get(),16)
    try:
      pilogger.write_byte_data(address, basereg, databyte)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim ConfigSchreiben")
      print("I2C Fehler\n")
      exit(-1)

    basereg = 0x06
    databyte = int(self.e4.get(),10)        # Hier Dezimalzahl in der Eingabe !
    try:
      pilogger.write_byte_data(address, basereg, databyte)
    except IOError:
      messagebox.showerror("Error on I²C access","Fehler I²C Bus beim ConfigSchreiben")
      print("I2C Fehler\n")
      exit(-1)

    self.readlogger()
    

  def cancel(self, event=None):

    self.parent.focus_set()
    self.destroy()


  def validate(self):
    
    return 1

  
  def apply(self):

    global FactPulse, UnitPulse, PollInter, LoggInter, TempSense, SlaveAddr, PiLoInter, MeasInter, StatReset
    global TimPuFact, WorkDir

    SlaveAddr = self.e1.get()
    if PiLoInter:
      if PiLoInter != MeasInter:
        MeasInter = PiLoInter
    TimPuFact = int(float(self.e4.get()))
    TempSense = self.cb3.get()
    FactPulse = float(self.e5.get())
    UnitPulse = self.e6.get()
    PollInter = int(float(self.e7.get()))
    LoggInter = float(self.e8.get())

    try:
      f = open(WorkDir+'/PiLogger_Config.txt','w')
      try:
        f.write(str(SlaveAddr)+'\n')
        f.write(str(MeasInter)+'\n')
        f.write(str(TimPuFact)+'\n')
        f.write(str(TempSense)+'\n')
        f.write(str(FactPulse)+'\n')
        f.write(str(UnitPulse)+'\n')
        f.write(str(PollInter)+'\n')
        f.write(str(LoggInter)+'\n')
        f.write(str(StatReset)+'\n')
      finally:
        f.close()
    except IOError:
      messagebox.showwarning("Fehler","Fehler beim Speichern der Einstellungen.")
    messagebox.showinfo("Info","Einstellungen gespeichert.",parent=mainframe)


root = Tk()
root.title("PiLogger Monitor")
WorkDir = os.path.dirname(os.path.realpath(__file__))
os.chdir(WorkDir)
img=PhotoImage(file=WorkDir+'/Logo_PiLogger_Icon.png')
root.iconphoto(True,img)
PiLoFont = "Noto Mono"

AktVolt = StringVar()
AvgVolt = StringVar()
MinVolt = StringVar()
MaxVolt = StringVar()
AktAmp  = StringVar()
AvgAmp  = StringVar()
MinAmp  = StringVar()
MaxAmp  = StringVar()
AktTemp = StringVar()
AvgTemp = StringVar()
MinTemp = StringVar()
MaxTemp = StringVar()
AktWind = StringVar()
AvgWind = StringVar()
MinWind = StringVar()
MaxWind = StringVar()
AktWatt = StringVar()
AvgWatt = StringVar()
MinWatt = StringVar()
MaxWatt = StringVar()

mainframe = Frame(root)
mainframe.grid(column=0, row=0, sticky=(N, W, E, S))
mainframe.columnconfigure(0, weight=1)
mainframe.rowconfigure(0, weight=1)

app = logger(root)

root.mainloop()
root.destroy()

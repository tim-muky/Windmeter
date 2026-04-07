#!/usr/bin/python3
# -*- coding: utf-8 -*-
# PiLogger Web-Monitor DE, Version 0.18 beta, 2024-10-22
# Coypright 2018,2024 G.Weiß-Engel
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
from gpiozero import Button
import os
import bottle
import json
from datetime import datetime, date, time, timedelta
import threading
import locale
from shutil import copyfile
from time import sleep
from math import log
from PiLo_Thermistor import PtcTable, NtcTable

I2Cadr = 72												# muss Integer sein !
MeasInter = 2.0
LogFactor = 30
StatReset = True
TimPuFact = 5.0
UnitPulse1 = 'km/h'
FactPulse1 = 1.44
UnitPulse2 = 'm/s'
FactPulse2 = 0.4
TempSense = 'NTC 10k B3928'
LogSplit = True
LogLines = 1440
LineCount = 0
MeasCount = 0
WindCount = 0
TimeCount = 0.0
EnerCntB = 0.0
EnerCntE = 0.0
EnerCntV = 0.0
TimeCntTag = 0.0
EnerCntTagB = 0.0
EnerCntTagE = 0.0
EnerCntTagV = 0.0
DoVAcorr = True
CorrVoltOffset = 0.0
CorrVoltFactor = 1.0
CorrAmpOffset = 0.0
CorrAmpFactor = 1.0
CorrNtcOffset = 0.0
CorrNtcFactor = 1.0
CorrPtcOffset = 0.0
CorrPtcFactor = 1.0
WindAkt1 = 0.0
WindAkt2 = 0.0
InitWindAvg = False

ERRORLOG = True											# bei Bedarf abschaltbar
DEBUG = False											# sollte normal ausgeschaltet sein!
bottle.debug(False)										# sollte normal ausgeschaltet sein!
bottle.TEMPLATE_PATH.insert(0, os.path.join(os.path.dirname(__file__), 'templates'))

def printD(message):
	if DEBUG:
		print(message)

def printE(message):
	if ERRORLOG:
		with open(WorkDir+'/PiLo-Error.log','a') as datafile:
			print(message,file=datafile)

def writeConfig():
	global I2Cadr, MeasInter, LogFactor, StatReset, TimPuFact, UnitPulse1, FactPulse1
	global UnitPulse2, FactPulse2, TempSense, LogSplit, LogLines
	global DoVAcorr, CorrVoltOffset, CorrVoltFactor, CorrAmpOffset, CorrAmpFactor
	global CorrNtcOffset, CorrNtcFactor, CorrPtcOffset, CorrPtcFactor
	data = {}
	data["SlaveAddr"] = I2Cadr
	data["MeasInter"] = MeasInter
	data["LogFactor"] = LogFactor
	data["StatReset"] = StatReset
	data["TimPuFact"] = TimPuFact
	data["UnitPulse1"] = UnitPulse1
	data["FactPulse1"] = FactPulse1
	data["UnitPulse2"] = UnitPulse2
	data["FactPulse2"] = FactPulse2
	data["TempSense"] = TempSense
	data["LogSplit"] = LogSplit
	data["LogLines"] = LogLines
	data["DoVAcorr"] = DoVAcorr
	data["CorrVoltOffset"] = CorrVoltOffset
	data["CorrVoltFactor"] = CorrVoltFactor
	data["CorrAmpOffset"] = CorrAmpOffset
	data["CorrAmpFactor"] = CorrAmpFactor
	data["CorrNtcOffset"] = CorrNtcOffset
	data["CorrNtcFactor"] = CorrNtcFactor
	data["CorrPtcOffset"] = CorrPtcOffset
	data["CorrPtcFactor"] = CorrPtcFactor
	with open(WorkDir+'/PiLogger_Config.json','w') as outfile:
		json.dump(data,outfile,sort_keys=True,indent=4)

def readPiLoConf():
	global I2Cadr, MeasInter, TimPuFact
	Fehler = ""
	pilogger = smbus.SMBus(1)
	try:
		SlaveAddr = pilogger.read_byte_data(I2Cadr,0x11)
	except IOError:
		printD("I2C Fehler beim Lesen SlaveAddr\n")
		printE(getLogTime()+" I2C Fehler @ Lesen SlaveAddr")
		Fehler += getLogTime()+" I2C Fehler @ Lesen SlaveAddr;"
		SlaveAddr = 72
	try:
		I2Cadr = int(SlaveAddr)								# globale Variable aktualisieren
	except ValueError:
		try:
			I2Cadr = int(SlaveAddr,16)
		except ValueError:
			I2Cadr = 72
	try:
		TimeBase = pilogger.read_byte_data(I2Cadr,0x12)
	except IOError:
		printD("I2C Fehler beim Lesen TimeBase\n")
		printE(getLogTime()+" I2C Fehler @ Lesen Zeitbasis")
		Fehler += getLogTime()+" I2C Fehler @ Lesen Zeitbasis;"
		TimeBase = 0
	try:
		TimFacLo = pilogger.read_byte_data(I2Cadr,0x13)
	except IOError:
		printD("I2C Fehler beim Lesen TimFacLo\n")
		printE(getLogTime()+" I2C Fehler @ Lesen Zeitfaktor Lo")
		Fehler += getLogTime()+" I2C Fehler @ Lesen Zeitfaktor Lo;"
		TimFacLo = 1
	try:
		TimFacHi = pilogger.read_byte_data(I2Cadr,0x14)
	except IOError:
		printD("I2C Fehler beim Lesen TimFacHi\n")
		printE(getLogTime()+" I2C Fehler @ Lesen Zeitfaktor Hi")
		Fehler += getLogTime()+" I2C Fehler @ Lesen Zeitfaktor Hi;"
		TimFacHi = 0
	if TimeBase == 0:
		cTimeBase = 1
	elif TimeBase == 1:
		cTimeBase = 1/4
	elif TimeBase == 2:
		cTimeBase = 1/64
	elif TimeBase == 3:
		cTimeBase = 1/512
	else:
		cTimeBase = 1
	MeasInter = (256 * TimFacHi + TimFacLo) * cTimeBase		# globale Variable aktualisieren
	try:
		AvgFactr = pilogger.read_byte_data(I2Cadr,0x15)
	except IOError:
		printD("I2C Fehler beim Lesen AvgFactr\n")
		printE(getLogTime()+" I2C Fehler @ Lesen Mittelungsfaktor")
		Fehler += getLogTime()+" I2C Fehler @ Lesen Mittelungsfaktor;"
		AvgFactr = 3
	try:
		TimPuFac = pilogger.read_byte_data(I2Cadr,0x16)
	except IOError:
		printD("I2C Fehler beim Lesen TimPuFac\n")
		printE(getLogTime()+" I2C Fehler @ Lesen PulsZeitfaktor")
		Fehler += getLogTime()+" I2C Fehler @ Lesen PulsZeitfaktor;"
		TimPuFac = 10
	TimPuFact = float(TimPuFac)								# globale Variable aktualisieren
	return (SlaveAddr,TimeBase,TimFacLo,TimFacHi,AvgFactr,TimPuFac,Fehler)

def writePiLoConf(nSlavAddr,nTimeBase,nTimFacLo,nTimFacHi,nAvgFactr,nTimPuFac):
	global I2Cadr
	response = 'ok'
	pilogger = smbus.SMBus(1)
	try:
		pilogger.write_byte_data(I2Cadr,0x01,nSlavAddr)
		I2Cadr = nSlavAddr
	except IOError:
		printD("I²C Fehler @ new SlavAddr")
		printE(getLogTime()+" I2C Fehler @ Schreiben SlavAddr")
		response = 'Fehler'
	try:
		pilogger.write_byte_data(I2Cadr,0x02,nTimeBase)
	except IOError:
		printD("I²C Fehler @ new TimeBase")
		printE(getLogTime()+" I2C Fehler @ Schreiben TimeBase")
		response = 'Fehler'
	try:
		pilogger.write_byte_data(I2Cadr,0x03,nTimFacLo)
	except IOError:
		printD("I²C Fehler @ new TimFacLo")
		printE(getLogTime()+" I2C Fehler @ Schreiben TimFacLo")
		response = 'Fehler'
	try:
		pilogger.write_byte_data(I2Cadr,0x04,nTimFacHi)
	except IOError:
		printD("I²C Fehler @ new TimFacHi")
		printE(getLogTime()+" I2C Fehler @ Schreiben TimFacHi")
		response = 'Fehler'
	try:
		pilogger.write_byte_data(I2Cadr,0x05,nAvgFactr)
	except IOError:
		printD("I²C Fehler @ new AvgFactr")
		printE(getLogTime()+" I2C Fehler @ Schreiben AvgFactr")
		response = 'Fehler'
	try:
		pilogger.write_byte_data(I2Cadr,0x06,nTimPuFac)
	except IOError:
		printD("I²C Fehler @ new TimPuFac")
		printE(getLogTime()+" I2C Fehler @ Schreiben TimPuFac")
		response = 'Fehler'
	return (response)

def PiLoInit():
	global I2Cadr, MeasInter, LogFactor, StatReset, TimPuFact, UnitPulse1, FactPulse1
	global UnitPulse2, FactPulse2, TempSense, LogSplit, LogLines, TimeCount, TimeCntTag
	global EnerCntB, EnerCntTagB, EnerCntE, EnerCntTagE, EnerCntV, EnerCntTagV, LineCount
	global WindAvg10m, WindAvg60m, WindAvgTag, WindAvgJahr, InitWindAvg
	global Avg10mFact, Avg60mFact, AvgTagFact, AvgJahrFact
	global DoVAcorr, CorrVoltOffset, CorrVoltFactor, CorrAmpOffset, CorrAmpFactor
	global CorrNtcOffset, CorrNtcFactor, CorrPtcOffset, CorrPtcFactor
	global PtcTable, PtcTablePointer, NtcTable, NtcTablePointer
	gotConfig = False
	printE(getLogTime()+" Neustart")
	try:
		with open(WorkDir+'/PiLogger_Config.json','r') as infile:
			data = json.load(infile)
		SlaveAddr = data["SlaveAddr"]
		MeasInter = data["MeasInter"]
		LogFactor = data["LogFactor"]
		StatReset = data["StatReset"]
		TimPuFact = data["TimPuFact"]
		UnitPulse1 = data["UnitPulse1"]
		FactPulse1 = data["FactPulse1"]
		UnitPulse2 = data["UnitPulse2"]
		FactPulse2 = data["FactPulse2"]
		TempSense = data["TempSense"]
		LogSplit = data["LogSplit"]
		LogLines = data["LogLines"]
		DoVAcorr = data["DoVAcorr"]
		CorrVoltOffset = data["CorrVoltOffset"]
		CorrVoltFactor = data["CorrVoltFactor"]
		CorrAmpOffset = data["CorrAmpOffset"]
		CorrAmpFactor = data["CorrAmpFactor"]
		CorrNtcOffset = data["CorrNtcOffset"]
		CorrNtcFactor = data["CorrNtcFactor"]
		CorrPtcOffset = data["CorrPtcOffset"]
		CorrPtcFactor = data["CorrPtcFactor"]
		printD("Config gelesen")
		gotConfig = True
	except (IOError, KeyError):
		SlaveAddr = 72
		MeasInter = 2.0
		LogFactor = 30
		StatReset = True
		TimPuFact = 5.0
		UnitPulse1 = 'km/h'
		FactPulse1 = 1.44
		UnitPulse2 = 'm/s'
		FactPulse2 = 0.4
		TempSense = 'NTC 10k B3928'
		LogSplit = True
		LogLines = 1440
		DoVAcorr = False
		CorrVoltOffset = 0.0
		CorrVoltFactor = 1.0
		CorrAmpOffset = 0
		CorrAmpFactor = 1.0
		CorrNtcOffset = 0
		CorrNtcFactor = 1.0
		CorrPtcOffset = 0
		CorrPtcFactor = 1.0
		printD("Fehler beim Lesen von 'PiLogger_Config.json'")
		printE(getLogTime()+" Fehler @ Lesen 'PiLogger_Config.json'")
		gotConfig =False
	try:
		I2Cadr = int(SlaveAddr)
	except ValueError:
		try:
			I2Cadr = int(SlaveAddr,16)
		except ValueError:
			I2Cadr = 72

	for i in range(len(PtcTable)):
		if PtcTable[i][1] >= 25:
			PtcTablePointer = i
			break
	for i in range(len(NtcTable)):
		if NtcTable[i][1] >= 25:
			NtcTablePointer = i
			break

	pilogger = smbus.SMBus(1)							# beim Raspberry Pi 1 SMBus(0)
	try:
		ant = pilogger.read_word_data(I2Cadr,0x31)		# Dummy Read zum Initialisieren
	except IOError:
		printD("I²C Fehler @ DummyRead Temp")
		printE(getLogTime()+" I2C Fehler @ DummyRead Temp")
		ant = 0
	readPiLoConf()
	if not gotConfig:									# Wenn kein 'PiLogger_Config.json' -> anlegen
		writeConfig()
	try:
		f = open(WorkDir+'/LastLog.txt','r')
		try:
			TimeCount = float(f.readline())				# summierte Zeit für Dauer-Energie-Zähler
			EnerCntB = float(f.readline())				# letzter Bilanz-Zählerstand
			EnerCntE = float(f.readline())				# letzter Ertrag-Zählerstand
			EnerCntV = float(f.readline())				# letzter Verbrauch-Zählerstand
			TimeCntTag = float(f.readline())			# summierte Zeit für Tages-Energie-Zähler
			EnerCntTagB = float(f.readline())			# letzter Bilanz-TagesZählerstand
			EnerCntTagE = float(f.readline())			# letzter Ertrag-TagesZählerstand
			EnerCntTagV = float(f.readline())			# letzter Verbrauch-TagesZählerstand
			LineCount = int(f.readline())				# Eintragszahl in aktueller LogDatei
			Zeitstring = f.readline()					# letzter Zeitstempel
			Zeitstring = Zeitstring.split('\n',1)[0]	# Linefeed abtrennen
			WindAvg10m = float(f.readline())			# letzter Wind 10 Min Durchschnitt
			WindAvg60m = float(f.readline())			# letzter Wind 1 Std Durchschnitt
			WindAvgTag = float(f.readline())			# letzter Wind 1 Tag Durchschnitt
			WindAvgJahr = float(f.readline())			# letzter Wind 1 Jahr Durchschnitt
		finally:
			f.close()
			printD("LastLog gelesen")
			try:
				LogZeit = datetime.strptime(Zeitstring,"%Y-%m-%d %H:%M:%S")
			except ValueError:
				LogZeit = datetime(2023,1,1,0,0,0)
			printD(LogZeit)
	except:
		TimeCount = 0.0
		EnerCntB = 0.0
		EnerCntE = 0.0
		EnerCntV = 0.0
		TimeCntTag = 0.0
		EnerCntTagB = 0.0
		EnerCntTagE = 0.0
		EnerCntTagV = 0.0
		LineCount = 0
		LogZeit = datetime(2019,1,1,0,0,0)
		WindAvg10m = 0.0
		WindAvg60m = 0.0
		WindAvgTag = 0.0
		WindAvgJahr = 0.0
		printD("Fehler beim Lesen von 'LastLog.txt'")
		printE(getLogTime()+" Fehler @ Lesen 'LastLog.txt'")
	while datetime.now() <= LogZeit :					# Warten bis Zeit synchronisiert ist
		sleep(5)
		printD("Warte...")
		printE(getLogTime()+" Warten auf NTP Sync")
	printE(getLogTime()+" Start Log-Mode")
	try:
		pilogger.write_byte(I2Cadr,0x78)				# Statistisk Reset Block1
		printD("Stat-Reset")
	except IOError:
		printD("I²C Fehler @ StatReset 1\n")
		printE(getLogTime()+" I2C Fehler @ StatReset 1")
	try:
		pilogger.write_byte(I2Cadr,0x88)				# Statistisk Reset Block2
	except IOError:
		printD("I²C Fehler @ StatReset 2\n")
		printE(getLogTime()+" I2C Fehler @ StatReset 2")

	Avg10mFact = 600 / MeasInter / TimPuFact / 5
	Avg60mFact = 3600 / MeasInter / TimPuFact / 5
	AvgTagFact = 86400 / MeasInter / TimPuFact / 5
	AvgJahrFact = 31536000 / MeasInter / TimPuFact / 5

	if LogSplit and (LineCount >= LogLines):
		SplitLogfile()
		LineCount = 0
	else:
		LogHeader(True)

def LogHeader(trennen):
	lineA = '#____Timestamp_____;Mom[°C];Avg[°C];Min[°C];Max[°C];Mom[{0}];Avg[{0}];Min[{0}];Max[{0}];Mom [V];\
Avg [V];Min [V];Max [V]; Mom [A]; Avg [A]; Min [A]; Max [A]; Mom [W]; Avg [W]; Min [W]; Max [W]; Bila [Wh];\
 Ertr [Wh]; Verb [Wh];BilTg [Wh];ErtTg [Wh];VerTg [Wh];W1h[{0}];W1d[{0}];W1y[{0}]'.format(UnitPulse1)
	lineB = str(datetime.now())							# os.path.getmtime(path) ?
	lineB = lineB.split('.',1)[0]						# microsec abtrennen
	lineB += ';NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN;NaN'
	with open(WorkDir+'/logdata.csv','a') as datafile:
		print(lineA,file=datafile)						# 297 Zeichen pro Zeile + 446
		print(lineB,file=datafile)
	if trennen:
		with open(WorkDir+'/showdata.csv','a') as datafile:
			print(lineA,file=datafile)
			print(lineB,file=datafile)

def SplitLogfile():
	try:
		copyfile(WorkDir+'/logdata.csv',WorkDir+'/showdata.csv')
	except IOError as e:
		printD("Unable to copy file. %s" % e)
		exit(1)
	except:
		printD("Unexpected error:", sys.exc_info())
		exit(1)
	oldname = WorkDir+'/logdata.csv'
	stamp = str(datetime.now())
	stamp = stamp.split('.',1)[0]						# microsec abtrennen
	stamp = stamp.replace(' ','_')
	stamp = stamp.replace(':','-')
	newname = WorkDir+'/logdata_'+stamp+'.csv'
	os.rename(oldname,newname)
	printD("Split Logfile")
	printE(getLogTime()+" Split Logfile")
	LogHeader(False)

def TempValNtc1(ntv):									# NTC 10 kOhm @ 25°C, alt, B25/100=3950
	global CorrNtcOffset, CorrNtcFactor
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
		w = w * CorrNtcFactor + CorrNtcOffset			# * Korrektur Exemplarstreuung
	return w

# NTC 10 kOhm @ 25°C, B25/85=3928, B25/100=3950
# -55°C...+150°C , 3 Segment Approximation -10°C..+70°C < +/-0.4K
def TempValNtc2(ntv):
	global CorrNtcOffset, CorrNtcFactor
	v = ntv / 65535
	if ntv < 1336:										# > +150°C
		w = 999
	elif ntv >= 62218:									# < -55°C
		w = -999
	else:
		if ntv < 10523:									# > +70°C
			w = -37.9441456*log(v)+2.42698623
		elif ntv < 55328:								# > -15°C
			w = +110.012731-291.206862*v+365.866946*v*v-227.609690*v*v*v
		else:											# <= -15°C
			w = +46902.5190-159135.977*v+180139.491*v*v-68063.7560*v*v*v
		w = w * CorrNtcFactor + CorrNtcOffset			# * Korrektur Exemplarstreuung
	return w

# NTC 10 kOhm @ 25°C, B25/85=3477, B25/100=3492
# -55°C...+160°C , 3 Segment Approximation -55°C..+100°C < +/-0.6K
def TempValNtc3(ntv):
	global CorrNtcOffset, CorrNtcFactor
	v = ntv / 65535
	if ntv < 1750:										# > +160°C
		w = 999
	elif ntv >= 61888:									# < -55°C
		w = -999
	else:
		if ntv < 9818:									# > +75°C
			w = -45.6395979*log(v)-4.97482473
		elif ntv < 55498:								# > -15°C
			w = +126.385782-360.841171*v+471.966445*v*v-290.638213*v*v*v
		else:											# <= -15°C
			w = +25437.9192-87503.0502*v+100504.490*v*v-38580.0352*v*v*v
		w = w * CorrNtcFactor + CorrNtcOffset			# * Korrektur Exemplarstreuung
	return w

# NTC per Tabelle
def TempValNtc4(ntv):									
	global NtcTable, NtcTablePointer, CorrNtcOffset, CorrNtcFactor
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
		if NtcTable[NtcTablePointer][0] == ntv:			# Treffer!
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
		w = w * CorrNtcFactor + CorrNtcOffset			# * Korrektur Exemplarstreuung
	return w

# PTC Pt1000, 1000 Ohm @ 0°C
# -60°C...+290°C Approximation -55°C...+280°C < +/-0,02K
def TempValPtc1(ptv):
	global CorrPtcOffset, CorrPtcFactor
	v = ptv / 65535
	if ptv < 25498:
		w = -999
	elif ptv < 62224:
		w = -249.992835+453.078834*v+62.3193206*v*v+63.2008663*v*v*v
		w = w * CorrPtcFactor + CorrPtcOffset			# * Korrektur Exemplarstreuung
	else:
		w = 999
	return w

# PTC KTY81-110, 1000 Ohm @ 25°C
# -55°C...+140°C Approximation < +/-0,4K
def TempValPtc2(ptv):									
	global CorrPtcOffset, CorrPtcFactor
	v = ptv / 65535
	if ptv < 16016:
		w = -999
	elif ptv < 62189:
		w = -175.628285+580.82185*v-437.516532*v*v+189.749364*v*v*v
		w = w * CorrPtcFactor + CorrPtcOffset			# * Korrektur Exemplarstreuung
	else:
		w = 999
	return w

# PTC per Tabelle
def TempValPtc3(ptv):									
	global PtcTable, PtcTablePointer, CorrPtcOffset, CorrPtcFactor
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
		if PtcTable[PtcTablePointer][0] == ptv:			# Treffer!
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
		w = w * CorrPtcFactor + CorrPtcOffset			# * Korrektur Exemplarstreuung
	return w

def TempVal(raw):
	if TempSense == 'NTC 10k':							# rückwärts kompatibel
		tval = TempValNtc1(raw)
	elif TempSense == 'NTC 10k B3928':
		tval = TempValNtc2(raw)
	elif TempSense == 'NTC 10k B3477':
		tval = TempValNtc3(raw)
	elif TempSense == 'NTC Tabelle':
		tval = TempValNtc4(raw)
	elif TempSense == 'PT1000':							# rückwärts kompatibel
		tval = TempValPtc1(raw)
	elif TempSense == 'PTC Pt1000':
		tval = TempValPtc1(raw)
	elif TempSense == 'PTC KTY81-110':
		tval = TempValPtc2(raw)
	elif TempSense == 'PTC Tabelle':
		tval = TempValPtc3(raw)
	else:
		tval = '-UTS-'									# Fehler: unbekannter Tem-Sensor
	return tval

def getPiLoTemp():
	Fehler = ""
	pilogger = smbus.SMBus(1)
	try:
		ant = pilogger.read_word_data(I2Cadr,0x30)		# momentane Temperatur
	except IOError:
		printD("I²C Fehler @ Read Temp")
		ant = 0
		Fehler = getLogTime()+" I2C Fehler @ Temperatur-Lesen"
	tc = TempVal(ant)
	if tc != '-UTS-':
		tf = tc * 1.8 + 32
		out1 = '{0:-6.1f}'.format(tc)
		out2 = '{0:-6.1f}'.format(tf)
	else:
		out1 = 'tc'
		out2 = 'tf'
		Fehler = getLogTime()+" unbekannter Temperatur-Sensor"
	return out1,out2,Fehler

def getPiLoVoltAmp():
	global DoVAcorr, CorrVoltOffset, CorrVoltFactor, CorrAmpOffset, CorrAmpFactor
	Fehler = ""
	pilogger = smbus.SMBus(1)
	try:
		ant1 = pilogger.read_word_data(I2Cadr,0x50)		# momentane Spannung
	except IOError:
		printD("I²C Fehler @ Read Volt")
		ant1 = 0
		Fehler += getLogTime()+" I2C Fehler @ Volt-Lesen;"
	volt = ant1 / 1092.267
	try:
		ant2 = pilogger.read_word_data(I2Cadr,0x60)		# momentaner Strom
	except IOError:
		printD("I²C Fehler @ Read Amp")
		ant2 = 0
		Fehler += getLogTime()+" I2C Fehler @ Amp-Lesen;"
	if ant2 >= 32768:
		ant2 = ant2 - 65536
	amp = ant2 / 2141.634
	try:
		ant4 = pilogger.read_word_data(I2Cadr,0x20)		# momentane Leistung
	except IOError:
		printD("I²C Fehler @ Read Watt1")
		ant4 = 0
		Fehler += getLogTime()+" I2C Fehler @ Watt1-Lesen;"
	try:
		ant5 = pilogger.read_word_data(I2Cadr,0x21)
	except IOError:
		printD("I²C Fehler @ Read Watt2")
		ant5 = 0
		Fehler += getLogTime()+" I2C Fehler @ Watt2-Lesen;"
	aktP = ant4 + ant5*65536
	if aktP > 2147483647:
		aktP = aktP - 4294967295
	aktP = aktP / 2147483648 * 918
	if DoVAcorr:										# Einrechnung Korrekturwerte
		if volt < 0.0005:
			volt = 0.0005
		corrAmp = aktP / volt
		corrVolt = volt * CorrVoltFactor + CorrVoltOffset
		corrAmp = corrAmp * CorrAmpFactor + CorrAmpOffset
		aktP = corrVolt * corrAmp
		volt = volt * CorrVoltFactor + CorrVoltOffset
		amp = amp * CorrAmpFactor + CorrAmpOffset
	
	out1 = '{0:-8.3f}'.format(volt)
	out2 = '{0:-8.3f}'.format(amp)
	out3 = 'Laden'
	if amp < 0:											# Betrag bilden
		amp = -amp
		out3 = 'Entladen'
	if volt < 0:
		volt = -volt
	out4 = '{0:-8.3f}'.format(aktP)
	return out1,out2,out3,out4,Fehler

def getPiLoEner(EnerCnt):
	EnerWh = EnerCnt / 3600
	if EnerWh > 999.99:
		out = '{0:-8.2f} kWh'.format(EnerWh/1000)
	else:
		out = '{0:-8.2f} Wh'.format(EnerWh)
	out = out.replace('.',',')
	return out

def getPiLoEnerRaw(EnerCnt):
	EnerWh = EnerCnt / 3600
	out = '{0:-11.2f}'.format(EnerWh)
	return out

def getPiLoEnTi(zeit):									# Zeitraum in sec für Energie umrechnen
	min = 0
	if zeit >= 60:
		min = int(zeit/60)
		sec = int(zeit - min*60)
	else:
		sec = int(zeit)
	std = 0
	if min >= 60:
		std = int(min/60)
		min = min - std*60
	day = 0
	if std >= 24:
		day = int(std/24)
		std = std - day*24
		out = '{0:2d}d {1:2d}h {2:2d}m'.format(day,std,min,sec)
	else:
		out = '{0:2d}h {1:2d}m {2:2d}s'.format(std,min,sec)
	return out

def getPiLoTime():
	dt = datetime.now()
	out = dt.strftime("%A, %d.%B %Y %H:%M:%S")			# mit aktueller user locale
	return out

def getLogTime():
	dt = datetime.now()
	out = dt.strftime("%d.%m.%y %H:%M:%S")
	return out

def LastLogSchreiben(LogZeit):
	global TimeCount, EnerCntB, EnerCntE, EnerCntV
	global TimeCntTag, EnerCntTagB, EnerCntTagE, EnerCntTagV
	global WindAvg10m, WindAvg60m, WindAvgTag, WindAvgJahr
	line = str(LogZeit)
	line = line.split('.',1)[0]							# microsec abtrennen
	with open(WorkDir+'/LastLog.txt','w') as datafile:
		print(TimeCount,file=datafile)
		print(EnerCntB,file=datafile)
		print(EnerCntE,file=datafile)
		print(EnerCntV,file=datafile)
		print(TimeCntTag,file=datafile)
		print(EnerCntTagB,file=datafile)
		print(EnerCntTagE,file=datafile)
		print(EnerCntTagV,file=datafile)
		print(LineCount,file=datafile)
		print(line,file=datafile)
		print(WindAvg10m,file=datafile)
		print(WindAvg60m,file=datafile)
		print(WindAvgTag,file=datafile)
		print(WindAvgJahr,file=datafile)
	printD("LastLog geschrieben.")

def ScaleWatt(karl,lisa,maxi,nina,voltcalc):
	global DoVAcorr
	Watt = karl + lisa*256 + (maxi + nina*256)*65536
	if Watt > 2147483647:
		Watt = Watt - 4294967295
	Watt = Watt / 2147483648 * 918						# Watt unkorrigiert skaliert
	if DoVAcorr:										# Einrechnung Korrekturwerte
		if voltcalc < 0.0005:
			voltcalc = 0.0005
		corrAmp = Watt / voltcalc
		corrVolt = voltcalc * CorrVoltFactor + CorrVoltOffset
		corrAmp = corrAmp * CorrAmpFactor + CorrAmpOffset
		Watt = corrVolt * corrAmp
	return Watt

def dotheLog():
	global TimeCount, EnerCntB, EnerCntE, EnerCntV, TimeCntV
	global TimeCntTag, EnerCntTagB, EnerCntTagE, EnerCntTagV, LineCount
	global DoVAcorr, CorrVoltOffset, CorrVoltFactor, CorrAmpOffset, CorrAmpFactor
	global WindAvg10m
	pilogger = smbus.SMBus(1)
	logStamp = datetime.now()
	ant = []
	try:
		ant = pilogger.read_i2c_block_data(I2Cadr,0x70)
	except IOError:
		printD("I²C Fehler @ Blockread 1\n")
		printE(getLogTime()+" I2C Fehler @ Blockread 1")
	ret = []
	try:
		ret = pilogger.read_i2c_block_data(I2Cadr,0x80)
	except IOError:
		printD("I²C Fehler @ Blockread 2\n")
		printE(getLogTime()+" I2C Fehler @ Blockread 2")
	printD(logStamp)
	if StatReset == True:
		try:
			pilogger.write_byte(I2Cadr,0x78)
			printD("Stat-Reset")
		except IOError:
			printD("I²C Fehler @ StatReset 1\n")
			printE(getLogTime()+" I2C Fehler @ StatReset 1")
		try:
			pilogger.write_byte(I2Cadr,0x88)
		except IOError:
			printD("I²C Fehler @ StatReset 2\n")
			printE(getLogTime()+" I2C Fehler @ StatReset 2")
	line = str(logStamp)
	line = line.split('.',1)[0]							# microsec abtrennen

	vl = []
	for i in range (16):
		x=ret.pop(0)
		y=ret.pop(0)
		z=y*256+x
		if i in range (12,16):							# Stromwerte +/-
			if z >= 32768:
				z = z - 65536
		if i == 3:										# Wenn NTC dann Max Temp <> Min Temp
			if TempSense[0] == 'N':
				vl.insert(2,z)
			else:
				vl.append(z)
		else:
			vl.append(z)

	for i in range (16):
		z=vl.pop(0)
		if i < 4:										# Temperatur
			w = TempVal(z)
			if w != '-UTS-':
				out = '{0:-7.2f}'.format(w)
			else:
				out = ' -UTS- '
			line = line+';'+out
		elif i < 8:										# Pulse
			z = z * FactPulse1 / MeasInter / TimPuFact
			if i == 5:
				z = WindAvg10m
			line = line+';'+'{0:-8.3f}'.format(z)
		elif i < 12:									# Volt
			z = z / 1092.267
			if i == 8:
				voltakt = z
			if i == 9:
				voltavg = z
			if i == 10:
				voltmin = z
			if i == 11:
				voltmax = z
			if DoVAcorr:
				z = z * CorrVoltFactor + CorrVoltOffset	# Korrekturwerte einrechnen
			line = line+';'+'{0:-8.3f}'.format(z)
		else:											# Amp
			z = z / 2141.634
			if DoVAcorr:
				z = z * CorrAmpFactor + CorrAmpOffset	# Korrekturwerte einrechnen
			line = line+';'+'{0:-8.3f}'.format(z)

	karl = ant.pop(0)
	lisa = ant.pop(0)
	maxi = ant.pop(0)
	nina = ant.pop(0)
	aktP = ScaleWatt(karl,lisa,maxi,nina,voltakt)

	karl = ant.pop(0)
	lisa = ant.pop(0)
	maxi = ant.pop(0)
	nina = ant.pop(0)
	avgP = ScaleWatt(karl,lisa,maxi,nina,voltavg)

	karl = ant.pop(0)
	lisa = ant.pop(0)
	maxi = ant.pop(0)
	nina = ant.pop(0)
	minP = ScaleWatt(karl,lisa,maxi,nina,voltmin)

	karl = ant.pop(0)
	lisa = ant.pop(0)
	maxi = ant.pop(0)
	nina = ant.pop(0)
	maxP = ScaleWatt(karl,lisa,maxi,nina,voltmax)

	if minP > maxP:							# wenn durch Korrektur Volt & Amp negativ sind -> swap nötig
		swap = minP
		minP = maxP
		maxP = swap
	line = line+';'+'{0:-8.3f}'.format(aktP)
	line = line+';'+'{0:-8.3f}'.format(avgP)
	line = line+';'+'{0:-8.3f}'.format(minP)
	line = line+';'+'{0:-8.3f}'.format(maxP)

	if DoVAcorr:
		voltavg = voltavg * CorrVoltFactor + CorrVoltOffset	# voltavg unkorrigiert nicht mehr benötigt
	if voltavg < 0:										# Negative Spannung nur durch Korrektur möglich
		avgP = - avgP									# Fehlzählung durch negative Spannung nach Korrektur verhindern

	EnerCntB += avgP*LogFactor*MeasInter				# Watt*Sec Dauer-Zähler
	EnerWh = EnerCntB / 3600
	line = line+';'+'{0:-10.3f}'.format(EnerWh)
	if avgP > 0:
		EnerCntE += avgP*LogFactor*MeasInter
	EnerWh = EnerCntE / 3600
	line = line+';'+'{0:-10.3f}'.format(EnerWh)
	if avgP < 0:
		EnerCntV -= avgP*LogFactor*MeasInter
	EnerWh = EnerCntV / 3600
	line = line+';'+'{0:-10.3f}'.format(EnerWh)

	EnerCntTagB += avgP*LogFactor*MeasInter				# Watt*Sec Tages-Zähler
	EnerWh = EnerCntTagB / 3600
	line = line+';'+'{0:-10.3f}'.format(EnerWh)
	if avgP > 0:
		EnerCntTagE += avgP*LogFactor*MeasInter
	EnerWh = EnerCntTagE / 3600
	line = line+';'+'{0:-10.3f}'.format(EnerWh)
	if avgP < 0:
		EnerCntTagV -= avgP*LogFactor*MeasInter
	EnerWh = EnerCntTagV / 3600
	line = line+';'+'{0:-10.3f}'.format(EnerWh)

	line = line+';'+'{0:-8.3f}'.format(WindAvg60m)
	line = line+';'+'{0:-8.3f}'.format(WindAvgTag)
	line = line+';'+'{0:-8.3f}'.format(WindAvgJahr)

	with open(WorkDir+'/logdata.csv','a') as datafile:
		print(line,file=datafile)
	with open(WorkDir+'/showdata.csv','a') as datafile:
		print(line,file=datafile)

	TimeCount += LogFactor*MeasInter					# Zeitsumme für Dauer-Energie-Zähler in sec
	TimeCntTag += LogFactor*MeasInter					# Zeitsumme für Tages-Energie-Zähler in sec

	resetZeit = datetime.combine(datetime.date(logStamp),time(0,0,0))
	timeDiff = logStamp - resetZeit
	diffSek = timeDiff.seconds + timeDiff.microseconds / 1000000
	if diffSek > 0 and diffSek <= (LogFactor*MeasInter):
		printD('Tageszähler-Reset')
		TimeCntTag = 0.0
		EnerCntTagB = 0.0
		EnerCntTagE = 0.0
		EnerCntTagV = 0.0

	LineCount += 1
	if LogSplit and LineCount >= LogLines:
		SplitLogfile()
		LineCount = 0
	LastLogSchreiben(logStamp)

def JetztAber(para):
	global MeasCount, WindCount, LogFactor, TimPuFact, WindAvg10m, Avg10mFact
	global WindAvg60m, Avg60mFact, WindAvgTag, AvgTagFact, WindAvgJahr, AvgJahrFact
	global WindAkt1, WindAkt2, FactPulse1, FactPulse2, MeasInter, InitWindAvg
	MeasCount += 1
	WindCount += 1
	printD("Interrupt! auf {} bei {}".format(para,MeasCount))
	if WindCount >= TimPuFact:
		pilogger = smbus.SMBus(1)
		try:
			ant = pilogger.read_word_data(I2Cadr,0x40)		# momentaner Wind
		except IOError:
			printD("I²C Fehler @ Read Wind")
			ant = 0
		WindAkt1 = ant * FactPulse1 / MeasInter / TimPuFact
		WindAkt2 = ant * FactPulse2 / MeasInter / TimPuFact
		if InitWindAvg:
			WindAvg10m = WindAkt1
			WindAvg60m = WindAkt1
			WindAvgTag = WindAkt1
			WindAvgJahr = WindAkt1
			InitWindAvg = False
			printD("Reset Wind-Statistik")
			printE(getLogTime()+" Reset Wind-Statistik")
		else:
			WindAvg10m += (WindAkt1-WindAvg10m) / Avg10mFact	# Winddaten in Haupteinheiten mitteln
			WindAvg60m += (WindAkt1-WindAvg60m) / Avg60mFact
			WindAvgTag += (WindAkt1-WindAvgTag) / AvgTagFact
			WindAvgJahr += (WindAkt1-WindAvgJahr) / AvgJahrFact
		WindCount = 0
	if MeasCount >= LogFactor:
		printD("Ich logge..")
		dotheLog()
		MeasCount = 0

@bottle.route('/')
def MainHandler():
	values = {
		'debug': DEBUG,
	}
	return bottle.template('index.html', values)

@bottle.route('/static/<filename>')
def StaticHandler(filename):
	if filename.endswith(".css"):
		bottle.response.content_type = 'text/css'
	elif filename.endswith(".js"):
		bottle.response.content_type = 'text/javascript'
	elif filename.endswith(".png"):
		bottle.response.content_type = 'image/png'
	return bottle.static_file(filename, root=os.path.join(WorkDir,'static'))

@bottle.route('/logdata/<filename>')
def LogDataHandler(filename):
	if filename.endswith(".csv"):
		bottle.response.content_type = 'text/csv'
	return bottle.static_file(filename, root=WorkDir)

@bottle.route('/download/<filename:path>')
def download(filename):
	if filename == 'logdata.csv':
		# first copy work file to /static dir (snapshot)
		# adding exception handling
		try:
			copyfile(WorkDir+'/logdata.csv',WorkDir+'/logdata_snap.csv')
			filename = 'logdata_snap.csv'
		except IOError as e:
			printD("Unable to copy file. %s" % e)
			printE(getLogTime()+" Fehler @ Copy Logdata")
			exit(1)
		except:
			printD("Unexpected error:", sys.exc_info())
			printE(getLogTime()+" Fehler @ Copy Logdata")
			exit(1)
	return bottle.static_file(filename, root=WorkDir, download=True)

@bottle.route('/reqdelete/<filename:path>')
def delete_file(filename):
	printD("Datei löschen.")
	response = ''
	thisfile = os.path.join(WorkDir,filename)
	printD(thisfile)
	try:
		os.remove(thisfile)
		response = 'ok'
	except OSError as e:
		printD("Error: %s - %s." % (e.filename, e.strerror))
		printE(getLogTime()+" Fehler @ Delete File %s - %s" % (e.filename, e.strerror))
		response = 'Fehler'
	return str(response)

@bottle.route('/flashpilo/')
def do_Flash_PiLo():
	printD("Flash PiLogger.")
	response = ''
	bottle.response.content_type = 'text/plain'
	pilogger = smbus.SMBus(1)
	try:
		pilogger.write_byte_data(I2Cadr,0x0F,0x55)			# Aktuelle Einstellungen flashen
		response = 'ok'
	except IOError:
		printD("I²C Fehler @ Flash PiLogger")
		printE(getLogTime()+" I2C Fehler @ Flash PiLogger")
		response = 'Fehler'
	return str(response)

@bottle.route('/factorydef/')
def do_FactoryDef():
	printD("Set factory default.")
	response = ''
	bottle.response.content_type = 'text/plain'
	pilogger = smbus.SMBus(1)
	try:
		pilogger.write_byte_data(I2Cadr,0x0D,0xAB)			# Factory Default ausführen
		response = 'ok'
	except IOError:
		printD("I²C Fehler @ FactoryDefault")
		printE(getLogTime()+" I2C Fehler @ FactoryDefault")
		response = 'Fehler'
	return str(response)

@bottle.route('/ampzero/')
def do_Amp_Zero():
	printD("Perform AmpZero.")
	response = ''
	bottle.response.content_type = 'text/plain'
	pilogger = smbus.SMBus(1)
	try:
		pilogger.write_byte_data(I2Cadr,0x07,0x44)			# AmpZero ausführen
		response = 'ok'
	except IOError:
		printD("I²C Fehler @ AmpZero")
		printE(getLogTime()+" I2C Fehler @ AmpZero")
		response = 'Fehler'
	return str(response)

@bottle.route('/reqenerzero/')
def do_Ener_Zero():
	global EnerCntB, EnerCntE, EnerCntV, EnerCntTagB, EnerCntTagE, EnerCntTagV, TimeCount, TimeCntTag
	printD("Reset Energiezähler.")
	bottle.response.content_type = 'text/plain'
	TimeCount = 0.0
	EnerCntB = 0.0
	EnerCntE = 0.0
	EnerCntV = 0.0
	TimeCntTag = 0.0
	EnerCntTagB = 0.0
	EnerCntTagE = 0.0
	EnerCntTagV = 0.0
	LastLogSchreiben(datetime.now())
	return str('ok')

@bottle.route('/sendpiloconf')
def Write_PiLoConf():
	global MeasInter, I2Cadr, TimPuFact, MeasCount, InitWindAvg
	printD("Write PiLogger Config.")
	response = ''
	bottle.response.content_type = 'text/plain'
	nSlavAddr = int(bottle.request.query.SlavAddr)
	nTimeBase = int(bottle.request.query.TimeBase)
	nTimFacLo = int(bottle.request.query.TimFacLo)
	nTimFacHi = int(bottle.request.query.TimFacHi)
	nAvgFactr = int(bottle.request.query.AvgFactr)
	nTimPuFac = int(bottle.request.query.TimPuFac)
	response = writePiLoConf(nSlavAddr,nTimeBase,nTimFacLo,nTimFacHi,nAvgFactr,nTimPuFac)
	if response == 'ok':
		if nTimeBase == 0:
			TimeBase = 1
		elif nTimeBase == 1:
			TimeBase = 1/4
		elif nTimeBase == 2:
			TimeBase = 1/64
		elif nTimeBase == 3:
			TimeBase = 1/512
		else:
			TimeBase = 1
		MeasInter = (256 * nTimFacHi + nTimFacLo) * TimeBase
		I2Cadr = nSlavAddr
		TimPuFact = float(nTimPuFac)
	writeConfig()
	MeasCount = 0
	PiLoInit()
	InitWindAvg = True							# PiLo Config ändern -> WindAvg Reset
	return str(response)

@bottle.route('/getpiloconf/')
def Read_PiLoConf():
	printD("Read PiLogger Config.")
	bottle.response.content_type = 'application/json'
	ant = readPiLoConf()
	data = {}
	data["SlavAddr"] = ant[0]
	data["TimeBase"] = ant[1]
	data["TimFacLo"] = ant[2]
	data["TimFacHi"] = ant[3]
	data["AvgFactr"] = ant[4]
	data["TimPuFac"] = ant[5]
	data["Fehler"] = ant[6]
	return json.dumps(data)

@bottle.route('/getraspiconf/')
def Show_RaspiConf():
	printD("Show Raspi Config.")
	bottle.response.content_type = 'application/json'
	data = {}
	data["MeasInter"] = MeasInter
	data["LogFactor"] = LogFactor
	data["StatReset"] = StatReset
	data["UnitPulse1"] = UnitPulse1
	data["FactPulse1"] = FactPulse1
	data["UnitPulse2"] = UnitPulse2
	data["FactPulse2"] = FactPulse2
	data["TempSense"] = TempSense
	data["LogSplit"] = LogSplit
	data["LogLines"] = LogLines
	return json.dumps(data)

@bottle.route('/getcalconf/')
def Show_CalConf():
	printD("Show Cal Config.")
	bottle.response.content_type = 'application/json'
	data = {}
	data["DoVAcorr"] = DoVAcorr
	data["VoltOffset"] = CorrVoltOffset
	data["VoltFactor"] = CorrVoltFactor
	data["AmpOffset"] = CorrAmpOffset
	data["AmpFactor"] = CorrAmpFactor
	data["NtcOffset"] = CorrNtcOffset
	data["NtcFactor"] = CorrNtcFactor
	data["PtcOffset"] = CorrPtcOffset
	data["PtcFactor"] = CorrPtcFactor
	return json.dumps(data)

@bottle.route('/sendraspiconf')
def Store_RaspiConf():
	global FactPulse1, FactPulse2, LogFactor, StatReset, TempSense
	global UnitPulse1, UnitPulse2, LogSplit, LogLines, MeasCount
	printD("Store Raspi Config.")
	bottle.response.content_type = 'application/json'
	FactPulse1 = float(bottle.request.query.FactPulse1)
	FactPulse2 = float(bottle.request.query.FactPulse2)
	LogFactor = int(bottle.request.query.LogFactor)
	StatReset = True
	if bottle.request.query.StatReset == "true":
		StatReset = True
	elif bottle.request.query.StatReset == "false":
		StatReset = False
	TempSense = bottle.request.query.TempSense
	UnitPulse1 = bottle.request.query.UnitPulse1
	UnitPulse2 = bottle.request.query.UnitPulse2
	LogSplit = True
	if bottle.request.query.LogSplit == "true":
		LogSplit = True
	elif bottle.request.query.LogSplit == "false":
		LogSplit = False
	LogLines = int(bottle.request.query.LogLines)
	writeConfig()
	MeasCount = 0
	PiLoInit()
	return str('ok')

@bottle.route('/sendcalconf')
def Store_CalConf():
	global DoVAcorr, CorrVoltOffset, CorrVoltFactor, CorrAmpOffset, CorrAmpFactor
	global CorrNtcOffset, CorrNtcFactor, CorrPtcOffset, CorrPtcFactor
	printD("Store Cal Config.")
	bottle.response.content_type = 'application/json'
	DoVAcorr = True
	if bottle.request.query.DoVAcorr == "true":
		DoVAcorr = True
	elif bottle.request.query.DoVAcorr == "false":
		DoVAcorr = False
	CorrVoltOffset = float(bottle.request.query.VoltOffset)
	CorrVoltFactor = float(bottle.request.query.VoltFactor)
	CorrAmpOffset = float(bottle.request.query.AmpOffset)
	CorrAmpFactor = float(bottle.request.query.AmpFactor)
	CorrNtcOffset = float(bottle.request.query.NtcOffset)
	CorrNtcFactor = float(bottle.request.query.NtcFactor)
	CorrPtcOffset = float(bottle.request.query.PtcOffset)
	CorrPtcFactor = float(bottle.request.query.PtcFactor)
	writeConfig()
	MeasCount = 0
	PiLoInit()
	return str('ok')

@bottle.route('/data/')
def Req_new_data():
	global EnerCntB, EnerCntE, EnerCntV, TimeCount, EnerCntTagB, EnerCntTagE, EnerCntTagV, TimeCntTag
	global WindAkt1, WindAkt2, WindAvg10m, WindAvg60m, WindAvgTag, WindAvgJahr
	FehlerMeldung = ""
	printD("Request new data.")
	bottle.response.content_type = 'application/json'
	data = {}
	Temp1,Temp2,Fehler = getPiLoTemp()
	Temp1 = Temp1.replace('.',',')
	Temp2 = Temp2.replace('.',',')
	data["PiLoTemp1"] = Temp1 + ' °C'
	data["PiLoTemp2"] = Temp2 + ' °F'
	if Fehler != "":
		FehlerMeldung += Fehler
	Wind1 = '{0:-6.1f}'.format(WindAkt1)
	Wind1 = Wind1.replace('.',',')
	Wind2 = '{0:-6.1f}'.format(WindAkt2)
	Wind2 = Wind2.replace('.',',')
	Wind3 = '{0:-6.1f}'.format(WindAvg10m)
	Wind3 = Wind3.replace('.',',')
	Wind4 = '{0:-6.1f}'.format(WindAvg60m)
	Wind4 = Wind4.replace('.',',')
	Wind5 = '{0:-6.1f}'.format(WindAvgTag)
	Wind5 = Wind5.replace('.',',')
	Wind6 = '{0:-6.1f}'.format(WindAvgJahr)
	Wind6 = Wind6.replace('.',',')
	data["PiLoWind1"] = Wind1 + ' ' + UnitPulse1
	data["PiLoWind2"] = Wind2 + ' ' + UnitPulse2
	data["PiLoWind10m"] = Wind3 + ' ' + UnitPulse1
	data["PiLoWind1h"] = Wind4 + ' ' + UnitPulse1
	data["PiLoWind1d"] = Wind5 + ' ' + UnitPulse1
	data["PiLoWind1y"] = Wind6 + ' ' + UnitPulse1
	Volt,Amps,Mode,Watt,Fehler = getPiLoVoltAmp()
	Volt = Volt.replace('.',',')
	Amps = Amps.replace('.',',')
	Watt = Watt.replace('.',',')
	data["PiLoVolt"] = Volt + ' V'
	data["PiLoAmps"] = Amps + ' A'
	data["PiLoMode"] = Mode
	data["PiLoWatt"] = Watt + ' W'
	if Fehler != "":
		FehlerMeldung += Fehler
	ZeitTg = getPiLoEnTi(TimeCntTag)
	ZeitDa = getPiLoEnTi(TimeCount)
	data["TgEner"] = getPiLoEner(EnerCntTagB)
	data["TgEnTi"] = ZeitTg
	data["TgEnerE"] = getPiLoEner(EnerCntTagE)
	data["TgEnTiE"] = ZeitTg
	data["TgEnerV"] = getPiLoEner(EnerCntTagV)
	data["TgEnTiV"] = ZeitTg
	data["PiLoEner"] = getPiLoEner(EnerCntB)
	data["PiLoEnTi"] = ZeitDa
	data["PiLoEnerE"] = getPiLoEner(EnerCntE)
	data["PiLoEnTiE"] = ZeitDa
	data["PiLoEnerV"] = getPiLoEner(EnerCntV)
	data["PiLoEnTiV"] = ZeitDa
	data["PiLoTime"] = getPiLoTime()
	data["Fehler"] = FehlerMeldung
	FehlerMeldung = ""
	return json.dumps(data)

@bottle.route('/rawdata/')
def Req_new_rawdata():
	global EnerCntB, EnerCntE, EnerCntV, TimeCount, EnerCntTagB, EnerCntTagE, EnerCntTagV, TimeCntTag
	global WindAkt1, WindAkt2, WindAvg10m, WindAvg60m, WindAvgTag, WindAvgJahr
	FehlerMeldung = ""
	printD("Request new rawdata.")
	bottle.response.content_type = 'application/json'
	data = {}
	data["PiLoTemp1"],data["PiLoTemp2"],Fehler = getPiLoTemp()
	data["UnitTemp1"] = '°C'
	data["UnitTemp2"] = '°F'
	if Fehler != "":
		FehlerMeldung += Fehler
	data["PiLoWind1"] = '{0:-6.1f}'.format(WindAkt1)
	data["UnitWind1"] = UnitPulse1
	data["PiLoWind2"] = '{0:-6.1f}'.format(WindAkt2)
	data["UnitWind2"] = UnitPulse2
	data["PiLoWind10m"] = '{0:-6.1f}'.format(WindAvg10m)
	data["PiLoWind1h"] = '{0:-6.1f}'.format(WindAvg60m)
	data["PiLoWind1d"] = '{0:-6.1f}'.format(WindAvgTag)
	data["PiLoWind1y"] = '{0:-6.1f}'.format(WindAvgJahr)
	data["PiLoVolt"],data["PiLoAmps"],data["PiLoMode"],data["PiLoWatt"],Fehler = getPiLoVoltAmp()
	if Fehler != "":
		FehlerMeldung += Fehler
	data["DayEnergy"] = getPiLoEnerRaw(EnerCntTagB)
	data["DayEnerTime"] = str(round(TimeCntTag/60))					# in Minuten
	data["DayHarvest"] = getPiLoEnerRaw(EnerCntTagE)
	data["DayConsumption"] = getPiLoEnerRaw(EnerCntTagV)
	data["PermEnergy"] = getPiLoEnerRaw(EnerCntB)
	data["PermEnerTime"] = str(round(TimeCount/60))					# in Minuten
	data["PermHarvest"] = getPiLoEnerRaw(EnerCntE)
	data["PermConsumption"] = getPiLoEnerRaw(EnerCntV)
	data["UnitEnergy"] = 'Wh'
	data["PiLoTime"] = getLogTime()
	data["Error"] = FehlerMeldung
	FehlerMeldung = ""
	return json.dumps(data)

@bottle.route('/listdatafiles/')
def List_Datafiles():
	printD("List data files.")
	data = []
	Liste = os.listdir(WorkDir)
	Liste.sort()
	for file in Liste:
		if file.endswith(".csv"):
			if file not in ("logdata.csv","logdata_snap.csv","showdata.csv"):
				data += [file]
	return json.dumps(data)

def Do_Reboot():
	os.system("sudo reboot now")

@bottle.route('/reqreboot/')
def Req_Reboot():
	printD("Reboot requested.")
	printE(getLogTime()+" Reboot requested")
	t = threading.Timer(1.5,Do_Reboot)
	t.start()
	return str('ok')

def Do_Shutdown():
	os.system("sudo shutdown now")

@bottle.route('/reqshutdown/')
def Req_Shutdown():
	printD("Shutdown requested.")
	printE(getLogTime()+" Shutdown requested")
	t = threading.Timer(1.5,Do_Shutdown)
	t.start()
	return str('ok')

@bottle.route('/reqsplitnow/')
def do_Split_Now():
	global LineCount
	printD("Request Split Logfile.")
	bottle.response.content_type = 'text/plain'
	SplitLogfile()
	LineCount = 0
	return str('ok')

@bottle.error(404)
def error404(error):
	return 'Error 404: Nicht gefunden.'

WorkDir = os.path.dirname(os.path.realpath(__file__))
os.chdir(WorkDir)
loc = locale.getlocale()								# get current locale
printD(loc)
locale.setlocale(locale.LC_ALL, '')						# use user's preferred locale
PiLoInit()

button = Button(4)
button.when_pressed = JetztAber

bottle.run(host='0.0.0.0', port=8080, quiet=True)

printD('\nQuit\n')
printE(getLogTime()+" Quit")


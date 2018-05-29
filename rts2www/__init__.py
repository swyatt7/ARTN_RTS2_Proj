from __future__ import print_function
from flask import Flask, send_file
from flask import render_template
from flask import request
from flask_basicauth import BasicAuth
import requests
from requests.auth import HTTPBasicAuth
import json
import glob
import os
import time
import sys
import subprocess
from lxml import html
import re
from astropy.coordinates import Angle
from astropy import units as u
import sys
from rts2solib import asteroid, stellar, rts2comm, so_exposure

global importRTS2
importRTS2 = True
global prx
prx = None

import rts2
print( "imported rts2" )



app = Flask(__name__)
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
app.static_folder = 'static'
app.config.from_object(__name__)

if len( sys.argv ) == 1:

	CONFIG_PATH = "/home/rts2obs/.mtnops"
	CONFIG_FILE = "flask_rts2.json"
	CONFIG_FD = open(os.path.join(CONFIG_PATH, CONFIG_FILE))

else:
	config_fd = open( sys.argv[1] )
	
CONFIG = json.load(CONFIG_FD)
CONFIG_FD.close()
app.config['BASIC_AUTH_USERNAME'] = CONFIG["username"]
app.config['BASIC_AUTH_PASSWORD'] = CONFIG['password']
basic_auth = BasicAuth( app )


try:
    prx = rts2.createProxy( url='http://localhost:8889', username=CONFIG["username"], password=CONFIG["password"])
    importRTS2 = True
    print("RTS2 succesfully imported")
except:
    print("RTS2 not imported whoopsy")
    importRTS2 = False



name_i = 11
ra_i = 4
dec_i = 5
type_i = 14
exp_i = 7
filt_i = 9
amounts_i = 8
tid_index = 0
type_dict = {"UVOT": 0, "AzTEC": 1, "SPOL": 1, "STAND": 3}



class Rts2Queue:
	def __init__( self, _name ):
	    self.name = _name
	    self.queueitems = self.populate()
	def populate(self):
	    queue = rts2.Queue(prx, self.name)
            queue.load()
	    queueitems = []
            for p in queue.entries:
                targ = rts2.target.get(p.id)
		queueitems.append(Rts2QueueItem(targ[0][1], targ[0][0]))
	    return queueitems


class Rts2QueueItem:
   def __init__(self, _name, _id):
	self.name = _name
	self.id = _id


class QueueObject:
    def __init__(self, _name, _ra, _dec, _type, _obs_infos):
        self.type = _type
        self.name = _name
        self.ra = _ra
        self.dec = _dec
        self.observation_info = _obs_infos

    def outputobjectinfo(self):
        print("Queue Object: {}, {}".format(self.name, self.type))
        print("RA: {}".format(self.ra))
        print("DEC: {}".format(self.dec))
        print("Observation Infos")
        for obsinfo in self.observation_info:
            print("Filter: {}, Exposure Time: {}, Amount {}".format(obsinfo.filter, obsinfo.exptime, obsinfo.num_exposures))


class ObservationInfo:
    def __init__(self, _filter, _exptime, _amount):
        self.amount = _amount
        self.filter = _filter
        self.exptime = _exptime

def populaterts2queues(queues=['plan','manual','simul']):
	Queues = []
	for q in queues:
		Queues.append(Rts2Queue(q))
	return Queues

def findoffset(sr):
    for key in type_dict.keys():
        if key in sr:
            typeindex = sr.index(key)
            if key == "STAND":
                return -99
            return type_i - typeindex
    return 0


def formatcoord(coord):
    if "-" in coord:
        coord = coord.split("-")[1]
        return "-{}:{}:{}".format(coord[0:2], coord[2:4], coord[4:])
    return "{}:{}:{}".format(coord[0:2], coord[2:4], coord[4:])


def readlotis(fullpath):
    fi = open(fullpath)
    lotisdata = []
    for line in fi:
        splitline = line.split()
        offset = findoffset(splitline)
        if offset != -99 and line[0] is not "#":
            name = splitline[name_i - offset]
            ra = formatcoord(splitline[ra_i - offset])
            dec = formatcoord(splitline[dec_i - offset])
            exptime = splitline[exp_i - offset]
            filters = splitline[filt_i - offset]
            amounts = splitline[amounts_i - offset]
            objtype = splitline[type_i - offset]
            observationinfos = []
            for f in filters:
                observationinfos.append(so_exposure(f, exptime, amounts))
            a = stellar(name, ra, dec, observationinfos)
            # a.outputobjectinfo()
            lotisdata.append(a)
    return lotisdata


def readfromweb():
    page = requests.get("http://slotis.kpno.noao.edu/LOTIS/skypatrol.html")
    tree = html.fromstring(page.content)
    targetsinfo = [re.sub('\n', '', x) for x in tree.xpath('//h2/text()')[3:] if '%' in x]
    lotisdata = []
    for line in targetsinfo:
        splitline = line.split()
        offset = findoffset(splitline)
        if offset != -99:
            name = splitline[9]
            ra = formatcoord(splitline[2])
            dec = formatcoord(splitline[3])
            exptime = splitline[5]
            filters = splitline[7]
            amounts = splitline[6]
            objtype = ""
            observationinfos = []
            for f in filters:
                observationinfos.append(so_exposure(f, exptime, amounts))
            lotisdata.append(stellar(name, ra, dec, observationinfos))

    target = os.path.join(APP_ROOT, "uploads")
    file_dest = target+'/lotisweb.queue'
    savequeue(lotisdata, file_dest)
    return [lotisdata, 'lotisweb.queue']


def savequeue(data, fullpath):
    of = open(fullpath, "w+")
    data.sort(key=lambda x: x.name, reverse=False)
    for i, d in enumerate(data):
        param = ('{},{},{},{}'.format(d.name, d.ra, d.dec, d.type)) + "^z^"
        for o in d.observation_info:
            param += ('{},{},{}'.format(o.filter, o.exptime, o.num_exposures)) + "<z>"
        of.write(param + '\n')
    of.close()


def readqueue(fullpath):
    data = []
    fi = open(fullpath, "r")
    for line in fi:
        maininfo = line.split("^z^")[0]
        smain = maininfo.split(',')
        observationinfo = line.split("^z^")[1].split("<z>")
        observationinfo = observationinfo[:len(observationinfo) - 1]
        observationinfos = []
        for obs in observationinfo:
            sobs = obs.split(',')
            observationinfos.append(so_exposure(sobs[0], sobs[1], sobs[2]))
        data.append(stellar(smain[0], smain[1], smain[2], observationinfos))
    return data


def getobjectnames(fullpath):
    data = readqueue(fullpath)
    names = []
    for d in data:
        names.append(d.name)
    return names


def getdatafromname(fullpath, name):
    data = readqueue(fullpath)
    for d in data:
        if d.name == name:
            return d
    return stellar("", "", "", "")


def removequeueobject(fullpath, name):
    data = readqueue(fullpath)
    iindex = None
    for i, d in enumerate(data):
        if d.name == name:
            iindex = i
    if iindex is not None:
        data.pop(iindex)
        savequeue(data, fullpath)


def getuploads():
    target = os.path.join(APP_ROOT, "uploads")
    if not os.path.isdir(target):
        os.mkdir(target)
        return []
    uploads = [x for x in os.listdir(target) if ".queue" in x]
    return uploads


def getqueuefilelist(filename):
    target = os.path.join(APP_ROOT, "uploads")
    output = []
    fullpath = target + "/" + filename
    fi = open(fullpath)
    for line in fi:
        output.append(line)
    fi.close()
    return output


@app.route('/')
@basic_auth.required
def root():
    queues = []
    if importRTS2:
	queues = populaterts2queues()
    """Main page renders the index.html page"""
    return render_template("index2.html", username=app.config['BASIC_AUTH_USERNAME'],
                           passwd=app.config['BASIC_AUTH_PASSWORD'], importRTS2=importRTS2, queues=queues)

@app.route('/rts2_status.html')
def rts2_status():
	return render_template('rts2_status.html')

@app.route('/index')
def index():
    return render_template('index.html', files=getuploads(), importRTS2=importRTS2)


@app.route('/home')
def home():
    queues = []
    if importRTS2:
        queues = populaterts2queues()
    return render_template("index2.html", username=app.config['BASIC_AUTH_USERNAME'],
                           passwd=app.config['BASIC_AUTH_PASSWORD'], importRTS2=importRTS2, queues=queues)


@app.route('/about')
def about():
    return render_template('index.html', files=getuploads(), importRTS2=importRTS2)


@app.route('/edit_queue', methods=['POST'])
def edit_queue():
    filename = request.form["edit_queue"]
    return render_template('edit_queue.html', queue=filename.split('.queue')[0], importRTS2=importRTS2)


@app.route('/load', methods=['POST'])
def load():
    target = os.path.join(APP_ROOT, "uploads")
    if not os.path.isdir(target):
        os.mkdir(target)
    for _file in request.files.getlist("queue"):
        filename = _file.filename
        destination = "/".join([target, filename])
        _file.save(destination)
        try:
            data = readlotis(destination)
            queue_dest = "/".join([target, filename.split('.')[0] + '.queue'])
            savequeue(data, queue_dest)
        except:
            pass

    return index()


@app.route('/showfile', methods=['POST'])
def showfile():
    if 'lotisweb' in request.form.keys():
        output, filename = readfromweb()
        return render_template('index.html', files=getuploads(), output=output, importRTS2=importRTS2)
    filename = request.form["load_queue"]
    target = os.path.join(APP_ROOT, "uploads")
    fullpath = target + "/" + filename
    if "display" in request.form.keys():
        output = readqueue(fullpath)
        return render_template('index.html', files=getuploads(), output=output, importRTS2=importRTS2)
    if 'edit' in request.form.keys():
        names = getobjectnames(fullpath)
        data = readqueue(fullpath)
        return render_template('edit_queue.html', queue=filename.split('.queue')[0], object_names=names, data=data, importRTS2=importRTS2)
    if 'rts2queue' in request.form.keys():
        if importRTS2:
            data = readqueue(fullpath)
            targetids = []
            for d in data:
                targetid = getrts2targetid(d)
                setrts2observscript(d, targetid)
                targetids.append(targetid)
            setrts2queue(targetids)
        return render_template('index.html', files=getuploads(), rts2queue=importRTS2, importRTS2=importRTS2)


def setrts2queue(targetids):
    if len(targetids) > 0:
        targetstring = ""
        for iid in targetids:
            targetstring += " {}".format(str(iid))
        cmd = "rts2-queue --queue plan --clear{}".format(targetstring)
        print(cmd)
        subprocess.call(cmd, shell=True)


def setrts2observscript(queueobj, targetid):
    script = "BIG61.OFFS=(1m,0) "
    # UBVRI
    filterdict = {"U": 0, "B": 1, "V": 2, "R": 3, "I": 4, "SCHOTT": 5}
    for obs in queueobj.observation_info:
        tmp = "filter={} E {} ".format(filterdict[str.upper(obs.filter)], str(obs.exptime))
        script += (tmp * int(obs.num_exposures))
    cmd = "rts2-target -c C0 --lunarDistance 15: --airmass :2.2 -s \"{}\" {}".format(script, str(targetid))
    print(cmd)
    subprocess.call(cmd, shell=True)


def getrts2targetid(queueobj):
    print(queueobj.name)
    targetid = None
    target = rts2.target.get(queueobj.name)
    print(target)
    if len(target) == 0:
	
        ra = Angle(queueobj.ra, unit=u.hour)
        dec = Angle(queueobj.dec, unit=u.deg)
        targetid = rts2.target.create(queueobj.name, ra.deg, dec.deg)
    else:
        targetid = target[0][0]
    return targetid


@app.route('/editqueuedata', methods=['POST'])
def editqueuedata():
    editname = request.form['editname']
    queuefile = request.args['queuefile'] + ".queue"
    target = os.path.join(APP_ROOT, "uploads")
    fullpath = target + "/" + queuefile
    if "edit" in request.form.keys():
        names = getobjectnames(fullpath)
        editdata = getdatafromname(fullpath, editname)
        return render_template('edit_queue.html', queue=queuefile.split('.queue')[0], object_names=names,
                               data=readqueue(fullpath), editdata=editdata)
    if "remove" in request.form.keys():
        removequeueobject(fullpath, editname)
        names = getobjectnames(fullpath)
        return render_template('edit_queue.html', queue=queuefile.split('.queue')[0], object_names=names,
                               data=readqueue(fullpath))
    if "addnew" in request.form.keys():
        names = getobjectnames(fullpath)
        return render_template('edit_queue.html', queue=queuefile.split('.queue')[0], object_names=names,
                               data=readqueue(fullpath), addnew=True)


@app.route('/updatequeuedata', methods=['POST'])
def updatequeuedata():
    editname = request.args['editname']
    queuefile = request.args['queuefile'] + ".queue"
    target = os.path.join(APP_ROOT, "uploads")
    fullpath = target + "/" + queuefile

    updatename = request.form['name']
    ra = request.form['ra']
    dec = request.form['dec']
    filters = request.form.getlist('filter')
    exptimes = request.form.getlist('exptime')
    amounts = request.form.getlist('amount')

    queueobj = stellar(updatename, ra, dec, [])
    for f in range(0, len(filters)):
        if filters[f] != "" or exptimes[f] != "" or amounts[f] != "":
            obsinfo = so_exposure(filters[f], exptimes[f], amounts[f])
            queueobj.observation_info.append(obsinfo)

    removequeueobject(fullpath, editname)
    queuedata = readqueue(fullpath)
    queuedata.append(queueobj)
    if "updateexisting" in request.form.keys() or "updatenew" in request.form.keys():
        savequeue(queuedata, fullpath)
    return render_template('edit_queue.html', queue=queuefile.split('.queue')[0], object_names=getobjectnames(fullpath),
                           data=queuedata, editdata=queueobj, addnew=("addexposobj" in request.form.keys()))


def _get_device(device):
    """
    args: device -> name of the device

    Description: Uses RTS2 HTTP interface to get a json object of all the rts2 values
        (the ones you see in rts2-mon) of a device

    returns json with device data or error message
    """
    try:
        r = requests.get(
		"http://localhost:8889/api/get?e=1&d={}".format(device), 
		auth=(CONFIG["username"], CONFIG['password'] ) )
        data = r.text
    except Exception as err:
        data = json.dumps({"error": str(err)})

    return data


def _set_rts2_value(device, name, value):
    """
    args:
        device -> name of the device
        name -> name of the value to be set ie queue_only
        value -> value to set it to

    Description:    uses rts2 http interface to set an RTS2 value.

    returns json with device data or error message
    """

    try:
        r = requests.get("http://localhost:8889/api/set?async=None&v={}&d={}&n={}".format(value, device, name))
        data = r.text
    except Exception as err:
        data = json.dumps({"error": err})

    return data


# end worker functions


# Begin flask functions


@app.route("/rts2state/<state>")
@basic_auth.required
def change_state(state):
    commer = rts2comm()
    if state.lower() in ['on', 'off', 'standby']:
        commer.set_state(state)
        resp = "state set to {}".format(state)
    else:
        resp = "bad state {}".format(state)
    return resp


@app.route('/device/<name>')
@basic_auth.required
def get_device(name=None):
    commer = rts2comm()
    return json.dumps( commer.get_device_info() )


@app.route('/device')
@basic_auth.required
def get_all_devices():
    """Get the rts2 values for all the devices in RTS2 and put them in
    one big json."""
    commer = rts2comm()
    try:
        jdata = commer.get_device_info_all()
    except Exception as err:
        jdata = {"error": str(err)}

    jdata['rts2_status'] = commer.get_state()
    return json.dumps( jdata )


@app.route('/device/set/<device>/<name>/<value>')
@basic_auth.required
def set_rts2_value(device, name, value):
    _set_rts2_value(device, name, value)


@app.route('/queuestart')
@basic_auth.required
def rts2_queue_start():
    """Easy way set all the parameters for starting
    queue observing. """
    commer = rts2comm()
    commer.set_rts2_value("SEL", "plan_queing", 3)
    commer.set_rts2_value("SEL", "queue_only", True)
    commer.set_rts2_value("BIG61", "pec_state", 1)
    commer.set_rts2_value("EXEC", "auto_loop", False)


@app.route('/lastimg')
@basic_auth.required
def download_lastimg():
    """Use C0.last_img_path to downlaod the most recent image."""
    jdata = _get_device("C0")
    return send_file(json.loads(jdata.text)["d"]["last_img_path"][1])


@app.route('/weather/boltwood.json')
@basic_auth.required
def boltwood_json():
    try:
        r = requests.get("https://www.lpl.arizona.edu/~css/bigelow/boltwoodlast.json")
        jdata = json.loads( r.text )
        if jdata['iCloud'] == 1:
            jdata['cloud_state'] ='Clear'
        elif jdata['iCloud'] == 2:
            jdata['cloud_state'] ='Partly Cloudy'
        elif jdata['iCloud'] == 3:
            jdata['cloud_state'] ='Cloudy'
        
        if jdata['iDaylight'] == 3:
            jdata['day_state'] = "Day"
        elif jdata['iDaylight'] == 2:
            jdata['day_state'] = "Dusk"
        elif jdata['iDaylight'] == 1:
            jdata['day_state'] = "Night"

        jdata = json.dumps(jdata)

    except Exception as err:
        jdata = json.dumps({"error": str(err)})
    return jdata


if __name__ == '__main__':
    app.run( host='0.0.0.0', port=1080, debug=True )

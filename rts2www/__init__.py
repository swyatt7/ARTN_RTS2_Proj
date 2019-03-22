from flask import Flask, send_file, jsonify
from flask import render_template, redirect, url_for
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
from rts2solib import asteroid, stellar, rts2comm, so_exposure, load_from_script, queue
from rts2solib.big61filters import filter_set
from rts2solib.display_image import to_jpg

from rts2solib.db import message as rts2db_messages
from rts2solib.db import rts2_images, rts2_observations, rts2_targets
import subprocess
import datetime

#from rts2.queue import Queue

#global importRTS2
#importRTS2 = True
#global prx
#prx = None
#
#import rts2
#print( "imported rts2" )



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


@app.route("/test")
def _test():
    return render_template("index2.html", username=app.config['BASIC_AUTH_USERNAME'],
            passwd=app.config['BASIC_AUTH_PASSWORD'], importRTS2=False, queues=[])

@app.route('/')
@app.route('/home')
def home():
    queues = []
    importRTS2=False
    #if importRTS2:
        #queues = populaterts2queues()
    return render_template("index2.html", username=app.config['BASIC_AUTH_USERNAME'],
            passwd=app.config['BASIC_AUTH_PASSWORD'], importRTS2=importRTS2, queues=queues)

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


@app.route("/drivers/<driver>/<action>")
@basic_auth.required
def driver_actions(driver, action):
    cmd_errors=None
    proc_errors=None
    retncode = None
    success = True
    if driver.upper() in ['C0', 'BIG61', 'EXEC', 'SEL']:
        if action.lower() == "start":
            retncode = subprocess.call(["rts2-start", driver.upper()])

        elif action.lower() == "stop":
            retncode = subprocess.call(["rts2-stop", driver.upper()])

        elif action.lower() == "restart":
            print("restart driver")
            retncode = subprocess.call(["rts2-stop", driver.upper()])
            #if retncode == 0:
            retncode = subprocess.call(["rts2-start", driver.upper()])
        else:
            cmd_errors = "Bad action {}".format(action)
            success=False


    else:
        cmd_errors = "Bad driver name {}".format(driver)
        success = False
    if retncode is not None:
        if retncode != 0:
            retncode_errors = "Bad return code {}".format(retncode)
            success = False



    return jsonify({"cmd_errors":cmd_errors, "proc_errors":proc_errors, "success":success, "retncode":retncode})


@app.route("/rts2scripts")
@basic_auth.required
def rts2scripts():
    commer=rts2comm()
    try:
        target_name = commer.get_rts2_value("EXEC", "current_name").value
        current_exp_num = commer.get_rts2_value("C0", "script_exp_num").value
    except Exception as err:
        return jsonify({"total_num_exps": "???", "script_exp_num":"???"  })

    if target_name == "":
        exps=0
    else:
        try:
            script = load_from_script(target_name)
        except Exception as err:
            return jsonify({"total_num_exps": "???", "script_exp_num":"???"  })

        exps=0
        for expset in script["obs_info"]:
            exps+=int(expset["amount"])
    return jsonify({"total_num_exps": exps, "script_exp_num":current_exp_num  })

@app.route("/focus/focusrun")
@basic_auth.required
def dofocus():
    commer=rts2comm()
    focusid = 2572 #should be in config
    ret = commer.executeCommand( "EXEC", "now 2572" )
    return jsonify({"response":ret})


@app.route("/expose/<exptime>")
@basic_auth.required
def doexposure(exptime):
    commer=rts2comm()
    try:
        commer.setValue("C0", "exposure", float(exptime))
        ret = commer.executeCommand( "EXEC", "now 2578" ) 
    except Excption as err:
        ret = err

    return jsonify({"response":ret})
@app.route('/device/<name>')
@basic_auth.required
def get_device(name=None):
    commer = rts2comm()
    return json.dumps( commer.get_device_info() )


@app.route("/filters/<Filter>")
def goto_filter(Filter):
    filts = filter_set()
    filter_num = filts[Filter]
    commer = rts2comm()
    resp = commer.setValue("W0", "filter", filter_num, True )
    return jsonify({"response": resp})

@app.route('/device')
@basic_auth.required
def get_all_devices():
    """Get the rts2 values for all the devices in RTS2 and put them in
    one big json."""
    commer = rts2comm()
    try:
        jdata = commer._getall()
    except Exception as err:
        jdata = {"error": str(err)}

    jdata['rts2_status'] = commer.get_state()
    return json.dumps( jdata )


@app.route('/device/set/<device>/<name>/<value>')
@basic_auth.required
def set_rts2_value(device, name, value):
    commer=rts2comm()
    resp = commer.setValue(device, name, value)
    return jsonify({"response":resp})


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

@app.route('/queues/<action>')
@basic_auth.required
def _queues(action):

    try:
        if action == "clear":
            q=queue.Queue("plan")
            q.load()
            q.clear()
            resp="No Error"
    except Exeption as err:
        resp = str(err)

    return jsonify({"response": resp})



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

@app.route("/image/last.jpg")
def lastimg():
    commer = rts2comm()
    fname = commer.getValue("C0", "last_image", True)
    if fname == "":
        return redirect(url_for("static", filename="noimg.jpg"))
    try:
        img = to_jpg(fname)
    except FileNotFoundError as err:
        return redirect(url_for("static", filename="noimg.jpg"))
    img.save(os.path.join(APP_ROOT, "static","latest.jpg"))
    return redirect(url_for("static", filename="latest.jpg"))


@app.route('/db/message_json/<num>', methods=['GET'])
def dbmessages_json(num=20):
    #return jsonify([{"message":"foo", "time":str(datetime.datetime.now()), "type":4}])
    msg=rts2db_messages()
    messages = msg.query().order_by(msg._rowdef.message_time.desc())[:num]
    print(messages[0].message_time)
    msg_dict = [{"message": x.message_string, "time": str(x.message_time), "type": x.message_type} for x in messages]
    return jsonify(msg_dict)


if __name__ == '__main__':
    app.run( host='0.0.0.0', port=1080, debug=True )

#try:
#    prx = rts2.createProxy( url='http://localhost:8889', username=CONFIG["username"], password=CONFIG["password"])
#    importRTS2 = True
#
#    print("RTS2 succesfully imported")
#except:
#    print("RTS2 not imported whoopsy")
#    importRTS2 = False
#
#

#name_i = 11
#ra_i = 4
#dec_i = 5
#type_i = 14
#exp_i = 7
#filt_i = 9
#amounts_i = 8
#tid_index = 0
#type_dict = {"UVOT": 0, "AzTEC": 1, "SPOL": 1, "STAND": 3}
#
#
#
#class Rts2Queue:
#	def __init__( self, _name ):
#	    self.name = _name
#	    self.queueitems = self.populate()
#
#	def populate(self):
#	    queue = rts2.Queue(prx, self.name)
#            queue.load()
#	    queueitems = []
#            for p in queue.entries:
#                targ = rts2.target.get(p.id)
#		queueitems.append(Rts2QueueItem(targ[0][1], targ[0][0]))
#	    return queueitems
#
#
#class Rts2QueueItem:
#   def __init__(self, _name, _id):
#	self.name = _name
#	self.id = _id
#
#
#class QueueObject:
#    def __init__(self, _name, _ra, _dec, _type, _obs_infos):
#        self.type = _type
#        self.name = _name
#        self.ra = _ra
#        self.dec = _dec
#        self.observation_info = _obs_infos
#
#    def outputobjectinfo(self):
#        print("Queue Object: {}, {}".format(self.name, self.type))
#        print("RA: {}".format(self.ra))
#        print("DEC: {}".format(self.dec))
#        print("Observation Infos")
#        for obsinfo in self.observation_info:
#            print("Filter: {}, Exposure Time: {}, Amount {}".format(obsinfo.filter, obsinfo.exptime, obsinfo.num_exposures))
#
#
#class ObservationInfo:
#    def __init__(self, _filter, _exptime, _amount):
#        self.amount = _amount
#        self.filter = _filter
#        self.exptime = _exptime
#
#def populaterts2queues(queues=['plan','manual','simul']):
#
#	Queues = []
#	for q in queues:
#		Queues.append(Rts2Queue(q))
#	return Queues
#
#def findoffset(sr):
#    for key in type_dict.keys():
#        if key in sr:
#            typeindex = sr.index(key)
#            if key == "STAND":
#                return -99
#            return type_i - typeindex
#    return 0
#
#
#def formatcoord(coord):
#    if "-" in coord:
#        coord = coord.split("-")[1]
#        return "-{}:{}:{}".format(coord[0:2], coord[2:4], coord[4:])
#    return "{}:{}:{}".format(coord[0:2], coord[2:4], coord[4:])
#
#
#def readlotis(fullpath):
#    fi = open(fullpath)
#    lotisdata = []
#    for line in fi:
#        splitline = line.split()
#        offset = findoffset(splitline)
#        if offset != -99 and line[0] is not "#":
#            name = splitline[name_i - offset]
#            ra = formatcoord(splitline[ra_i - offset])
#            dec = formatcoord(splitline[dec_i - offset])
#            exptime = splitline[exp_i - offset]
#            filters = splitline[filt_i - offset]
#            amounts = splitline[amounts_i - offset]
#            objtype = splitline[type_i - offset]
#            observationinfos = []
#            for f in filters:
#                observationinfos.append(so_exposure(f, exptime, amounts))
#            a = stellar(name, ra, dec, observationinfos)
#            # a.outputobjectinfo()
#            a.save()
#            lotisdata.append(a)
#    return lotisdata
#
#
#def readfromweb():
#    page = requests.get("http://slotis.kpno.noao.edu/LOTIS/skypatrol.html")
#    tree = html.fromstring(page.content)
#    targetsinfo = [re.sub('\n', '', x) for x in tree.xpath('//h2/text()')[3:] if '%' in x]
#    lotisdata = []
#    for line in targetsinfo:
#        splitline = line.split()
#        offset = findoffset(splitline)
#        if offset != -99:
#            name = splitline[9]
#            ra = formatcoord(splitline[2])
#            dec = formatcoord(splitline[3])
#            exptime = splitline[5]
#            filters = splitline[7]
#            amounts = splitline[6]
#            objtype = ""
#            observationinfos = []
#            for f in filters:
#                observationinfos.append(so_exposure(f, exptime, amounts))
#            lotisdata.append(stellar(name, ra, dec, observationinfos))
#
#    target = os.path.join(APP_ROOT, "uploads")
#    file_dest = target+'/lotisweb.queue'
#    savequeue(lotisdata, file_dest)
#    return [lotisdata, 'lotisweb.queue']
#
#
#
#def savequeue(data, fullpath):
#    # most of this  stuff has been replaced by
#    # json we will keep it around in case 
#    # there is trouble
#    #of = open(fullpath, "w+")
#    data.sort(key=lambda x: x.name, reverse=False)
#    jsonpath = fullpath.replace(".queue", ".json")
#    json_data = []
#    for i, d in enumerate(data):
#        
#        json_data.append(d.dictify())
##        param = ('{},{},{},{}'.format(d.name, d.ra, d.dec, d.type)) + "^z^"
##        for o in d.observation_info:
##            param += ('{},{},{}'.format(o.filter, o.exptime, o.num_exposures)) + "<z>"
##        of.write(param + '\n')
##    of.close()
#    with open(jsonpath, "w") as jfd:
#        json.dump( json_data, jfd, indent=2 )
#
#
#def readqueue(fullpath, save_script=False):
#    data = []
#    jsonpath = fullpath.replace(".queue", ".json")
#    
#    with open(jsonpath) as fd:
#        json_data = json.load(fd)
#    for targ in json_data:
#        data.append(stellar( **targ ))
#    return data
#
#    # data is now read in as json
#    # we shall keep the below code in
#    # case there is trouble
#    fi = open(fullpath, "r")
#    for line in fi:
#        maininfo = line.split("^z^")[0]
#        smain = maininfo.split(',')
#        observationinfo = line.split("^z^")[1].split("<z>")
#        observationinfo = observationinfo[:len(observationinfo) - 1]
#        observationinfos = []
#        for obs in observationinfo:
#            sobs = obs.split(',')
#            observationinfos.append(so_exposure(sobs[0], sobs[1], sobs[2]))
#        targ = (stellar(smain[0], smain[1], smain[2], observationinfos))
#        if save_script:
#          targ.save()
#        data.append(targ)
#    return data
#
#
#def getobjectnames(fullpath):
#    data = readqueue(fullpath)
#    names = []
#    for d in data:
#        names.append(d.name)
#    return names
#
#
#def getdatafromname(fullpath, name):
#    data = readqueue(fullpath)
#    for d in data:
#        if d.name == name:
#            return d
#    raise NameError("Can't find name {}".format(name))
#
#
#
#def removequeueobject(fullpath, name):
#    data = readqueue(fullpath)
#    iindex = None
#    for i, d in enumerate(data):
#        if d.name == name:
#            iindex = i
#    if iindex is not None:
#        data.pop(iindex)
#        savequeue(data, fullpath)
#
#
#def getuploads():
#    target = os.path.join(APP_ROOT, "uploads")
#    if not os.path.isdir(target):
#        os.mkdir(target)
#        return []
#    uploads = [x for x in os.listdir(target) if ".queue" in x]
#    return uploads
#
#
#def getqueuefilelist(filename):
#    target = os.path.join(APP_ROOT, "uploads")
#    output = []
#    fullpath = target + "/" + filename
#    fi = open(fullpath)
#    for line in fi:
#        output.append(line)
#    fi.close()
#    return output
##
#
#@app.route('/')
#@basic_auth.required
#def root():
#    queues = []
#    if importRTS2:
#	queues = populaterts2queues()
#    """Main page renders the index.html page"""
#    return render_template("index2.html", username=app.config['BASIC_AUTH_USERNAME'],
#                           passwd=app.config['BASIC_AUTH_PASSWORD'], importRTS2=importRTS2, queues=queues)
#
#@app.route('/rts2_status.html')
#def rts2_status():
#	return render_template('rts2_status.html')
#
#@app.route('/index')
#def index():
#    return render_template('index.html', files=getuploads(), importRTS2=importRTS2 )
#



    #
#@app.route('/about')
#def about():
#    return render_template('index.html', files=getuploads(), importRTS2=importRTS2)
#
#
#@app.route('/edit_queue', methods=['POST'])
#def edit_queue():
#    filename = request.form["edit_queue"]
#    return render_template('edit_queue.html', queue=filename.split('.queue')[0], importRTS2=importRTS2)
#
#
#@app.route('/load', methods=['POST'])
#def load():
#    target = os.path.join(APP_ROOT, "uploads")
#    if not os.path.isdir(target):
#        os.mkdir(target)
#    for _file in request.files.getlist("queue"):
#        filename = _file.filename
#        destination = "/".join([target, filename])
#        _file.save(destination)
#        try:
#            data = readlotis(destination)
#            queue_dest = "/".join([target, filename.split('.')[0] + '.queue'])
#            savequeue(data, queue_dest)
#        except:
#            pass
#
#    return index()
#
#
#@app.route('/nightlyreport', methods=['GET'])
#def nightlyreport():
#      
#   report = ["OBSERVED AN AMAZING SUPERNOVA IN ALL AMAZING RELEVANT FILTERS AND IT YIELDED AMAZING RESULTS", "SCIENCE FOREVER"]
#
#   return render_template('nightlyreport.html', report = report) 
#
#

#
#
#@app.route('/dbmessages', methods=['GET'])
#def dbmessages(num=20):
#    msg=rts2db_messages()
#    messages = msg.query().order_by(msg._rowdef.message_time.desc())[:num]
#  
#    return render_template('dbmessages.html', messages = messages)   
#    
#
#@app.route('/showfile', methods=['POST'])
#def showfile():
#    if 'lotisweb' in request.form.keys():
#        output, filename = readfromweb()
#        return render_template('index.html', files=getuploads(), output=output, importRTS2=importRTS2)
#    filename = request.form["load_queue"]
#    target = os.path.join(APP_ROOT, "uploads")
#    fullpath = target + "/" + filename
#    if "display" in request.form.keys():
#        output = readqueue(fullpath, save_script=False)
#        return render_template('index.html', files=getuploads(), output=output, importRTS2=importRTS2)
#    if 'edit' in request.form.keys():
#        names = getobjectnames(fullpath)
#        data = readqueue(fullpath, False)
#        return render_template('edit_queue.html', queue=filename.split('.queue')[0], object_names=names, data=data, importRTS2=importRTS2)
#    if 'rts2queue' in request.form.keys():
#        if importRTS2:
#            data = readqueue(fullpath, False)
#            targetids = []
#            for d in data:
#                d.save()
#                targetid = d.id
#                #setrts2observscript(d, targetid)
#                targetids.append(targetid)
#            setrts2queue(targetids)
#            print(fullpath)
#        return render_template('index.html', files=getuploads(), rts2queue=importRTS2, importRTS2=importRTS2)
#
#
#def setrts2queue(targetids):
#    if len(targetids) > 0:
#        print("LOADING THE QUEUES")
#        q = rts2.Queue( prx, 'plan' )
#        targetstring = ""
#        
#        for iid in targetids:
#            if type(iid) == list:#hack iid should not be a list!
#                iid = iid[0]
#            q.add_target(iid)
#
#        #q.load()
#        #q.save()
##            targetstring += " {}".format(str(iid))
##        cmd = "rts2-queue --queue plan --clear{}".format(targetstring)
##        print(cmd)
##        subprocess.call(cmd, shell=True)
#
#
#def setrts2observscript(queueobj, targetid):
#    script = "BIG61.OFFS=(1m,0) "
#    # UBVRI
#    filterdict = {"U": 0, "B": 1, "V": 2, "R": 3, "I": 4, "SCHOTT": 5}
#    for obs in queueobj.observation_info:
#        tmp = "filter={} E {} ".format(filterdict[str.upper(obs.filter)], str(obs.exptime))
#        script += (tmp * int(obs.num_exposures))
#    cmd = "rts2-target -c C0 --lunarDistance 15: --airmass :2.2 -s \"{}\" {}".format(script, str(targetid))
#    
#    print(cmd)
#    subprocess.call(cmd, shell=True)
#
#
#def getrts2targetid(queueobj):
#    print(queueobj.name)
#    targetid = None
#    target = rts2.target.get(queueobj.name)
#    print(target)
#    if len(target) == 0:
#	
#        ra = Angle(queueobj.ra, unit=u.hour)
#        dec = Angle(queueobj.dec, unit=u.deg)
#        targetid = rts2.target.create(queueobj.name, ra.deg, dec.deg)
#    else:
#        targetid = target[0][0]
#    return targetid
#
#
#@app.route('/editqueuedata', methods=['POST'])
#def editqueuedata():
#    if 'editname' in request.form:
#        editname = request.form['editname']
#    else:
#        editname = None
#        
#    queuefile = request.args['queuefile'] + ".queue"
#    target = os.path.join(APP_ROOT, "uploads")
#    fullpath = target + "/" + queuefile
#    if "edit" in request.form.keys():
#        names = getobjectnames(fullpath)
#        editdata = getdatafromname(fullpath, editname)
#        return render_template('edit_queue.html', queue=queuefile.split('.queue')[0], object_names=names,
#                               data=readqueue(fullpath), editdata=editdata)
#    if "remove" in request.form.keys():
#        removequeueobject(fullpath, editname)
#        names = getobjectnames(fullpath)
#        return render_template('edit_queue.html', queue=queuefile.split('.queue')[0], object_names=names,
#                               data=readqueue(fullpath))
#    if "addnew" in request.form.keys():
#        names = getobjectnames(fullpath)
#        return render_template('edit_queue.html', queue=queuefile.split('.queue')[0], object_names=names,
#                               data=readqueue(fullpath), addnew=True)
#
#
#@app.route('/updatequeuedata', methods=['POST'])
#def updatequeuedata():
#    editname = request.args['editname']
#    queuefile = request.args['queuefile'] + ".queue"
#    target = os.path.join(APP_ROOT, "uploads")
#    fullpath = target + "/" + queuefile
#
#    updatename = request.form['name']
#    ra = request.form['ra']
#    dec = request.form['dec']
#    filters = request.form.getlist('filter')
#    exptimes = request.form.getlist('exptime')
#    amounts = request.form.getlist('amount')
#
#    queueobj = stellar(updatename, ra, dec, [])
#    for f in range(0, len(filters)):
#        if filters[f] != "" or exptimes[f] != "" or amounts[f] != "":
#            obsinfo = so_exposure(filters[f], exptimes[f], amounts[f])
#            queueobj.observation_info.append(obsinfo)
#	#queueobj.save()
#    removequeueobject(fullpath, editname)
#    queuedata = readqueue(fullpath)
#    queuedata.append(queueobj)
#    if "updateexisting" in request.form.keys() or "updatenew" in request.form.keys():
#        savequeue(queuedata, fullpath)
#    return render_template('edit_queue.html', queue=queuefile.split('.queue')[0], object_names=getobjectnames(fullpath),
#                           data=queuedata, editdata=queueobj, addnew=("addexposobj" in request.form.keys()))
#


# end worker functions


# Begin flask functions




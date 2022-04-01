#!/usr/bin/env python
# coding: utf-8
# Copyright (c) 2013-2014 Abram Hindle
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import flask
from flask import Flask, request
from flask_sockets import Sockets
import random
import string
import gevent
from gevent import queue
import json

app = Flask(__name__, template_folder="static", static_folder="static")
sockets = Sockets(app)
app.debug = True


class World:
    def __init__(self):
        self.space = dict()
        self.listeners = list()

    def add_set_listener(self, listener):
        self.listeners.append( listener )

    def remove_listener(self, listener):
        self.listeners.remove(listener)

    def update(self, entity, key, value):
        entry = self.space.get(entity, dict())
        entry[key] = value
        self.space[entity] = entry
        self.update_listeners( entity )

    def set(self, entity, data):
        self.space[entity] = data
        self.update_listeners(entity)

    def update_listeners(self, entity):
        """update the set listeners"""
        for listener in self.listeners:
            listener.put(entity, self.get(entity))

    def clear(self):
        self.space = dict()
        for listener in self.listeners:
            listener.clear()

    def get(self, entity):
        return self.space.get(entity, dict())

    def world(self):
        return self.space


class Client:
    def __init__(self):
        self.id = ''.join([random.choice(string.ascii_lowercase) for i in range(5)])
        self.queue = queue.Queue()
        self.counter = 0

    def __eq__(self, other):
        return self.id == other.id

    def add_entity(self, data):
        if "x" not in data:  # We Have Been Given An Entity Name
            for entity in data:
                myWorld.set(entity, data[entity])
        else:  # We Generate A New Entity Name
            myWorld.set(f"{self.id}-{self.counter}", data)
            self.counter += 1

    def clear(self):
        self.counter = 0
        self.queue.put_nowait({"clear": True})

    def put(self, entity, data):
        d = dict()
        d[entity] = data
        self.queue.put_nowait(d)

    def get(self):
        return self.queue.get()


myWorld = World()


@app.route('/')
def hello():
    """Return something coherent here.. perhaps redirect to /static/index.html """
    return flask.render_template("index.html")


def read_ws(ws, client: Client):
    """A greenlet function that reads from the websocket and updates the world"""
    try:
        while True:
            msg = ws.receive()
            print("WS RECV: %s" % msg)
            if msg is not None:
                packet = json.loads(msg)
                client.add_entity(packet)
            else:
                break
    except:
        print("WebSocket Closed")


@sockets.route('/subscribe')
def subscribe_socket(ws):
    """Fulfill the websocket URL of /subscribe, every update notify the
       websocket and read updates from the websocket """
    print("Websocket Connected!")
    client = Client()
    myWorld.add_set_listener(client)
    g = gevent.spawn(read_ws, ws, client)
    try:
        while True:
            msg = client.get()
            ws.send(json.dumps(msg))
    except Exception as e:  # WebSocketError as e:
        print("WS Error %s" % e)
    finally:
        myWorld.remove_listener(client)
        gevent.kill(g)


# I give this to you, this is how you get the raw body/data portion of a post in flask
# this should come with flask but whatever, it's not my project.
def flask_post_json():
    """Ah the joys of frameworks! They do so much work for you
       that they get in the way of sane operation!"""
    if request.json is not None:
        return request.json
    elif request.data is not None and request.data.decode("utf8") != u'':
        return json.loads(request.data.decode("utf8"))
    else:
        return json.loads(request.form.keys()[0])


@app.route("/entity/<entity>", methods=['POST', 'PUT'])
def update(entity):
    """update the entities via this interface"""
    myWorld.set(entity, flask_post_json())
    return flask.Response(json.dumps(myWorld.get(entity)), status=200, mimetype="application/json")


@app.route("/world", methods=['POST','GET'])    
def world():
    """you should probably return the world here"""
    return flask.Response(json.dumps(myWorld.world()), status=200, mimetype="application/json")


@app.route("/entity/<entity>")    
def get_entity(entity):
    """This is the GET version of the entity interface, return a representation of the entity"""
    response = json.dumps(myWorld.get(entity))
    return flask.Response(response, status=200, mimetype="application/json")


@app.route("/clear", methods=['POST','GET'])
def clear():
    """Clear the world out!"""
    myWorld.clear()
    return flask.Response(json.dumps(dict()), status=200, mimetype="application/json")


if __name__ == "__main__":
    ''' This doesn't work well anymore:
        pip install gunicorn
        and run
        gunicorn -k flask_sockets.worker sockets:app
    '''
    app.run()
